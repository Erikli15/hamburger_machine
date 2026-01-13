"""
Ingredienssensorhantering för hamburgermaskinen.
Övervarar nivåer på kött, bröd, grönsaker, ost, såser etc.
"""

import time
import threading
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import RPi.GPIO as GPIO # För Raspberry Pi-baserade sensorer
from ...utils.logger import get_logger

logger = get_logger(__name__)

class IngredientType(Enum):
    """Typer av ingredienser som övervakas."""
    MEAT_PATTIES = "meat_patties"
    BUNS = "buns"
    CHEESE = "cheese"
    LETTUCE = "lettuce"
    TOMATO = "tomato"
    ONION = "onion"
    PICKLES = "pickles"
    KETCHUP = "ketchup"
    MUSTARD = "mustard"
    MAYONNAISE = "mayonnaise"
    BACON = "bacon"

class SensorType(Enum):
    """Typer av sensorer som används."""
    ULTRASONIC = "ultrasonic" # För nivämatning i behållare
    INFRARED = "infared" # För närvarodetektering
    LOAD_CELL = "load_cell" # För viktmätning
    PHOTOELECTRIC = "photoelectric" # För delräkning

@dataclass
class IngredientStatus:
    """Status för en specifik ingrediens."""
    ingredient_type: IngredientType
    current_level: float # 0.0 - 100.0 (%)
    units_remaining: int # Antal eneter kvar
    is_low: bool # True om behållaren är tom
    is_empty: bool # True om behållaren är tom
    last_updated: float # Timestamp

@dataclass
class SensorConfig:
    """Konfiguration för en sensor."""
    sensor_id: str
    ingresient: IngredientType
    sensor_type: SensorType
    gpio_pin_trigger: Optional[int] = None # För ultrasoniska sensor
    gpio_pin_echo: Optional[int] = None # För ultransoniska sensorer
    gpio_pin_data: Optional[int] = None # För IR/andra digitala sensorer
    adc_channel: Optional[int] = None # För analoge sensorer
    max_capacity: int = 100 # Max antal enheter
    low_threshold: float = 20.0 # Varningsnivå i procent
    empty_threshold: float = 5.0 # Tom-nivå i procent
    calibration_factor: float = 1.0 # Kalibreringsfaktor

class InventorySensorManager:
    """
    Hantera alla ingredienssensorer i hamburgarmaskin.

    Ansvarar för att:
    1. Läsa sensordata regelbundet
    2. Uppdatera ingrediensstatus
    3. Skicka varningar vid låga nivåer
    4. Hantera sensorkalibrering
    """

    def __init__(self, config_path: str = None):
        """
        Initierar sensorhanteraren.

        Args:
            config_path: Sökväg till snesor-configurationsfil
        """
        self.snsors: Dict[str, SensorConfig] = {}
        self.status: Dict[IngredientType, IngredientStatus] = {}
        self.callbacks: List[Callable] = []

        # GPIO-inställningar för Raspberry Pi
        self.gpio_initialized = False
        self.init_gpio()

        # Ladda konfiguration
        self.load_config(config_path)

        logger.info("InventorySensorManager initierad")

    def init_gpio(self):
        """Initera GPIO för Rasparry Pi."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            self.gpio_initialized = True
            logger.debug("GPIO initierad")
        except Exception as e:
            logger.error(f"Kunde inte initiera GPIO: {e}")
            self.gpio_initialized = False

    def load_config(self, config_path: str = None):
        """
        Ladda sensor-konfiguration.
        
        I en riktig implementation skulle detta läsa från en YAML/JSON-fil.
        Här använder vi hårdkodad konfiguration som exempel
        """
        # Exempelkonfiguration i . produktion läs från fil
        self.sensors = {
            "meat_sensor_1": SensorConfig(
                sensor_id="meat_sensor_1",
                ingresient_type=IngredientType.MEAT_PATTIES,
                sensor_type=SensorType.ULTRASONIC,
                gpio_pin_trigger=17,
                gpio_pin_echo=18,
                max_capacity=50,
                low_threshold=10.0,
                empty_threshold=2.0
            ),
            "bun_sensor_1": SensorConfig(
                sensor_id="bun_sensor_1",
                ingresient_type=IngredientType.BUNS,
                sensor_type=SensorType.INFRARED,
                gpio_pin_data=23,
                max_capacity=100,
                low_threshold=15.0
            ),
            "cheese_sensor_1": SensorConfig(
                sensor_id="cheese_sensor_1",
                ingresient_type=IngredientType.CHEESE,
                sensor_type=SensorType.ULTRASONIC,
                gpio_pin_trigger=24,
                gpio_pin_echo=25,
                max_capacity=80,
                low_threshold=15.0
            ),
            # Lägg till fler sensorer här...
        }

        # Initiera status för alla ingredienstyper
        for ingredient in IngredientType:
            self.statu[ingredient] = IngredientStatus(
                ingredient_type=ingredient,
                current_level=100.0, # Börja med fulla nivåer
                units_remaining=100,
                is_low=False,
                is_empty=False,
                last_updated=time.time()
            )

        logger.info(f"Laddade {len(self.sensor)} sensorkonfigurationer")

    def start_polling(self):
        """Starta backgrundståd för att avläsa sensorer regelbundet."""
        if self.is_running:
            logger.warning("Sensoravläsning redan igång")
            return
        
        self.is_running = True
        self.polling_thread = threading.Thread(
            target=self._polling_loop,
            daemon=True,
            name="SensorPollingThread"
        )
        self.polling_thread.start()
        logger.info("Startade sensoravläsning")

    def stop_polling(self):
        """Stoppa bakgrundstråden."""
        self.is_running = False
        if self.polling_thread:
            self.polling_thread.join(timeout=2.0)
        logger.info("Stoppade sensoravläsning")

    def _polling_loop(self):
        """Huvudloop för att avläsa alla sensorer."""
        while self.is_running:
            try:
                self.read_all_sensors()
                time.sleep(self.polling_interval)
            except Exception as e:
                logger.error(f"Fel i sensoravläsningsloop: {e}")
                time.sleep(1) # Kort paus vid fel

    def read_all_sensors(self):
        """Läs alla sensorer och uppdatera status."""
        for sensor_id, sensor_config in self.sensors.items():
            try:
                self.read_sensor(sensor_id)
            except Exception as e:
                logger.error(f"Kunde inte läsa sensor {sensor_id}: {e}")

    def read_sensor(self, sensor_id: str) -> Optional[float]:
        """
        Läs en specifik sensor.

        Args:
            sensor_id: ID för sensorn att läsa

        Returns:
            Läsvärden eller None vid fel
        """
        if sensor_id not in self.sensors:
            logger.error(f"Okänd sensor: {sensor_id}")
            return None
        
        sensor_config = self.sensors[sensor_id]

        try:
            # Beronde på sensortyp, använd olika läsmetoder
            if sensor_config.sensor_type == SensorType.ULTRASONIC:
                value = self._read_ultrasonic_sensor(sensor_config)
            elif sensor_config.sensor_type == SensorType.INFRARED:
                value = self._read_infrared_sensor(sensor_config)
            elif sensor_config.sensor_type == SensorType.LOAD_CELL:
                value = self._read_load_cell_sensor(sensor_config)
            elif sensor_config.sensor_type == SensorType.PHOTOELECTRIC:
                value = self._read_photoelectric_sensor(sensor_config)
            else:
                logger.error(f"Okänt sensortyp: {sensor_config.sensor_type}")
                return None
            
            if value is not None:
                self._update_ingredient_status(sensor_config, value)

            return value
        
        except Exception as e:
            logger.error(f"Fel vid avläsning av sensor {sensor_id}: {e}")
            return None

    def _read_ultrasonic_sensor(self, config: SensorConfig) -> Optional[float]:
        """
        Läs en ultrasonisk avståndssensor (HC - SR04).

        Returns:
            Avstånd i centimeter
        """
        if not self.gpio_initialized:
            logger.error("GPIO inte initierad för ultraljudssensor")
            return None

        try:
            # Trigger-pin sänds en puls
            GPIO.setup(config.gpio_pin_trigger, GPIO.OUT)
            GPIO.setup(config.gpio_pin_echo, GPIO.IN)

            # Skicka 10µs puls
            GPIO.output(config.gpio_pin_trigger, True)
            time.sleep(0.000001) # 10µs
            GPIO.output(config.gpio_pin_trigger, False)

            # Vänta på att echo-pin blir HIGH
            timeout_start = time.time()
            while GPIO.input(config.gpio_pin_echo) == 0:
                if time.time() - timeout_start > 0.1: # 100ms timeout
                    return None

            # Mät hur långe echo förblir HIGH
            pulse_start = time.time()
            while GPIO.input(config.gpio_pin_echo) == 1:
                if time.time() - pulse_start > 0.1: # 100ms timeout
                    return None
                
            pulse_duration = time.time() - pulse_start

            # Avstånd = (tid * ljudhastighet) / 2
            # ljudhastighet = 343 m/s = 34300 cm/s
            distance = (pulse_duration * 34300) / 2

            return distance
        
        except Exception as e:
            logger.error(f"Fel vid ultraljudsavläsning: {e}")
            return None
        
    def _read_infraread_sensor(self, config: SensorConfig) -> Optional[float]:
        """
        Läs en IR-sensor för närvarodetekering.

        Returns:
            1.0 om objekt detekteras, 0.0 om inte
        """
        if not self.gpio_initialized:
            logger.error("GPIO inte intierad IR-sensor")
            return None
        
        try:
            GPIO.setup(config.gpio_pin_data, GPIO.IN)
            value = GPIO.input(config.gpio_pin_data)

            # Vissa sensor är aktiva Låga, andra aktiva höga
            # Justera baserat på din specifika sensor
            return 1.0 - float(value) # Konventra till 1.0/0.0

        except Exception as e:
            logger.error(f"Fel vid IR-avläsning: {e}")
            return None

    def _read_load_cell_sensor(self, config: SensorConfig) -> Optional[float]:
        """
        Läs en lödcell för viktmätning.

        Returns:
            Vikt i gram
        """
        # För enkelhets skull - i verkligheten skulle detta använda
        # ett ADC-biblotek eller HX711-krets
        try:
            # Simulerad läsning - ersätt med riktig implementering
            # Exempel: använd ADS1115 för ADC-läsning
            return 500.0 # Simulerad vikt
        except Exception as e:
            logger.error(f"Fel vid lödcellsavläsning: {e}")
            return None
        
    def _read_photoelectric_sensor(self, config: SensorConfig) -> Optional[float]:
        """
        Läs en fotoelektrisk sensor för delräkning.

        Returns:
            Antal delar som passerat
        """
        # Implementera basserat på din specifika sensor
        # Kan räkna pulser eller läsas digitalt
        return 1.0 # Simulerat värde
    
    def _update_ingredient_status(self, config: SensorConfig, sensor_value: float):
        """
        Uppdatera ingrediensstatus baserat på sensorns värde.

        Args:
            config: Sensorkonfiguration
            sensor_value: Senaste sensornläsningen
        """
        ingresient_type = config.ingresient_type
        current_status = self.status[ingresient_type]

        # Konvertera sensornvärde till nivåprocent
        # Denna konventering beror på din fysiska uppsättning
        level_percentage  = config.ingresient_type
        units_remaining  = self.status[ingresient_type]

        # Uppdatera status
        is_low = level_percentage <= config.low_threshold
        is_empty = level_percentage <= config.empty_threshold

        # Kontrollera om status har ändrats
        status_changed = (
            current_status.current_level != level_percentage or
            current_status.is_low != is_low or
            current_status.is_empty != is_empty
        )

        self.status[ingresient_type] = IngredientStatus(
            ingredient_type=ingresient_type,
            current_level=level_percentage,
            units_remaining=units_remaining,
            is_low=is_low,
            is_empty=is_empty,
            last_updated=time.time()
        )

        # Meddela om statusändring
        if status_changed:
            self._notify_status_change(ingresient_type, self.status[ingresient_type])

            # Logga varningar vid låga nivåer
            if is_empty:
                logger.warning(f"{ingresient_type.value}: Behållare TOM!")
            elif is_low:
                logger.warning(f"{ingresient_type.value}: Låg nivå ({level_percentage:.1f}%)")

    def _convert_to_percentage(self, config: SensorConfig, sensor_value: float) -> float:
        """
        Konventera på senornvärde till nivåprocent.

        Args:
            config: Sensorkonfiguration
            sensor_value: Rått sensornvärde

        Returns: 
            Nivå i procent (0.0 - 100.0)
        """
        # Denna implementering beror på din fysiska installation
        # och sensorernas kalibrering

        if config.sensor_type == SensorType.ULTRASONIC:
            # Anta att 0cm = full, 30cm = tom
            # Justera dessa värden baserat på dina behållares höjd
            empty_distance = 30.0 # cm när tom¨
            full_distance = 5.0 # cm när full

            # Begränsa avståndet
            distance = max(min(sensor_value, empty_distance), full_distance)

            # Konvertera till procent
            percentage = 100.0 * (empty_distance - distance) / (empty_distance - full_distance)

        elif config.sensor_type == SensorType.INFRARED:
            # Digital sensor: 1.0 = del närvarande, 0.0 = ingen del
            percentage = 100.0 if sensor_value > 0.5 else 0.0

        else:
            # För andra sensorer, använd em emlel skalning
            percentage = min(max(sensor_value, 0.0),100.0)
        
        # Applicera kalibreringsfaktor
        percentage *= config.calibration_factor

        return max(0.0, min(100.0, percentage)) # Begränsa till 0-100
    
    def _notify_status_chandge(self, ingredient_type: IngredientType, status: IngredientStatus):
        """Anropa registerade callbacks vis status"""
        for callback in self.callbacks:
            try:
                callback(ingredient_type, status)
            except Exception as e:
                logger.error(f"Fel i statusändrscallback: {e}")

    def register_callback(self, callback: Callable):
        """
        Register en callback-funktion för statusändring.

        Callback-funktionen ska ha signaturen:
        callback(ingredient_type: IngredientType, status: IngredientStatus)
        """
        self.callbacks.append(callback)
        logger.debug(f"Registrerad ny callback. Totalt: {len(self.callbacks)}")

    def get_ingredient_status(self, ingredient_type: IngredientType) -> Optional[IngredientStatus]:
        """Hämta status för en specifik ingrediens."""
        return self.status.get(ingredient_type)

    def get_all_status(self) -> List[IngredientType]:
        """Hämta status för alla ingredienser."""
        return self.status.copy()
    
    def get_low_ingredients(self) -> List[IngredientType]:
        """Hämta lista över ingredienser med låg nivå."""
        return [
            ingredient_type
            for ingredient_type, status in self.status.items()
            if status.is_empty
        ]
    
    def calibrate_sensor(self, sensor_id: str, empty_value: float = None, Full_value: float = None):
        """
        Kalibrera en sensor.

        Args:
            sensor_id: Sensor att kalibrera
            empty_value: Sensorvärde när behållaren är tom
            full_value: Sensornvärde när behållaren är full
        """
        if sensor_id not in self.sensors:
            logger.error(f"Kan inte kalibrera okänt sensor: {sensor_id}")
            return
        
        sensor_config = self.sensors[sensor_id]

        # I en riktig implementering skulle vi spara dessa kalibreringsvärden
        # och använda dem i _convert_to_percentage()
        logger.info(f"Kalibrerar sensor {sensor_id}")
        # Implementera kalibreringslogik här

    def simulate_ingredient_use(self, ingredient_type: IngredientType, units: int = 1):
        """
        Simulera att en ingredients snvänds (för restning)

        Args:
            ingredient_type: Typ av ingrediens
            units: Antal enheter som används
        """
        if ingredient_type not in self.status:
            logger.error(f"Okänt igredientstyp {ingredient_type}")
            return
        
        current_status = self.status[ingredient_type]
        new_units = max(0, current_status.units_remaining - units)

        # Hitta sensor för denna ingredientstyp
        sensor_config = None
        for sensor in self.ingredient_type.values():
            if sensor.ingredient_type == ingredient_type:
                sensor_config = sensor
                break

            if sensor_config:
                level_percentage = 100.0 * (new_units / sensor_config.max_capacity)

                self.status[ingredient_type] = IngredientStatus(
                    ingredient_type=ingredient_type,
                    current_level=level_percentage,
                    units_remaining=new_units,
                    is_low=level_percentage <= sensor_config.low_threshold,
                    is_empty=level_percentage <= sensor_config.empty_threshold,
                    last_updated=time.time()
                )

                logger.info(f"Simulerade användning: {ingredient_type.value} -{units} enheter")
                self._notify_status_chandge(ingredient_type.value, self.status[ingredient_type])

    def cleanupe(self):
        """Städa upp resurser."""
        self.stop_polling()

        if self.gpio_initialized:
            try:
                GPIO.cleanup()
                logger.debug("GPIO städa")
            except Exception as e:
                logger.error(f"Fel vid GPIO-städning: {e}")

# Hjälpfunktioner för att använda modulen
def create_sensor_manager(config_path: str = None) -> InventorySensorManager:
    """
    Skapa och konfigurera en sensorhanterare.

    Args: 
        conig_path: Valfri sökerväg till konfigurationsfil

    Returns:
        Konfigurarad InventorySensorManager
    """
    return InventorySensorManager(config_path)

if __name__ == "__main__":
    # # Testkod för att valifera sensorhanteraren
    print("Testar InventorySensorManager...")

    manager = InventorySensorManager()

    # Test: Simulera statusändringar
    def test_callback(ingredient_type: IngredientType, status: IngredientStatus):
        print(f"Callback: {ingredient_type.value} = {status.current_level:.1f}%")

    manager.register_callback(test_callback)

    # Starta avläsning
    manager.start_polling()

    # Simulera lite anvöndning
    print("\nSimulerar ingrediensanvändning...")
    time.sleep(2)
    manager.simulate_ingredient_use(IngredientType.MEAT_PATTIES, 10)
    manager.simulate_ingredient_use(IngredientType.BUNS, 5)

    # Visa status
    print("\nAktuell status:")
    for ingredient_type, stastus in manager.get_all_status().items():
        print(f" {ingredient_type.value}: {stastus.units_remaining} enheter ({stastus.current_level:.1f}%)")

        time.sleep(2)

        # Städa upp
        manager.cleanupe()
        print("\nTest klar.")


