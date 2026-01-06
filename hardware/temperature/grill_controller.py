"""
Grill Controller Module
Hanterar temperaturkontroll för hamburgargrillen
"""

import time
import threading
from enum import Enum
from typing import Optional, Callable, List, Dict
import RPi.GPIO as GPIO
from dataclasses import dataclass
from datetime import datetime

from ...utils.logger import get_logger
from ...utils.config_lodaer import ConfigLoader
from ...hardware.temperature.sensor_manager import TemperatureSensor

logger = get_logger(__name__)

class GrillState(Enum):
    """Tillstånd för grillen"""
    OFF = "off"
    HEATING = "heating"
    READY = "ready"
    COOKING = "cooking"
    ERROR = "error"
    MAINTENANCE = "maintenance"

class BurgerDoneness(Enum):
    """Stekgrad för hamnburgare"""
    RARE = "rare" # 54°C
    MEDIUM_RARE = "medium_rare" # 57°C
    MEDIUM = "medium" # 63°C
    MEDIUM_WELL = "medium_well" # 68°C 
    WELL_DONE = "well_done" # 74°C

@dataclass
class CookingProfile:
    """Profiler för olika burgartyper"""
    name: str
    target_temperature: float # Temperature i °C
    cooking_time: float # Tid i sekunder
    pressure_level: float # Trycknivå (0-1)
    flip_required: bool # Behöver vändas?
    flip_time: Optional[float] # När att vända (sekunder)

@dataclass
class GrillStatus:
    """Statusinformation för geillen"""
    state: GrillState
    current_temperature: float
    target_temperature: float
    heating_element_active: bool
    cooking_timer: Optional[float]
    burgers_on_grill: int
    last_maintenance: datetime
    error_message: Optional[str]

class GrillController:
    """Huvudklass för grillkontroll"""

    # Färdefinierad cooking profiles
    COOKING_PROFILES = {
        "standard_beef": CookingProfile(
            name="standarf Beef Burger",
            target_temperature=71.0, # USDA rekommendation
            cooking_time=240.0, # 4 minuter
            pressure_level=0.7,
            flip_required=True,
            flip_time=120.0 # Vänd efter 2 minuter 
        ),
        "premium_wagyu": CookingProfile(
            name="Premium Wagyu Burger",
            target_temperature=63.0, # Medium
            cooking_time=180.0, # 3 minuter
            pressure_level=0.5, # Lägre tryck för mör kött
            flip_required=True,
            flip_time=90.0 
        ),
        "chicken": CookingProfile(
            name="Chicken Burger",
            target_temperature=74.0, # Kyckling måste vara väl tillagad
            cooking_time=300.0, # 5 minuter
            pressure_level=0.8,
            flip_required=True,
            flip_time=150.0
        ),
        "veggie": CookingProfile(
            name="Veggie Burger",
            target_temperature=65.0,
            cooking_time=210.0, # 3.5 minuter
            pressure_level=0.6,
            flip_required=False, # Vegetaiska burgare behöver ite vändas
            flip_time=None
        )
    }

def __init__(self, config_path: str = "config.yaml"):
    """Initiera grillkontrollern"""
    self.config = ConfigLoader.load_temperature_config(config_path)["grill"]

    # GPIO pins (anpassa efter din hardware setup)
    self.HEARING_PIN = self.config["gpio_pins"]["heating_element"]
    self.TEMP_SENSOR_PIN = self.config["gpio_pins"]["temperature_sensor"]
    self.PRESSURE_PIN = self.config["gpio_pins"]["pressure_sensor"]
    self.SAFETY_PIN = self.config["gpio_pins"]["safety_relay"]

    # Konfiguratiomsparametrar
    self.MAX_TEMPERATURE = self.config["limits"]["max_temperature"]
    self.MIN_TEMPERATURE = self.config["limits"]["min_temperature"]
    self.HEATING_RATE = self.config["heating_rate_c_per_s"] # °C per sekund
    self.COOLING_RATE = self.comfig["cooling_rate_c_per_s"] # °C per sekund
    self.TEMPERATURE_TOLERANCE = self.config["temperature_tolerance"]

    # Initiala tillstånd
    self.state = GrillState.OFF
    self.current_temperature = 20.0 # Rumstemperatur som default
    self.target_temperature = 0.0
    self.heating_element_active = False
    self.cooking_start_time = None
    self.burgers_on_grill = 0
    self.current_profile: Optional[CookingProfile] = None
    self.error_message: Optional[str] = None

    # Hardware komponenter
    self.temperature_sensor = TemperatureSensor(self.TEMP_SENSOR_PIN)
    self._setup_gpio()

    # Tråd för temperaturövervakning
    self.monitoring_thread = None
    self.monitoring_active = False
    self.control_lock = threading.Lock()

    # Callbacks för händelser
    self.on_state_change: Optional[Callable] = None
    self.on_temperature_reached: Optional[Callable] = None
    self.on_cooking_complete: Optional[Callable] = None
    self.on_error: Optional[Callable] = None

    # Maintenance tracking
    self.burgers_cooked = 0
    self.last_maintenance = datetime.now()

    logger.info("GrillController initialiserad")

def _seyup_gpio(self):
    """Ställ GPIO pins"""
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.HEATING_PIN, GPIO.OUT)
        GPIO.setup(self.SAFETY_PIN, GPIO.OUT)
        GPIO.output(self.HEATING_PIN, GPIO.LOW)
        GPIO.output(self.SAFETY_PIN, GPIO.HIGH) # Safety relay ON
        logger.debug("GPIO pins konfigurerade")
    except Exception as e:
        logger.error(f"GPIO setup fel: {e}")
        raise

def start(self):
    """Starta grillkontrollern"""
    if self.state != GrillState.OFF:
        logger.warning("Grill är redan på")
        return False
    
    self.monitoring_active = True
    self.monitoring_thread = threading.Thread(
        target=self._temperature_monitor,
        daemon=True
    )
    self.monitoring_thread.start()

    self._set_state(GrillState.HEATING)
    logger.info("Grillkontroller startad")
    return True

def stop(self):
    """Stoppa grillkontrollern"""
    self.monitoring_active = False
    self._turn_off_heating()

    if self.monitoring_thread:
        self.monitoring_thread.join(timeout=2)

    self._set_state(GrillState.OFF)
    logger.info("Grillkontroller stoppad")

def set_temperature(self, temperature: float, profile_name: str = None):
    """
    Sätt måltemperature för grillen

    Args:
        temperature: Temperatur i °C
        profile_name: Optional cooking profile namn
    """
    with self.control_lock:
        # Validera temperatur
        if temperature < self.MIN_TEMPERATURE or temperature > self.MAX_TEMPERATURE:
            error_msg = f"Ogiltig temperatur: {temperature}°C. Måste vara mellan {self.MIN_TEMPERATURE}-{self.MAX_TEMPERATURE}°C"
            self._trigger_error(error_msg)
            return False
        
        self.target_temperature = temperature

        # Sätt cooking profile om angivet
        if profile_name and profile_name in self.COOKING_PROFILES:
            self.current_profile = self.COOKING_PROFILES[profile_name]
            logger.info(f"Cooking profile sett: {profile_name}")

        # Starta uppvärmning om inte redan pågor
        if self.state == GrillState.READY:
            self._set_state(GrillState.HEATING)

        logger.info(f"Måltemperatur satt till: {temperature}°C")
        return True
    
    def start_cooking(self, burger_type: str = "standard_beef", count: int = 1):
        """
        Starta cooking process

        Args:
            burger_type: Typ av burger (motsvarar cooking profile)
            count: Antal hamburgare
        """
        with self.control_lock:
            if self.state != GrillState.READY:
                error_msg = "Grillen är inte redo för cooking"
                self._trigger_error(error_msg)
                return False
            
            if count > self.config["max_burgers"]:
                error_msg = f"För många hamburger: {count}. Max: {self.config["max_burgers"]}"
                self._trigger_error(error_msg)
                return False
            
            if burger_type not in self.COOKING_PROFILES:
                error_msg = f"Okänd burger typ: {burger_type}"
                self._trigger_error(error_msg)
                return False
            
            # Sätt cooking profile
            profile = self.COOKING_PROFILES[burger_type]
            self.current_profile = profile
            self.burgers_on_grill = count
            self.cooking_start_time = time.time()

            # Justera måltemperatur baserat på antal burgare
            # Filer burgare = högre temperatur för kompensation
            temperature_adjustment = count * 0.5 # 0.5°C per extra burger
            self.target_temperature = profile.target_temperature + temperature_adjustment

            self._set_state(GrillState.COOKING)

            # Starta cooking timer
            cooking_thread = threading.Thread(
                target=self._cookong_timer,
                args=(profile.cooking_time,),
                daemon=True
            )
            cooking_thread.start()

            # Starta flip timer om behövs
            if profile.flip_required and profile.flip_time:
                flip_thread = threading.Thread(
                    target=self._flip_timer,
                    args=(profile.flip_time,),
                    daemon=True
                )
                flip_thread.start()

            logger.info(f"Cooking startad: {burger_type}, antal: {count}")
            return True
        
    def _temperature_monitor(self):
        """Huvudloop för temperaturövervakning och kontroll"""
        last_update = time.time()

        while self.monitoring_active:
            try:
                current_time = time.time()
                delta_time = current_time - last_update

                # Läs temperatur från sensor
                self._read_temperature()

                # Kontrollera temperatur och styr uppvärmning
                if self.state in [GrillState.HEATING, GrillState.COOKING, GrillState.READY]:
                    self._temperature_control(delta_time)

                # Säkerhetskontroller
                self._safety_checks()

                # Uppdatera status varje sekund
                if current_time - last_update >= 1.0:
                    self._update.status()
                    last_update = current_time
                
                time.sleep(0.1) # 100ms uppdateringsfrekvens

            except Exception as e:
                logger.error(f"Fel i temperaturövervakning: {e}")
                self._trigger_error(f"Temperaturovervakningsfel: {str(e)}")
                time.sleep(1)

    def _read_temperature(self):
        """Läs temperatur från sensor"""
        try:
            raw_temp = self.temperature_sensor.read_temperature()

            # Filtrera brus med moving avarage
            if hasattr(self, "_temp_history"):
                self._temp_history.append(raw_temp)
                if len(self._temp_history) > 5:
                    self._temp_history.pop(0)
                self.current_temperature = sum(self._temp_history) / len(self._temp_history)
            else: self._temp_history = [raw_temp]
            self.current_temperature = raw_temp

        except Exception as e:
            logger.error(f"Kunde inte läsa temperatur: {e}")
            # Använd simulering i fall av fel
            self._simulate_temperature()

    def _simulate_temperature(self):
        """Simulera temperaturändring (för testning/fallback)"""
        if self.heating_element_active:
            # Uppvärmning
            self.current_temperature += self.HEATING_RATE * 0.1 # För 100ms interval

        else:
            # Nedkyling
            self.current_temperature -= self.COOLING_RATE * 0.1

        # Begränsa till realistiska värden
        self.current_temperature = max(20.0, min(self.current_temperature, 300.0))

    def _temperature_control(self, delta_time: float):
        """PID-liknande temperaturkontroll"""
        temperature_diff = self.target_temperature - self.current_temperature

        # Om vi är inom tolerans, är vi redo
        if abs(temperature_diff) <= self.TEMPERATURE_TOLERANCE:
            if self.state == GrillState.HEATING:
                self._set_state(GrillState.READY)
                if self.on_temperature_reached:
                    self.on_temperature_reached(self.target_temperature)
                return
            
        # Beräkna värmebehov
        if temperature_diff > 0:
            # Behöver värma upp
            heat_needed = temperature_diff * self.config["pid"]["kp"]

            # Integrared del (akumulera error)
            if not hasattr(self, "_integral_error"):
                self._integral_error = 0
            self._integral_error += temperature_diff * delta_time
            heat_needed += self._itegral_error * self.config["pid"]["ki"]

            self._last_temp_diff = temperature_diff

            # Aktivera värmare om behov över tröskel
            if heat_needed > self.config["heating_threshold"]:
                self._turn_on_heating()
            else:
                self._turn_off_heating()

        else:
            # För varmt, stäng av värmare
            self._turn_off_heating()

    def _turn_on_heating(self):
        """Slå på värmarelementet"""
        if not self.heating_element_active:
            GPIO.output(self.HEATING_PIN, GPIO.HIGH)
            self.heating_element_active = True

    def _turn_off_heating(self):
        """Slå av värmarelementet"""
        if self.heating_element_active:
            GPIO.output(self.HEATING_PIN, GPIO.LOW)
            self.heating_element_active = False

    def _safety_checks(self):
        """Utför säkerhetskontroller"""
        # Övertemperaturskydd
        if self.current_temperature > self.MAX_TEMPERATURE + 10:
            self._trigger_error(f"ÖVERTEMPERATUR: {self.current_temperature}°C")
            self._emergency_shutdown()

        # Temperatursensorfel
        if self.current_temperature < -10 or self.current_temperature > 400:
            self._trigger_error(f"Ogiltig temperaturavläsning: {self.current_temperature}°C")

        # Värmarelement timeout (för lång tid på)
        if self._heating_element_active:
            if not hasattr(self, "_heating_start_time"):
                self._heating_start_time = time.time()
            elif time.time() - self._heating_start_time > self.config["max_heating_time"]:
                self._trigger_error("Värmarelement timeout")
                self._turn_off_heating()
        else:
            if hasattr(self, "_heating_start_time"):
                delattr(self, "_heating_start_time")

    def _emergency_shutdown(self):
        """Nödstopp av grillen"""
        logger.critical("NÖDSTOPP: Grillen stängs av")

        # Stäng av allt
        self._set_turn_off_heating()
        GPIO.output(self.SAFETY_PIN, GPIO.LOW) # Koppla bort ström

        # Sätt error state
        self._set_state(GrillState.ERROR)
        self.monitoring_active = False

    def _cooking_timer(self, cooking_time: float):
        """Timer för cooking process"""
        time.sleep(cooking_time)

        with self.control_lock:
            if self.state == GrillState.COOKING:
                # Cooking klar
                self.burgers_cooked += self.burgers_on_grill
                self.burgers_on_grill = 0

                logger.info(f"Cooking klar efter {cooking_time} sekunder")

                # Återgå till READY state
                self._set_state(GrillState.READY)

                # Utlös callback
                if self.on_cooking_complete:
                    self.on_cooking_complete()

    def _flip_timer(self, flip_time: float):
        """Timer för att vända hamburgare"""
        time.sleep(flip_time)

        with self.control_lock:
            if self.state == GrillState.COOKING:
                logger.info("DAGS ATT VÄNDA HAMBURGARNA")
                # Här skulle vi integerara med robotic arm för att vända burgarna
                # För mu loggar vi bara

    def _update_status(self):
        """Uppdarera statusinformation"""
        # Kontrollera om maintenance behövs
        if self.burger_cooked >= self.config["maintenance_interval"]:
            self._set_state(GrillState.MAINTENANCE)
            logger.warning(f"Maintenance behövs. Burgare tillagda: {self.burgers_cooked}")

    def _set_state(self, new_state: GrillState):
        """Ändra grillens state"""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state

            logger.info(f"Grill state ändrad: {old_state.value} -> {new_state.value}")

            # Utlös calllback
            if self.on_state_change:
                self.on_state_change(old_state, new_state)

    def _trigger_error(self, error_message: str):
        """Hantera fel"""
        self.error_message = error_message
        logger.error(f"Grill error: {error_message}")

        self._set_state(GrillState.ERROR)

        if self.on_error:
            self.on_error(error_message)

    def get_status(self) -> GrillStatus:
        """Hämta aktuell status"""
        cooking_timer = None
        if self.cooking_start_time and self.current_profile:
            elapsed = time.time() - self.cooking_start_time
            remaining = max(0, self.current_profile.cooling_time - elapsed)
            cooking_timer = remaining

            return GrillStatus(
                state=self.state, 
                current_temperature=round(self.current_temperature, 1),
                target_temperature=round(self.target_temperature, 1),
                heating_element_active=self.heating_element_active,
                cooking_timer=cooking_timer,
                burgers_on_grill=self.burger_on_grill,
                last_maintenance=self.last_maintenace,
                error_message=self.error_message
            )
        
    def reset_error(self):
        """Återställ från error state"""
        if self.state == GrillState.ERROR:
            self.error_message = None
            self._set_state(GrillState.OFF)
            logger.info("Error återställd")
            return True
        return False
    
    def perform_maintenance(self):
        """Utanför maintenance och återställ räknare"""
        if self.state == GrillState.MAINTENANCE:
            self.burger_cooked = 0
            self.last_maintenace = datetime.now()
            self._set_state(GrillState.OFF)
            logger.info("Maintenance utförd")
            return True
        return False
    
    def get_available_profiles(self) -> List[str]:
        """Hämta lista på tillgängliga cooking profiles"""
        return list(self.COOKING_PROFILES.keys())
    
    def get_profile_details(self, profile_name: str) -> Optional[Dict]:
        """Hämta detaljer för specifik profile"""
        if profile_name in self.COOKING_PROFILES:
            profile = self.COOKING_PROFILES[profile_name]
            return {
                "name": profile.name,
                "target_temperature": profile.target_temperature,
                "cooking_time": profile.cooking_time,
                "pressure_level": profile.pressure_level,
                "flip_required": profile.flip_required,
                "flip_time": profile.flip_time
            }
        return None
    
    def cleanup(self):
        """Städa upp resurser"""
        self.stop()

        try:
            GPIO.cleanup()
            logger.info("GPIO resurser rensade")
        except:
            pass

# Exempel på använding
if __name__ == "__main__":
    # Testa grillkontrollern
    grill = GrillController()

    try:
        # Starta grillem
        grill.start()

        # Sätt temperatur 
        grill.set_temperature(200.0, "standard_beef")

        # Vänta på att grillem blir redo
        import time
        time.sleep(10)

        # Starta cooking
        grill.start_cooking("standard_beef", 2)

        # Vänta på att cooking ska bli klar
        time.sleep(5)

        # Hämta satus
        status = grill.get_status()
        print(f"Grill status: {status.state.value}")
        print(f"Temperatur: {status.current_temperature}°C")

        # Stoppa grillen
        grill.stop()
    
    except KeyboardInterrupt:
        print("\nAvbrytem av användare")
    finally:
        grill.cleanup()
