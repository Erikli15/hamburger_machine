"""
Transportband (Conveyor) controller för hamburgerautomaten.

Denna modul styr transportbandet som flyttar hamburgare komponsenter
mellan olika stationer i systemet
"""

import time
import threading
import logging
from typing import Optional, Callable, Dict, Any
from enum import Enum
from dataclasses import dataclass
import RPi.GPIO as GPIO # För Raspberry Pi kompatibletet
import random # För simulering, ta bort i produktion

# Konstanter
CONVEYOR_SPEEDS = {
    "slow": 0.3,
    "normal": 0.5,
    "fast": 0.8,
    "max": 1.0
}

class ConveyorDirection(Enum):
    """Riktning för transportbandet."""
    FORWARD = 1
    REVERSE = 2
    STOP = 3

class ConveyorZone(Enum):
    """Olika zoner i transportbandet."""
    LOADING = 1 # Laddningszon - ingredinser Läggs på
    COOKING = 2 # Tillagningszon - grill/friös
    ASSEMBLY = 3 # Monteringszon - robotarmen
    QUALITY_CHECK = 4 # Kvalitetskontroll
    PACKAGING = 5 # Föråackningszon
    DELIVERY = 6 # Utlämningszon

@dataclass
class ConveyorStatus:
    """Statusinformation för transportbandet."""
    is_moving: bool = False
    direction: ConveyorDirection = ConveyorDirection.STOP
    current_speed: float = 0.0
    current_position: float = 0.0 # i centimeter från start
    current_zone = Optional[ConveyorZone] = None
    items_on_belt: list = None # Lista med objekt på bandet

    def __post_init__(self):
        if self.items_on_belt is None:
            self.items_on_belt = []
    
class ItemOnBelt:
    """Reprentation av ett objekt på transportbandet."""

    def __init__(self, item_id: str, item_type: str, position: float):
        self.item_id = item_id
        self.item_type = item_type # "patty", "bun", "chees", etc.
        self.position = position # Position i cm från start
        self.zone = None
        self.timestamp = time.time()

    def __repr__(self):
        return f"Item {self.item_type}, id:{self.item_id}, pos:{self.position:.1f}cm"
    
class Conveyor:
    """
    Huvudklass för att styra transportbandet.
    
    Ansvarar för:
    - Start/stoppa bandet
    - Kontrollera hastighet och riktning
    - Spåra positioner på bandet
    - Hantera objelt på bandet
    - Zonindelning och positionering
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initiera transportbander.

        Args:
            config: Konfigurationsdictionary med inställningar
        """
        self.logger = logging.getLogger(__name__)
        self.config = config

        # Hårdvarupinnar (Raspbarry Pi)
        self.motor_pins = config.get("motor_pins", {"enble": 17, "input1": 27, "input2": 22})
        self.sensor_pins = config.get("sensor_pins", {"start": 23, "zone1": 24, "zone2": 25})

        # Dimensioner
        self.total_length = config.get("total_length_cm", 200.0) # Total längd i cm
        self.zone_boundaries = config.get("zone_boudaries", {
            ConveyorZone.LOADING: (0, 30),
            ConveyorZone.COOKING: (30, 80),
            ConveyorZone.ASSEMBLY: (80, 120),
            ConveyorZone.QUALITY_CHECK: (120, 150),
            ConveyorZone.PACKAGING: (150, 180),
            ConveyorZone.DELIVERY: (180, 200)
        })

        # Status
        self.status = ConveyorStatus()
        self.items_on_belt = []
        self.item_counter = 0

        # GPIO setup (endast om vi kör på riktig hårdvara)
        self.simulation_mode = config.get("simulation_mode", True)

        if not self.simulation_mode:
            self._setup_gpio()

        # Motorhastighetsreglering
        self.speed_pw, = None
        self.target_speed = 0.0
        self.acceleration_rate = config.get("acceleration_rate", 0.1) # Hastighetsändring per sekund

        # Thread för kontinurlig körning
        self.running = False
        self.control_thread = None
        self.lock = threading.Lock()

        # Callbacks för hänselsen
        self.callbacks = {
            "item:entred_zone": [],
            "item_left_zone": [],
            "position_reached": [],
            "emergency_stop": [],
            "maintenance_needed": []
        }

        self.logger.info("Conveyor initialiserad")

    def _setup_gpio(self):
        """Konfigurera GPIO-pinner för motorstyrning."""
        GPIO.setmode(GPIO.BCM)

        # Motorpinnor
        GPIO.setup(self.motor_pins["enable"], GPIO.OUT)
        GPIO.setup(self.motor_pins["input1"], GPIO.OUT)
        GPIO.setup(self.motor_pins["input2"], GPIO.OUT)

        # Sensorpinnar (optiska eller magnetiska sensorer)
        for pin in self.sensor_pins.values():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # PWM för hastig hetskotroll
        self.speed_pwm = GPIO.PWM(self.motor_pins["enable"], 1000) # 1 kHz PWM
        self.speed_pwm.start(0)

    def start(self):
        """Starta transportbandet."""
        with self.lock:
            if not self.running:
                self.running = True
                self.control_thread = threading.Thread(target=self._control_loopm, deamon=True)
                self.control_thread.start()
                self.logger.info("Transportband startat")
            return True
        
    def stop(self, emergency: bool = False):
        """Stoppa transportbandet.

        Args:
            emergency: On sant, omedelbart stopp (nödstopp)
        """
        with self.lock:
            self.running = False
            self.target_speed = 0.0

        if emergency:
            self.status.current_speed = 0.0
            self.status.is_moving = False
            self.status.direction = ConveyorDirection.STOP
            self._emergency_stop_hardware()
            self.logger.warning("Nödstopp aktiverat för transportband")

            # Utlöst callback för nödstopp
            self._trigger_callback("emergency_stop", "Emergency stop activated")
        else:
            self.logger.info("Transportband stoppat normalt")

        if self.control_thread:
            self.control_thread.join(timeout=2.0)

    def move_forwarde(self, speed: str = "normal"):
        """
        Flytta bandet framåt.

        Args:
            speed: "slow", "normal", "fast", "max"
        """
        speed_value = CONVEYOR_SPEEDS.get(speed, 0.5)

        with self.lock:
            self.target_speed = speed_value
            self.status.direction = ConveyorDirection.FORWARD
            self.status.is_moving = True
            self.logger.debug(f"Bandet rör sig framåt med hastighet: {speed}")

    def move_reverse(self, speed: str = "slow"):
        """
        Flytta bansdet bakåt (för underhåll/felsökning).

        Args:
            speed: "slow", "normal", "fast", "max"
        """
        seed_value = CONVEYOR_SPEEDS.get(speed, 0.3)

        with self.lock:
            self.target_speed = seed_value
            self.status.direction = ConveyorDirection.REVERSE
            self.status.is_moving = True
            self.logger.debug(f"Bandet rör sig bakåt med hastighetet: {speed}")

    def set_speed(self, speed_percentage: float):
        """
        Ställ in specifik hastighet.

        Args:
            speed_percentage: 0.0 till 1.0
        """
        if 0.0 <= speed_percentage <= 1.0:
            with self.lock:
                self.target_speed = speed_percentage
                self.logger.debug(f"Ogiltig hastighet: {speed_percentage}. Måste vara mellan 0 och 1.")

    def move_to_position(self, position_cm: float, speed: str = "normal"):
        """
        Flytta till specifik position på bandet.

        Args:
            position_cm: Position i centimeter från start
            speed: Hastighet att köra med
        """
        if position_cm < 0 or position_cm > self.total_length:
            self.logger.error(f"Ogiltig position: {position_cm}cm")
            return False
        
        speed_value = CONVEYOR_SPEEDS.get(speed, 0.5)

        # Simulerad positionering
        distance = abs(position_cm - self.status.current_position)
        estimated_time = distance / (speed_value * 100) # 100 cm/s vid full hastighet

        self.logger.info(f"Flytta till position: {position_cm}cm, uppskattad tid: {estimated_time:.1f}s")

        # I en riktig implementation skulle vi ha encoder för positionering
        self.target_speed = speed_value
        self.status.direction = ConveyorDirection.FORWARD

        # simulera rörelse (i verkligheten väntar vi på sensorer/encoder)
        def _move_to_target():
            self.sleep(estimated_time)
            self.status.current_position = position_cm
            self._update_zone()
            self._trigger_callback("position_reached", position_cm)
            self.logger.info(f"Nådde position {position_cm}cm")

        threading.Thread(target=_move_to_target, daemon=True).start()
        return True
    
    def add_item(self, item_type: str, position: Optional[float] = None) -> str:
        """
       Lägg till ett objekt på bandet.

       Args:
            item_type: Typ av objekt ("patty", "bun", etc.)
            position: Startposition (None för nurvarande position)

        Returns:
            item_id: Unikt ID objekt
        """
        if position is None:
            position = self.status.current_position
        
        with self.lock:
            self.item_counter += 1
            item_id = f"{item_type}_{self.item_counter:04d}"

            item = self._get_zone_for_position(position)
            zone = self._get_zone_for_position(position)
            item_zone = zone

            self.items_on_belt.append(item)
            self.status.items_on_belt.append(item)

            self.logger.info(f"Objekt tillagt: {item} i zon {zone}")

            # Utlös callback för nytt objekt i zon
            self._trigger_callback("item_entered_zone", {"item": item, "zone": zone})

            return item_id

    def remove_item(self, item_id: str) -> bool:
        """
       Tabort ett objekt från bandet.

       Args:
            item_id: Id för objektet att ta bort

        Retuns:
            True om objektet togs bort, False annars
        """
        with self.lock:
                for j, item in enumerate(self.items_on_belt):
                    if item.item_id == item_id:
                        removed_item = self.items_on_belt.pop(j)
                        break

                self.logger.info(f"Objekt borttaget: {removed_item}")

                # Utlös callback för objekt lämmnat zon
                if removed_item.zone:
                    self._trigger_callback("item_left_zone", {"item": removed_item, "zone": removed_item.zone})

                    return True
                
                self.logger.warning(f"Kunde inte hitta objektet med ID: {item_id}")
                return False
        
    def get_items_in_zone(self, zone: ConveyorZone) -> list:
        """
        Hämta alla objekt i en specifik zon.

        Args:
            zone: Zone ett söka i

        Returns:
            Lista med itemOnBelt-objekt
        """
        with self.lock:
            return [item for item in self.items_on_belt if item.zone == zone]
        
    def get_item_position(self, item_id: str) -> Optional[float]:
        """
        Hämta position för specifikt objekt.

        Args:
            item_id: ID för objektet

        Returns:
            Position i cm eller None om inte hittas 
        """
        with self.lock:
            for item in self.items_on_belt:
                if item.item_id == item_id:
                    return item.position
        return None
    
    def get_status(self) -> ConveyorStatus:
        """Hämta aktuell för transportbandet."""
        with self.lock:
            return self.status
        
    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Hämta diagnostikinformation.

        Returns:
            Dictionary med diagnostikdata
        """
        with self.lock:
            return {
                "is_operational": self.running,
                "motor_current": self._read_motor_current(),
                "sensor_status": self._check_sensors(),
                "belt_tension": self._check_belt_tension(),
                "total_item_processed": self.item_counter,
                "items_on_belt_count": len(self.items_on_belt),
                "zones_with_items": {
                    zone.name: len(self.get_items_in_zone(zone))
                    for zone in ConveyorZone
                }
            }

    def register_callback(self, event_type: str, callback: Callable):
        """
        Registrera en callback-funktion för en händelse.

        Args:
            event_type: Type av händelse
            callback: Funktion att anropa
        """
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
            self.logger.debug(f"Callback registrerad för {event_type}")
        else:
            self.logger.error(f"Okänd händelsetyp: {event_type}")

    def _control_loop(self):
        """Huvudkontrolloop för transportbandet."""
        self.logger.info("Kontrollop startad")

        last_update = time.time()

        with self.running:
            current_time = time.time()
            delta_time = current_time - last_update

            try:
                with self.lock:
                    # Uppdatera hastighet (ramp up/down)
                    if self.status.current_speed < self.target_speed:
                        increase = min(self.acceleration_rate * delta_time, self.target_speed - self.status.current_speed)
                        self.status.current_speed += increase
                    elif self.status.current_speed > self.target_speed:
                        decrease = min(self.acceleration_rate * delta_time, self.status.current_speed - self.target_speed)
                        self.status.current_speed -= decrease

                    # Uppdatera position om vi rör oss
                    if self.status.is_moving and self.status.current_speed > 0:
                        # Beräkna rörelse (cm per sekund)
                        movement_cm = self.status.current_speed * 100 * delta_time

                    if self.status.direction == ConveyorDirection.FORWARD:
                        self.status.current_position += movement_cm
                        if self.status.current_position > self.total_length:
                            self.status.current_position = self.total_length
                            self.status.is_moving = False
                    elif self.status.direction == ConveyorDirection.REVERSE:
                        self.status.current_position -= movement_cm
                        if self.status.current_position < 0:
                            self.status.current_position = 0
                            self.status.is_moving = False

                    # Uppdatera alla objekt på bandet
                    for item in self.items_on_belt:
                        if self.status.direction == ConveyorDirection.FORWARD:
                            item.update_position(item.position + movement_cm)
                        elif self.status.direction == ConveyorDirection.REVERSE:
                            item.update_position(item.position - movement_cm)

                    # Kolla om vi har bytt zon
                    new_zone = self._get_zone_for_position(self.status.current_position)

                    if new_zone != self.status.current_zone:
                        old_zone = self.status.current_zone
                        self.status.current_zone = new_zone
                        self._handle_zoen_change(old_zone, new_zone)

                    # Uppdatera zoner för atta objekt
                    for item in self.items_on_belt:
                        item_zone = self._get_zone_for_position(item.position)
                        if item_zone != item_zone:
                            old_zone = item.zone
                            item_zone = item_zone
                            self._handle_item_zone_change(item, old_zone, item_zone)

                    # Simulerad hårdvarustyrning
                    if not self.simulation_mode:
                        self._update_hardware()

                    # Periodisk diagnostik
                    if int(current_time) % 30 == 0: # Var 30:e sekund
                        self._run_diagnostics()
            except Exception as e:
                self.logger.error(f"Fel i kontrolloop: {e}", exc_info=True)

            last_update = current_time
            time.sleep(0.01) # 10,s uppdateringsfrekvens

        self.logger.info("Kontrolloop avslutad")

    def _get_zone_for_position(self, position: float) -> Optional[ConveyorZone]:
        """Hämta zon för given position"""
        for zone, (start, end) in self.zone_boundaries.items():
            if start <= position <=end:
                return zone
        return None
    
    def _update_zone(self):
        """Uppdatera aktuell zon baserat på position."""
        self.status.current_zone = self._get_zone_for_position(self.status.current_position)

    def _handle_zone_change(self, old_zone: Optional[ConveyorZone], new_zone: ConveyorZone):
        """Hantera zonebyte."""
        self.logger.debug(f"Bytte zon: {old_zone} -> {new_zone}")

        # Här kan vi lägga till zon-specifik logik
        if new_zone == ConveyorZone.DELIVERY:
            self.logger.info("När utlämningszonen - förbred för kundöverlämmning")
        elif new_zone == ConveyorZone.COOKING:
            self.logger.info("I tillagningszonen - aktivera värmekontroll")

    def _handle_item_zone_change(self, item: ItemOnBelt, old_zone: Optional[ConveyorZone], new_zone: ConveyorZone):
        """Hantera när ett objekt byter zon."""
        if old_zone:
            self._trigger_callback("item_left_zone", {"item": item, "zone": old_zone})

            self._trigger_callback("item_entered_zone", {"itme": item, "zone": new_zone})

            self.logger.debug(f"Objekt {item.item_id} bytte zon: {old_zone} -> {new_zone}")

    def _update_hardware(self):
        """Uppdatera hårdvarutröstning (Raspbarry Pi)."""
        if not self.simulation_mode:
            # Styr motorriktning
            if self.status.direction == ConveyorDirection.FORWARD:
                GPIO.output(self.motor_pins["input"], GPIO.HIGH)
                GPIO.output(self.motor_pins["iput2"], GPIO.LOW)
            elif self.status.direction == ConveyorDirection.REVERSE:
                GPIO.output(self.motor_pins["input1"], GPIO.LOW)
                GPIO.output(self.motor_pins["input2"], GPIO.HIGH)
            else: # STOP
                GPIO.output(self.motor_pins["input1"], GPIO.LOW)
                GPIO.output(self.motor_pins["input2"], GPIO.LOW)

            # Ställ in PWM för hastighet
            if self.speed_pwm:
                pwm_duty_cycle = self.status.current_speed * 100
                self.speed_pwm.ChangeDutyCycle(pwm_duty_cycle)

    def _emergency_stop_hardware(self):
        """Nödstopp av hårdvara."""
        if not self.simulation_mode:
            # Kortslut motor för snabb bromsning
            GPIO.output(self.motor_pins["input1"], GPIO.HIGH)
            GPIO.output(self.motor_pins["input2"], GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(self.motor_pins["input1"], GPIO.LOW)
            GPIO.output(self.motor_pins["input2"], GPIO.LOW)

    def _read_morot_current(self) -> float:
        """Läs morotström (simulerad/verklig)."""
        if self.simulation_mode:
            # Simulerad strömläsning
            base_current = 0.5
            load_current = len(self.items_on_belt) * 0.1
            speed_factor = self.status.current_speed * 0.3
            noise = random.uniform(-0.05, 0.05)
            return base_current + load_current + speed_factor + noise
        else:
            # I verkligheten: läs från strömsensor
            # Returnera placehplder
            return 0.0
        
    def _check_sensor(self) -> Dict[str, bool]:
        """Kolla status på alla sensorer."""
        sensor_status = {}

        if self.simulation_mode:
            # Simulerad sensorstatus
            for name, pin in self.sensor_pins.items():
                # Simulera att senorerna fungerar 99% av tiden
                sensor_status[name] = random.random() < 0.99
        else:
            # Läs riktiga sensorer
            for name, pin in self.sensor_pins.items():
                sensor_status[name] = GPIO.input(pin) == GPIO.LOW # Aktiv låg

        return sensor_status
    
    def _check_belt_tension(self) -> float:
        """Kolla bandspänneing (simulerad)."""
        # I verkligheten skulle vi ha en spänningssensor
        # Här returnerar vi ett simulerat värde
        base_tension = 0.8
        wear_factor = self.item.counter / 10000.0 # Ökar med användning
        variation = random.uniform(-0.05, 0.05)

        tension = base_tension - min(wear_factor, 0.3) + variation

        # Varnign om spänning är låg
        if tension < 0.6:
            self.logger.warning(f"Låg bandspänning: {tension:.2f}")
            self._trigger_callback("maintenance_needed", {"issue":"low_belt", "value": tension})

        return tension
    
    def _run_diagnostics(self):
        """Kör systemdiagnostik."""
        diagnostics = self.get_diagnostics()

        # Logga viktig diagnostik
        if not all(diagnostics["sensor_status"].values()):
            failed_sensors = [k for k, v in diagnostics["sensor_status"].items() if not v]
            self.logger.warning(f"Fel på sensorer: {failed_sensors}")

        if diagnostics["motor_current"] > 2.0: # För hög ström
            self.logger.error(f"För hög motorström: {diagnostics["motor_current"]}A")
            self._trigger_callback("maintenance_needed", {"issue": "high_motor_current", "value": diagnostics["motor_current"]})

    def _trigger_callback(self, event_type: str, data: Any):
        """Utlöst alla registrerade callbacks för en händelse."""
        if event_type in self.callbacks:
            for callback in self.callbacks[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    self.logger.error(f"Callback-fel för {event_type}: {e}")

    def cleanup(self):
        """Städa upp och frigör ewsurser."""
        self.stop()

        if not self.simulation_mode:
            if self.speed_pwm:
                self.speed_pwm.stop()
            GPIO.cleanup()
        
        self.logger.info("Coneyor rensed upp")

# Factory funkrion för arr skapa conveyor.insrans
def creat_conveyor(config_path: Optional[str] = None) -> Conveyor:
    """
   Skapa en conveyor-insrans från konfiguration.

   Args:
        config_path: Sökväg till konfigurationsfil (valfritt)

    Returns:
        Conveyor-instans
    """
    import yaml

    # Standardkontronfiguration
    deafult_config = {
        "simulation_mode": True,
        "total_leangth_cm": 200.0,
        "acceleration_rate": 0.1,
        "motor_pins": {
            "eneble": 17,
            "input1": 27,
            "input2": 22
        },
        "sensor_pins": {
            "start": 23,
            "zone1": 24,
            "zone2": 25
        },
        "zone_boundaries": {
            "LOADING": (0, 30),
            "COOKING": (30, 80),
            "ASSEMBLY": (80, 120),
            "QUALITY_CHECK": (120, 150),
            "PACKAGEING": (150, 180),
            "DELIVERY": (180, 200)
        }
    }

    config = deafult_config

    # Läs från fil om angiven
    if config_path:
        try:
            with open(config_path, "r") as f:
                file_config = yaml.safe_load(f)
                config.update(file_config)
        except Exception as e:
            logging.error(f"Kunde inte läsa konfigurationsfil: {e}")
    
    # Konventera zonsträngar till enum
    zone_map = {zone.name: zone for zone in ConveyorZone}
    if "zone_boundaries" in config:
        config["zone_boudaries"] = {
            zone_map.get(zone_name, ConveyorZone.LOADING): boundaries
            for zone_name, boundaries in config["zone_boudaries"].items()
        }

    return Conveyor(config)

# Exempel på användnong och test
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # SKapa conveyor-instans
    conveyor = creat_conveyor()

    # Exempel på callback funktiom
    def zone_entred_callback(data):
        item = data["item"]
        zone = data["zone"]
        print(f"Callback: Objekt {item.item_id} ({item.item_type})" f"entred zone {zone.name}")

    # Registrera callback
    conveyor.register_callback("item_entered_zone", zone_entred_callback)

    try:
        # Starta bandet
        conveyor.start()

        # Testa grundläggande funktioner
        conveyor.move_forwarde("normal")

        # Lägg till objekt
        item1 = conveyor.add_item("patty", position=10.0)
        item2 = conveyor.add_item("bun", position=15.0)

        # Vänta lite
        time.sleep(2)

        # Hämta status
        status = conveyor.get_status()
        print(f"\nStatus:")
        print(f" Position: {status.current_position:.1f}cm")
        print(f" Zon: {status.current_zone}")
        print(f" Hastighet: {status.current_speed:.2f}")
        print(f" Antal objekt: {len(status.items_on_belt)}")

        # Hämta diagnostik
        diag = conveyor.get_diagnostics()
        print(f"\nDiagnostik:")
        print(f" Motorström: {diag["motor_current"]:.2f}A")
        print(f" Bandspänning: {diag["belt_tension"]:.2f}")

        # Testa positionering
        conveyor.move_to_position(100.0, "slow")
        time.sleep(3)

        # Ta bort ett objekt
        conveyor.remove_item(item1)

        # Hämta objekt i zon
        items_in_assembly = conveyor.get_items_in_zone(ConveyorZone.ASSEMBLY)
        print(f"\Objekt i monteringzon: {len(items_in_assembly)}")

    except KeyboardInterrupt:
        print("\nAvbryten användare")
    finally:
        # Stada upp 
        conveyor.stop()
        conveyor.cleanup()
        print("Test avslutat")
                    
            
