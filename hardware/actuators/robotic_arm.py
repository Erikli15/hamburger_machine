"""
Robotic Arm Controller
Hanterar robotaremens rörelser för hantera hamburgare och ingredienser
"""

import time
import threading
import logging
from enum import Enum
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import RPi.GPIO as GPIO # För Respberry Pi
# Alterjativt: import board import digialia (för Adafruit/CiruitPython)

logger = logging.getLogger(__name__)

class ArmPosition(Enum):
    """Fördefinierade positioner för robotarmen."""
    HOME = "home"
    BUN_DISPENSER = "bun_dispenser70"
    GRILL = "grill"
    FRYER = "fryer"
    TOPPING_STATION_1 = "topping_station_1"
    TOPPING_STATION_2 = "topping_station_2"
    TOPPING_STATION_3 = "topping_station_3"
    SAUCE_STATION = "sauce_station"
    CONVEYOR_IN = "conveyor_in"
    CONVEYOR_OUT = "conveyor_out"
    WASTE_BIN = "waste_bin"
    MAINTENANCE = "maintenance"


class ArmStatus(Enum):
    """Status för robotarmene."""
    IDLE = "idle"
    MOVING = "moving"
    GRIPPING = "gripping"
    RELEASING = "releasing"
    ERROR = "error"
    CALIBRATING = "calibrating"
    MAINTENANCE = "maintenance"

class ArmError(Enum):
    """Feltyper för robotarmen."""
    MOTOR_STALL = "motor_stall"
    OVERCURRRENT = "overcurrent"
    POSITION_ERROR = "position_error"
    GRIPPER_FAILURE = "gripper_failure"
    COLLISION_DETECTED = "collision_detected"
    COMMUNICATION_ERROR = "communication_error"
    CALIBRATION_ERROR = "calibration_error"

@dataclass
class ArmState:
    """Aktuellt tillstånd för robotarmen"""
    position: ArmPosition
    status: ArmStatus
    gripper_open: bool
    current_load: float # gram
    temperature: float # Celsius
    errors: List[ArmError]
    last_maintenance: float # timestamp
    operation_count: int

class GripperType(Enum):
    """Typer av grippers."""
    VACUUM = "vacuum"
    MECHANICAL = "mechanical"
    MAGNETIC = "magnetic"
    SOFT_GRIP = "soft_grip"

class RoboticArm:
    """
    Huvudklass för robotarmkontroll.
    Simulerad eller fysisk implementation beronde på konfiguration.
    """

    def __init__(self, config: Dict[str, Any], simulation_mode: bool = False):
        """
        Initiera robotarmen.

        Args:
            config: Konfigurationsdictionary
            simulation_mode: Om True, kör i simuleringsläge
        """
        self.config = config
        self.simulation_mode = simulation_mode
        self.state = ArmState(
            position=ArmPosition.HOME,
            status=ArmStatus.IDLE,
            gripper_open=True,
            current_load=0.0,
            temperature=25.0,
            errors=[],
            last_maintenance=time.time(),
            operation_count=0
        )

        # Konfiguration
        self.gripper_type = GripperType(config.get("gripper_type", "vacuum"))
        self.max_payload = config.get("max_payload", 500.0) # gram
        self.speed_factor = config.get("speed_factor", 1.0)
        self.safe_temperature = config.get("safe_temperature", 60.0)

        # GPIO-pins för Raspberry Pi (anpassa efter din konfiguration)
        self.pins = {
            "motor_enable": 17,
            "motor_step": 18,
            "motor_dir": 27,
            "gripper_open": 22,
            "gripper_close": 23,
            "limit_switch_x": 24,
            "limit_switch_y": 25,
            "limit_switch_z": 26,
            "current_sensor": 5,
            "temperature_sensor": 6
        }

        # Rörelseregler (i mm eller steg)
        self.positions = self._load_positions()

        # Trådsäkerhet
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._current_operation = None

        # Kalibrering
        self._is_calibrated = False

        # Initiera hardware om inte simuleringsläge
        if not simulation_mode:
            self._initialze_hardware()

        logger.info(f"Robotic arm initialized in {"simulation" if simulation_mode else "hardware"} mode")
        logger.info(f"Gripper type: {self.gripper_type.value}, Max payload: {self.max_payload}g")

        def _initialize_hardware(self) -> None:
            """Initiera GPIO och motorer."""
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)

                # Konfigurera utgångspins
                for pin_name, pin_num in self.pins.items():
                    if "sensor" in pin_name or "switch" in pin_name:
                        GPIO.setup(pin_name, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                    else:
                        GPIO.setup(pin_num, GPIO.OUT)
                        GPIO.output(pin_name, GPIO.LOW)

                # Starta, övervakningstrådar
                self._start_monitoring()

                logger.info("Hardware initialzed successfully")

            except Exception as e:
                logger.error(f"Failed to initialize hardware: {e}")
                self._add_error(ArmError.COMMUNICATION_ERROR)

        def _load_positions(self) -> Dict[ArmPosition, Tuple[float, float, float]]:
            """Ladda fördefinierade positioner från konfiguration."""
            # Standardpositioner (x, y, z i mm)
            default_positions = {
                ArmPosition.HOME: (0.0, 0.0, 100.0),
                ArmPosition.BUN_DISPENSER: (150.0, 50.0, 50.0),
                ArmPosition.GRILL: (200.0, 100.0, 30.0),
                ArmPosition.FRYER: (250.0, 150.0, 40.0),
                ArmPosition.TOPPING_STATION_1: (100.0, 200.0, 20.0),
                ArmPosition.TOPPING_STATION_2: (120.0, 200.0, 20.0),
                ArmPosition.TOPPING_STATION_3: (140.0, 200.0, 20.0),
                ArmPosition.SAUCE_STATION: (180.0, 200.0, 15.0),
                ArmPosition.CONVEYOR_IN: (300.0, 50.0, 60.0),
                ArmPosition.CONVEYOR_OUT: (350.0, 50.0, 60.0),
                ArmPosition.WASTE_BIN: (400.0, 0.0, 10.0),
                ArmPosition.MAINTENANCE: (500.0, 0.0, 200.0)
            }

            # Överskriv med användarkonfiguration om finns
            user_positions = self.config.get("arm_positions", {})
            for pos_name, coords in user_positions.items():
                try:
                    psition = ArmPosition(pos_name)
                    default_positions[psition] = tuple(coords)
                except ValueError:
                    logger.warning(f"Unknown position in config: {pos_name}")
            
            return default_positions
        
        def move_to_position(self, position: ArmPosition, speed: float = 1.0) -> bool:
            """
            Flytta arm till specificerad position.

            Args:
                position: Målposition
                speed: Relativ hastighet (0.1-2.0)

            Returns:
                True om lyclad, False annars
            """
            with self._lock:
                if self._stop_event.is_set():
                    logger.warning("Arm movement stopped by emergency stop")
                    return False
                
                if self.state.status == ArmStatus.ERROR:
                    logger.error("Cannot move arm - in error state")
                    return False
                
                if position not in self.positions:
                    logger.error(f"Unknown position: {position}")
                    return False
                
                if not self.is_calibrated and position != ArmPosition.HOME:
                    logger.warning("Arm not calibrated, calibrating first...")
                    if not self.calibrate():
                        return False
                    
                logger.info(f"Moving arm from {self.state.position.value} to {position.value}")
                self.state.status = ArmStatus.MOVING

                try:
                    target_coords = self.positions[position]

                    if self.simulation_mode:
                        # Simulerad rörelse
                        time.sleep(2.0 / speed) # Simulerad fördröjning
                    else:
                        # Fysisk rörelse
                        self._physical_move(target_coords, speed)

                    self.state.position = position
                    self.state.status = ArmStatus.IDLE
                    self.state.operation_count += 1

                    logger.info(f"Arm moved succrssfully to {position.value}")
                    return True
                
                except Exception as e:
                    logger.error(f"Movement failed: {e}")
                    self.state.status = ArmStatus.ERROR
                    self._add_error(ArmError.POSITION_ERROR)
                    return False
                
            def _pysical_move(self, target_coords: Tuple[float, float, float], speed: float) -> None:
                """Utför fysisk rörelse till target_coords."""
                # Implementera stagmotor_kontroll här
                # Detta är en plasthållare - anpassa till din specifika hardware

                # Aktivera motorer
                GPIO.output(self.pins["motor_enable"], GPIO.HIGH)

                # Beräkna steg för varje axel
                # Antal 1mm = 10 steg (justera efter din konfiguration)
                steps_x = int(target_coords[0] * 10)
                steps_y  = int(target_coords[1] * 10)
                steps_z = int(target_coords[2] * 10)

                # Rörelsalgoritm (Bresenham eller liknande)
                max_steps = max(abs(steps_x), abs(steps_y), abs(steps_z))

                if max_steps > 0:
                    delay = 0.001 / speed # Justera för hastighet

                    for i in range(max_steps):
                        if self._check_collision():
                            raise Exception("Collision detected during movement")
                        
                        if i < abs(steps_x):
                            self._step_axis("x", steps_x > 0)

                        if i < abs(steps_y):
                            self._step_axis("y", steps_y > 0) 

                        if i < abs(steps_z):
                            self._step_axis("z", steps_z > 0)

                        time.sleep(delay)

                # Stänga av motorer
                GPIO.output(self.pins["motor_enable"], GPIO.LOW)

            def _step_axis(self, axis: str, direction: bool) -> None:
                """Ta ett steg i specificerad riktning,"""

                if axis == "x":
                    dir_pin = self.pins["motor_dir"]
                elif axis == "y":
                    dir_pin = self.pins["motor_dir"] # Anvämd andra pins i verkligheten
                else: # z
                    dir_pin = self.pins["motor_dir"] # Använd tredje plats i verkligheten

                # Sätt riktning
                GPIO.output(dir_pin, GPIO.HIGH if direction else GPIO.LOW)

                # Ge stegpils
                GPIO.output(self.pins["motor_step"], GPIO.HIGH)
                time.sleep(0.0001)
                GPIO.output(self.pins["motor_step"], GPIO.LOW)

            def grip(self, object_type: str = "burger_bun", force: float = 0.5) -> bool:
                """
                Greppa ett objekt.

                Args:
                    object_type: Typ av objekt att greppa
                    force: Greppkraft (0.0-1.0)

                Returns:
                    True om grepp lyckades, False annars 
                """
                with self._lock:
                    if self.state.gripper_open:
                        logger.info(f"Grippling {object_type} with force {force}")
                        self.state.status = ArmStatus.GRIPPING

                        try:
                            if self.simulation_mode:
                                time.sleep(0.5)
                                success = True
                            else:
                                success = self._physical_grip(force)

                            if success:
                                self.state.gripper:open = False

                                # Uppskatta vikt baserat på objekttyp
                                weights = {
                                    "burger_bun": 50.0,
                                    "patty": 120.0,
                                    "chees": 20.0,
                                    "lettuce": 30.0,
                                    "tomato": 40.0,
                                    "onion": 25.0,
                                    "complete_burger": 350.0
                                }
                                self.state.current_load = weights.get(object_type, 100.0)

                                logger.info(f"Successfully gripped {object_type}")
                                return True
                            else:
                                logger.warning(f"Failed to grip {object_type}")
                                self._add_error(ArmError.GRIPPER_FAILURE)
                                return False
                            
                        except Exception as e:
                            logger.error(f"Grip error: {e}")
                            self.state.status = ArmStatus.ERROR
                            return False
                        finally:
                            self.state.status = ArmStatus.IDLE
                    else:
                        logger.warning("Gripper already closed")
                        return False
                    
def _physical_grip(self, force: float) -> bool:
    """Utanför fysiskt grepp"""
    try:
        # Stäng gripper
        GPIO.output(self.pins["gripper_close"], GPIO.HIGH)
        time.sleep(force * 0.5) # Justera baserat på kraft
        GPIO.output(self.pins["gripper_close"], GPIO.LOW)

        # Varifera grepp (mec trycksensor eller strömavläsning)
        time.sleep(0.1)

        # Simulera varifiering - i verkligheten, läs sensor
        return True
    
    except Exception as e:
        logger.error(f"Physical grip failed: {e}")
        return False
    
def release(self) -> bool:
    """Släpp greppet."""
    with self._lock:
        if not self.state.gripper_open:
            logger.info("Relesing grip")
            self.state.status = ArmStatus.RELEASING

            try:
                if self.simulation_mode:
                    time.sleep(0.3)
                else:
                    self._physical_release()

                self.state.gripper_open = True
                self.state.current_load = 0.0
                self.state.status = ArmStatus.IDLE

                logger.info("Grip released successfully")
                return True
            
            except Exception as e:
                logger.error(f"Releas error: {e}")
                self.state.status = ArmStatus.ERROR
                return False
        else:
            logger.warning("Gripper already open")
            return True
        
def _physical_release(self) -> None:
    """Utför fysiskt släpp."""
    GPIO.output(self.pins["gripper_open"], GPIO.HIGH)
    time.sleep(0.3)
    GPIO.output(self.pins["gripper_open"], GPIO.LOW)

def calibrate(self) -> bool:
    """
   Kalibrera robotarmen genom att hitta nollpositioner.

   Returns:
        True om kalibrering lyckades, False annars
    """
    with self._lock:
        logger.info("Starting arm calibration")
        self.state.status = ArmStatus.CALIBRATING

        try:
            if self.simulation_mode:
                time.sleep(3.0)
                success = True
            else:
                success = self._phsical_calibrate()
            
            if success:
                self.is_calibrated = True
                self.state.position = ArmPosition.HOME
                self.state.status = ArmStatus.IDLE
                logger.info("Arm calibration successful")
                return True
            else:
                logger.error("Arm calibration failed")
                self._add_error(ArmError.CALIBRATION_ERROR)
                return False
            
        except Exception as e:
            logger.error(f"Calibation error: {e}")
            self.state.status = ArmStatus.ERROR
            return False
        
def _physical_calibrate(self) -> bool:
    """ Utför fysisk kalibrering."""
    try:
        # Kalibrera varje axel genom att flytta tills limit switch aktiveras
        axes = ["x", "y", "z"]

        for axis in axes:
            limit_pin = self.pins[f"limit_switch_{axis}"]

            # Flytta i negatic riktning tills limit switch triggars
            logger.debug(f"Calibrating {axis}-axis")

            # Sätta riktning mot nollpunkt
            GPIO.output(["motor_dir", GPIO.LOW])

            # Rörelse tills limit switch
            steps = 0
            max_steps = 10000 # Säkerhetsgräns

            while GPIO.input(limit_pin) == GPIO.HIGH and steps < max_steps:
                GPIO.output(self.pins["motor_step"], GPIO.HIGH)
                time.sleep(0.0001)
                GPIO.output(self.pins["motor_step"], GPIO.LOW)
                time.sleep(0.0001)
                steps += 1

            if steps >= max_steps:
                logger.error(f"Calibration faild for {axis}-axis: limit switch not reached")
                return False

        logger.debug("All axes calibrated")
        return True
        
    except Exception as e:
        logger.error(f"Physical calibration failed: {e}")
        return False
    
def assemble_burger(self, recipe: Dict[str, Any]) -> bool:
    """
    Assemblera en hamburger enligt recept.

    Args:
        recipe: Recept med ingredienser och ordning

    Returns:
        True om lyckades, False annars
    """
    logger.info(f"Starting burger assembly: {recipe.get("name", "Unknown")}")

    try:
        # 1. Hämta undersida av bulle
        if not self.move_to_position(ArmPosition.BUN_DISPENSER):
            return False

        if not self.grip("burger:bun"):
            return False
        
        # 2. Lägg på transportband
        if not self.move_to_position(ArmPosition.CONVEYOR_IN):
            return False
        
        if not self.release():
            False

        # 3. Hämta patty fron grillen
        if not self.move_to_position(ArmPosition.GRILL):
            return False
        
        if not self.grip("patty"):
            return False
        
        # 4. Lägg patty på bulle
        if not self.move_to_position(ArmPosition.CONVEYOR_IN):
            return False
        
        if not self.release():
            return False
        
        # 5. Lägg på toppnings i ordning
        toppings = recipe.get("toppings", [])

        for i, topping in enumerate(toppings):
            station = getattr(ArmPosition, f"TOPPING_STATION_{i+1}", ArmPosition.TOPPING_STATION_1)

            if not self.move_to_position(station):
                return False
            
            if not self.grip(topping):
                return False
            
            if not self.move_to_position(ArmPosition.CONVEYOR_IN):
                return False
            if not self.release():
                return False
            
        # 6. Lägg på sås
        if recipe.get("sauce"):
            if not self.move_to_position(ArmPosition.SAUCE_STATION):
                return False
            
            # Spacialhantering för såsdispenser
            self._disoense_sauce(recipe["sauce"])

        # 7, Hämta översidan av bulle
        if not self.move_to_position(ArmPosition.BUN_DISPENSER):
            return False
        
        if not self.grip("burger_bun"):
            return False
        
        # 8. Lägg på toppen
        if not self.move_to_position(ArmPosition.CONVEYOR_IN):
            return False
        
        if not self.release():
            return False
        
        # 9. Greppa färdig hamburger
        if not self.grip("complete_burger"):
            return False
        
        # 10. Flytta till utlämningsposition
        if not self.move_to_position(ArmPosition.CONVEYOR_OUT):
            return False
        
        if self.release():
            return False
        
        logger.info("Burger assemby completed successfully")
        return True
    
    except Exception as e:
        logger.error(f"Burger assemby failed: {e}")
        return False
    
def _dispense_sauce(self, sauce_type: str) -> None:
    """Dispensera sås (specialfunktion för vakuum-gripper)"""
    if self.gripper_type == GripperType.VACUUM:
        # Vakuumgripper kan användas för att dispensera sås
        logger.info(f"Dispensing {sauce_type} sauce")
        time.sleep(1.0) # simmulerad såsdispensering

def emergency_stop(self) -> None:
    """Nödstopp - omedelbart stoppa all rörelse."""
    with self._lock:
        logger.warning("EMERGENCY STOP ACTIVATED")
        self._stop_event.set()

        if not self.simulation_mode:
            # Stäng av alla motorer
            GPIO.output(self.pins["motor_enable"], GPIO.LOW)
            GPIO.output(self.pins["gripper_open"], GPIO.LOW)
            GPIO.output(self.pins["gripper_close"], GPIO.LOW)

        self.state.status = ArmStatus.ERROR

def resume(self) -> bool:
    """Återuppta efter nödstopp."""
    with self._lock:
        if self._stop_event.is_set():
            logger.info("Resuming from emergency stop")
            self._stop_event.clear()

            # Återgå till hemposition
            if not self.move_to_posision(ArmPosition.HOME):
                return False
            
        self.state.status = ArmStatus.IDLE
        return True
    return False

def _check_collision(self) -> bool:
    """Kontrollera kollision (simulerad eller med sensor)."""
    if self.simulation_mode:
        return False # Ingen kollision i simulering
    
    # Läs kollisionssensorer om tillgängliga
    # Platshållare - implementera med riktiga sensorer
    return False

def _check_overcurrent(self) -> bool:
    """Kontrollera överström."""
    if not self.simulation_mode:
        current_value = GPIO.input(self.pins["current_sensor"])
        # Impementera logik baserat på din strömsensor
        if current_value > 4.0: # Exempelgräns
            return True
        return False
    
def _check_temperature(self) -> bool:
    """Kontrollera motortemperatur"""
    if not self.simulation_mode:
        # Läs te,peratur (exempel med analog sensor)
        # temp_value = analog_read(self.pins["temperature_sensor"])
        # self.state.temperature = temp_value

        if self.state.temperature > self.safe_temperature:
            return True
        return False
    
def _start_monitoring(self) -> None:
    """Starta bakgrundsövervakning."""
    def monitor():
        while not self._stop_event.is_set():
            try:
                # Kolla överström
                if self._check_overcurrent():
                    logger.error("Overcurrent datected")
                    self._add_error(ArmError.OVERCURRRENT)
                    self.emergency_stop()

                # Kolla temperatur
                if self._check_temperatur():
                    logger.warning(f"High temperature: {self.state.temperature}°C")

                # Kolla för värdeminsning
                if self.state.operation_count > 10000:
                    logger.warning("Maintenance due: High operation count")
                
                time.sleep(0.1) # Övervaka 10 ggr per sekund

            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                time.sleep(1.0)

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

    def _add_error(self, error: ArmError) -> None:
        """Lägg till fel i listan."""
        if error not in self.state.errors:
            self.state.errors.append(error)
            logger.error(f"Arm error: {error.value}")

    def clear_errors(self) -> None:
        """Rena alla fel."""
        with self._lock:
            self.state.errors.clear()
            logger.info("All arm errors cleared")

    def get_status(self) -> Dict[str, Any]:
        """Hämta aktuell status."""
        with self._lock:
            return {
                "position": self.state.position.value,
                "status": self.state.value,
                "gripper_open": self.state.gripper_open,
                "current_load": self.state.current_load,
                "temperature": self.state.temperature,
                "errors": [e.value for e in self.state.errors],
                "operation_count": self.state.operation_count,
                "is_calibrated": self.is_calibrated,
                "simulation_mode": self.simulation_mode
            }
        
    def cleanup(self) -> None:
        """Städa upp resurser."""
        with self._lock:
            self._stop_event.set()

            if not self.simulation_mode:
                # Flytta till hemposition
                try:
                    self.move_to_position(ArmPosition.HOME)
                except:
                    pass

                # Stäng av GPIO
                GPIO.cleanup()
            
            logger.info("Robotic arm cleaned up")

# Enkel fabriksfunktion för at skapa arm-instans
def creat_robotic_arm(config_path: str = None, simulation: bool = False) -> RoboticArm:
    """
    Skapa en robotarm-instans

    Args:
        config_path: Sökväg till konfigurationsfil (valfri)
        simulation: Kör i simuleringsläge

    Returns:
        RoboticArm-instans
    """

    import yaml
    import os

    # Standardkonfigration
    default_config = {
        "gripper_type": "vacuum",
        "max_payload": 500.0,
        "speed_factor": 1.0,
        "safe_temperature": 60.0,
        "arm_positions": {} 
    }

    # Ladda anpassad konfiguration om finns
    config = default_config.copy()

    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                user_config = yaml.safe_load(f)
                config.update(user_config.get("robotic_arm", {}))
        except Exception as e:
            logger.warning(f"Could not load from {config_path}: {e}")
    return RoboticArm(config, simulation_mode=simulation)

# Testkod om filen körs direkt
if __name__ == "__main__":
    # Knfigurera logging
    logging.basicConfig(level=logging.INFO)

    # Testa i simuleringsläge
    print("=== Testing Robotic Arm (Simulation_mode) ===")

    arm = creat_robotic_arm(simulation=True)

    try:
        # Visa initial status
        print("Initial status:", arm.get_status())

        # Kalibrera
        print("\nCalibratig...")
        if arm.calibrate():
            print("Calibration sucessful")
        else:
            print("Calibration failed")
        
        # Test rörelse
        print("\nMoving to grill position...")
        if arm.move_to_position(ArmPosition.GRILL):
            print("Movement successful")

        # Testa grepp
        print("\nTesting grip...")
        if arm.grip("patty"):
            print("Grip sucessful")

        # Visa status efter opperationer
        print("\nFinal status:", arm.get_status())
    
    finally:
        arm.cleanup()
        print("\nTest completed")


