"""
Ingrediensdispenser-modul för hamburgermaskinen.

Hanterar alla typer av ingredienspensrar
- Bröddispensrar (övre och under)
- Köttdispensrar (nötkött, kyckling, vegetariskt)
- Grönsaksdispensrar (sallad, tomat, lök)
- Såsdispensrar (ketchup, senap, majonäs, specialsåser)
- Ost- och tillbehörsdispensrar

Förutsätter att dispensrarna är anslutna via GPIO (Rasparry Pi)
eller via serial/Modbus-kommunikation.
"""

import time
import threading
import logging
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum
from dataclasses import dataclass

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("RPi.GPIO not avalible - running in simulation mode")

# Lokal import
from ...utils.logger import setup_logger
from ...utils.config_loader import ConfigLoader
from ...core.event_bus import EventBus, EventType

class DispenserType(Enum):
    """Typer av dispenser."""
    BREAD_UPPER = "bread_upper" # Övre brödhalva
    BREAD_LOWER = "bread_lower" # Undre brödhalva
    MEAT = "meat" # Köttprodukter
    VEGETIABLE = "vegetiable" # Grönsaker
    SOUCE = "souce" # Såser
    CHEESE = "chees" # Ost
    TOPPINGS = "toppings" # Specialtillbehöver

class DispenserStatus(Enum):
    """Status för dispensrar."""
    READY = "ready" # Redo för användning
    DISPENSING = "dipensing" # Håller på att dispensera
    JAMMED = "jammed" # Fastnat/blockerad
    EMPTY = "empty" # tom förrådsbehållare
    ERROR = "error" # Tekniskt fel
    MAINTENANCE = "maintenance" # Under underhåll
    DISABLED = "disabled" # Avstängd

@dataclass
class DispenserConfig:
    """Konfiguration för en enskild dispenser."""
    dispenser_id: str
    name: str
    dispenser_type: DispenserType
    gpio_pin: Optional[int] = None # GPIO-pin för aktivering
    modbus_address: Optional[int] = None # Modbus-adress
    dispense_time: float = 1.0 # Standarddispenseringstid (sekunder)
    portion_size: float = 1.0 # Standardportion (gram/antal)
    max_capacity: int = 100 # Max antal portioner
    current_level: int = 100 # Nuvarande nivå
    calibration_factor: float = 1.0 # Kalibreringsfaktor

class IngredientDispenser:
    """Kontrollerar enskild ingrediensdispenser. """

    def __init__(self, config: DispenserConfig):
        """
        Initierar en dispenser.

        Args:
            config: Dispenser-konfiguration
        """
        self.config = config
        self.logger = setup_logger(f"dispenser_{config.dispenser_id}")
        self.event_bus = EventBus()

        self.status = DispenserStatus.READY
        self.current_level = config.current_level
        self.is_simulated = not GPIO_AVAILABLE

        # GPIO-initiering om tillgängligt
        if not self.is_simulated and config.gpio_pin:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(config.gpio_pin, GPIO.OUT)
                GPIO.output(config.gpio_pin, GPIO.LOW)
                self.logger.info(f"GPIO pin {config.gpio_pin} initialized for disper {config.dispenser_id}")
            except Exception as e:
                self.logger.error(f"Failed to initialize GPIO: {e}")
                self.is_simulated = True

            # Lås för trådsäkerhet
            self._lock = threading.Lock()

            self.logger.info(f"Initialized {config.dispenser_type.value} dispenser {config.name}" f"ID: {config.dispenser_id}")

            def dispense(self, portion_size: Optional[float] = None) -> Tuple[bool, str]:
                """
                Dispenser en portion av ingrediensen.

                Args:
                    portion_size: Specifik portionsstorlek (None för standard)

                Returns:
                    Tulp[bool, str]: (sucess, message)
                """
                with self._lock:
                    if self.status != DispenserStatus.READY:
                        error_msg = f"Connot dispense - dispenser status: {self.status.value}"
                        self.logger.warning(error_msg)
                        return False, error_msg
                    
                    if self.current_level <= 0:
                        self.status = DispenserStatus.EMPTY
                        error_msg = f"Dispenser {self.config.dispenser_id} is empty"
                        self.logger.warning(error_msg)
                        self.event_bus.publish(
                            EventType.DISPENSER_EMPTY,
                            {"dispenser_id": self.config.dispenser_id}
                        )

                        return False, error_msg
                    
                    # Beräkna dispenseringsparameter
                    actual_portion = portion_size or self.config.potion_size
                    dispense_time = self.config.config.dispenser_time * (actual_portion / self.config.portion_size)
                    dispense_time *= self.config.calibration_factor

                    try:
                        # Uppdatera status
                        self.status = DispenserStatus.DISPENSING
                        self.logger.info(f"Dispensing {actual_portion}g from {self.config.dispenser_id}")

                        # Publicera händelse
                        self.event_bus.publish(
                            EventType.DISPENSER_START,
                            {
                                "dipenser_id": self.config.dispenser_id,
                                "portion_size": actual_portion,
                                "dispense_time": dispense_time
                            }
                        )

                        # Aktivera dispenser (GPIO eller simulering)
                        if not self.is_simulated and self.config.gpio_pin:
                            GPIO.output(self.config.gpio_pin, GPIO.HIGH)
                            time.sleep(dispense_time)
                            GPIO.output(self.config.gpio_pin, GPIO.LOW)
                        else:
                            # Simulera dispenseringsfördröjning
                            time.sleep(dispense_time)

                            # Uppdatera inventering
                            self.current_level -= 1

                            # Logga och publicera händelse
                            success_msg = f"Successfully dispensed {actual_portion}g from {self.config.dispenser_id}"
                            self.logger.info(success_msg)

                            self.event_bus.publish(
                                EventType.DESPENSER_COMPLETE,
                                {
                                    "dispenser_id": self.config.dispenser_id,
                                    "portion_size": actual_portion,
                                    "remaining_level": self.current_level
                                }
                            )

                            # Återgå till redo-status
                            self.status = DispenserStatus.READY
                            return True, success_msg
                        
                    except Exception as e:
                        error_msg = f"Error during dispensing from {self.config.dispenser_id}: {str(e)}"
                        self.logger.error(error_msg)
                        self.status = DispenserStatus.ERROR,

                        self.event_bus.publish(
                            EventType.DISPENSER_ERROR,
                            {
                                "dispenser_id": self.config.dispenser_id,
                                "error": str(e)
                            }
                        )
                        return False, error_msg
                
            def calibrate(self, excepted_output: float, actual_output: float) -> float:
                """
                Kalibrerar dispenser baserat på förväntad vs faktisk output.

                Args:
                    expected_output: Förväntad mängd (gram)
                    actual_output: Faktiskt mängd (gram)

                Returns:
                    float: Ny kalibreringsfaktor
                """
                if actual_output == 0:
                    self.logger.error("Cannot calibrate - actual output is zero")
                    return self.config.calibration_factor
                
                # Beräkna ny kalibreringsfaktor
                old_factor = self.config.calibration_factor
                self.config.calibration_factor = old_factor * (excepted_output / actual_output)

                self.logger.info(f"Calibrated {self.config.dispenser_id}: " f"old factor={self.config.calibration_factor:.3f}")

                self.event_bus.publish(
                    EventType.DISPENSER_CALIBRATED,
                    {
                        "dispenser_id": self.config.dispenser_id,
                        "old_factor": old_factor,
                        "new_factor": self.config.calibration_factor
                    }
                )

                return self.config.calibration_factor
            
        def refil(self, amount: int) -> bool:
            """
            Fyller på dispenser.

            Args:
                amount: Antal portioner att fyll på

            Returns:
                bool: True om lyckad påfyllning
            """
            with self._lock:
                if amount <= 0:
                    self.logger.warning(f"Invalid refill amount: {amount}")
                    return False
                
                old_level = self.current_level
                self.current_level = min(self.current_level + amount, self.config.max_capasity)
                added = self.current_level - old_level

                self.logger.info(f"Refilled {self.config.dispenser_id}:" f"+{added} portion ({old_level} -> {self.current_level})")

                # Om dispenser var tom, uppdatera status
                if self.status == DispenserStatus.EMPTY and self.current_level > 0:
                    self.status = DispenserStatus.READY

                # Publicera händelse
                self.event_bus.publish(
                    EventType.REFILLED,
                        {
                            "dispenser_id": self.config.dispenser_id,
                            "amount_added": added,
                            "old_level": old_level,
                            "new_level": self.current_level
                        }
                )

                return True
            
        def get_status(self) -> Dict:
            """
            Hämtear aktuell status för dispenser.

            Returns:
                Dict: Statusinformation
            """
            return {
                "dispenser_id": self.config.dispenser_id,
                "name": self.config.name,
                "type": self.config.dispenser_type_id,
                "status": self.status.value,
                "current_level": self.current_level,
                "max_capacity": self.config.max_capacity,
                "portion_size": self.config.portion_size,
                "calibration_factor": self.config.calibration_factor,
                "is_simulated": self.is_simulated,
                "gpio_pin": self.config.gpio_pin
            }
        
        def set_status(self, new_status: DispenserStatus) -> bool:
            """
           Manuellt ändra dispenser-status.

           Arga:
                new_status: Ny status

            Returns:
                bool: True om status ändrad
            """
            with self._lock:
                old_status = self.status
                self.status = new_status

                self.logger.info(f"Status change for {self.config.dispenser_id}:" f"{old_status.value} -> {new_status.value}")

                self.event_bus.publish(
                    EventType.DISPENSER_STATUS_CHANGED,
                    { 
                        "dispenser_id": self.config.dispenser_id,
                        "old_status": old_status.value,
                        "new_status": new_status.value
                    }
                )

                return True
            
        def cleanup(self):
            """Städar upp resurser (GPIO, etc.)."""
            if not self.is_simulated and self.config.gpio_pin:
                try:
                    GPIO.output(self.config.gpio_pin, GPIO.LOW)
                    GPIO.cleanup(self.config.gpio_pin)
                    self.logger.info(f"Cleand up GPIO pin {self.config.gpio_pin}")
                except:
                    pass

class DispenserManager:
    """Hantera alla ingredienspensrar i systemet."""

    def __init__(self, config_file: str = "config/dispensers.yaml"):
        """
        Initierar dispenser-managern.

        Args:
            config_file: Sökväg till konfigurationsfil
        """
        self.logger = setup_logger("dispenser_manager")
        self.event_bus = EventBus()

        self.dispensers: Dict[str, IngredientDispenser] = {}
        self.dispensers_by_type: Dict[DispenserType, List[IngredientDispenser]] = {
            dtype: [] for dtype in DispenserType
        }

        # Ladda konfiguration
        self.config_loader = ConfigLoader()
        self.config_file = config_file

        self._load_configuration()

        self.logger.info(f"Dispenser manager initialized with {len(self.dispensers)} dispensers")

    def _load_configuration(self):
        """Laddar dispenser-konfiguration från fil."""
        try:
            config_data = self.config_loader.load_yaml(self.config_file)

            for dispenser_config in config_data.get("dispensers", []):
                try:
                    # Skapa DispenserConfig objekt
                    config_obj = DispenserConfig(
                        dispenser_id=dispenser_config["id"],
                        name=dispenser_config["name"],
                        dispenser_type=DispenserType(dispenser_config["type"]),
                        gpio_pin=dispenser_config.get("gpio_pin"),
                        modbus_address=dispenser_config.get("modbus_address"),
                        dispense_time=dispenser_config.get("dispense_time", 1.0),
                        portion_size=dispenser_config.get("portion_size", 1.0),
                        max_capacity=dispenser_config.get("max_capacity", 100),
                        current_level=dispenser_config.get("current_level", 100),
                        calibration_factor=dispenser_config.get("calibration_factor", 1.0)
                    )

                    # Skapa dipenser
                    dispenser = IngredientDispenser(config_obj)

                    # Lägg till i registren
                    self.dispensers[config_obj.dispenser_id] = dispenser
                    self.dispensers_by_type[config_obj.dispenser_type].append(dispenser)

                except KeyError as e:
                    self.logger.error(f"Missing required config faild for dispenser: {e}")
                except ValueError as e:
                    self.logger.error(f"Invalid config value for dispenser: {e}")

                self.logger.info(f"Loaded configuration for {len(self.dispensers)} dispensers")

        except FileNotFoundError:
            self.logger.warning(f"Config file {self.config_file} not found, using defaults")
            self._create_default_dispensers()
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            self._crate_default_dispensers()

    def _create_default_dispensers(self):
        """Skapa standarddispenserar för testning."""
        default_dispensers = [
            DispenserConfig(
                dispenser_id="bread_upper_1",
                name="Övre Bröd",
                dispenser_type=DispenserType.BREAD_UPPER,
                gpio_pin=17,
                dispense_time=0.5,
                portion_size=1
            ),
            DispenserConfig(
                dispenser_id="bread_lower_1",
                name="Undre Bröd",
                dispenser_type=DispenserType.BREAD_LOWER,
                gpio_pin=27,
                dispense_time=0.5,
                portion_size=1
            ),
            DispenserConfig(
                dispenser_id="meat_1",
                name="nötkött",
                dispenser_type=DispenserType.MEAT,
                gpio_pin=22,
                dispense_time=2.0,
                portion_size=120
            ),
            DispenserConfig(
                dispenser_id="sauce_ketchup",
                name="Ketchupe",
                dispenser_type=DispenserType.SAUCE,
                gpio_pin=23,
                dispense_time=1.0,
                portion_size=20
            )
        ]

        for config in default_dispensers:
            dispenser = IngredientDispenser(config)
            self.dispensers[config.dispenser_id] = dispenser
            self.dispensers_by_type[config.dispenser_type].append(dispenser)
        
        self.logger.info("Created 4 default dispensers for testing")

    def dispenser_ingredients(self, order: Dict) -> Dict[str, Tuple[bool, str]]:
        """
        Dispenserar alla ingredienser för en order.

        Args:
            order: Order med ingredienslista

        Returns:
            Dict[str, Tulpe[bool, str]]: Result per dispenser
        """
        results = {}

        try: 
            ingredients = order.get("ingredients", [])

            for ingredient in ingredients:
                ingredient_type = ingredient.get("type")
                dispenser_id = ingredient.get("dispenser_id")
                portion_size = ingredient.get("portion_size")

                # Hitta rätt dispemser
                dispenser = None

                if dispenser_id and dispenser_id in self.dispensers:
                    dispenser = self.dispensers[dispenser_id]
                elif ingredient_type:
                    # Hitta först ledig dispenser av rätt typ
                    for d in self.dispensers_by_type.get(DispenserType(ingredient_type), []):
                        if d.status == DispenserStatus.READY:
                            dispenser = d
                            break
                if dispenser:
                    success, message = dispenser.dispense(portion_size)
                    results[dispenser.config.dispenser_id] = (success, message)

                if not success:
                    self.logger.error(f"Failed to dispense {ingredient_type}: {message}")
                else:
                    error_msg = f"No available dispenser for {ingredient_type}"
                    results[ingredient_type] = (False, error_msg)
                    self.logger.error(error_msg)

            # Publicera händels
            self.event_bus.publish(
                EventType.ORDER_DISPENSED,
                {
                    "order_id": order.get("order_id"),
                    "results": results
                }
            )
        except Exception as e:
            self.logger.error(f"Error dispensing order {order.get("order_id")}: {e}")
            results["system_error"] = (False, str(e))

        return results
    
    def refill_dispenser(self, dispenser_id: str, amount: int) -> bool:
        """
        Fyller på en specifik despenser.

        Args:
            dispenser_id: ID för dispenser
            amount: Antal portioner att fylla på

        Returns:
            bool: True om lyckad
        """
        if dispenser_id not in self.dispensers:
            self.logger.error(f"Dispenser {dispenser_id} not found")
            return False
        
        return self.dispensers[dispenser_id].refill(amount)
    
    def refill_all_empty(self) -> Dict[str, bool]:
        """
        Fyller på alla tomma dispenserar med standardmängd.

        Returns:
            Dict[str, bool]: Result per dispenser
        """
        results =  {}

        for dispenser_id, dispenser in self.dispensers.items():
            if dispenser.current_level == 0:
                results[dispenser_id] = dispenser.refill(50) # Standardpåfyllning

        self.logger.info(f"Refilled {sum(results.values())} empty disponsers")
        return results
    
    def get_all_status(self) -> Dict:
        """
        Hämtar status för alla dispenser.

        Returns:
            Dict: Status för alla dispensrar
        """
        return {
            dispenser_id: dispenser.get_status()
            for dispenser_id, dispenser in self.dispensers.items()
        }
    
    def get_available_dispensers(self, dispenser_type: Optional[DispenserType] = None) -> List[str]:
        """
        Hämtar alla lediga dispenser (av valfri typ).

        Args:
            dispenser_type: Valfri dispensertyp att filtrera på

        Returns:
            List[str]: Lista med dispenser-ID:n
        """
        available = []
            
        for dispenser_id, dispenser in self.dispensers.items():
            if dispenser.status == DispenserStatus.READY:
                if dispenser_type is None or dispenser.config.dispenser_type == dispenser_type:
                    available.append(dispenser_id)
            
        return available
    
    def calibrate_dispenser(self, dispenser_id: str, excepted_output: float, actual_output: float) -> Optional[float]:
        """
        Kalibrerar en dispenser.

        Args:
            dispenser_id: ID för dispenser
            excepted_output: Förväntad output
            actual_output: Faktisk output

        Returns:
            Optional[float]: Ny kalibreringsfaktor, None om misslyckad
        """
        if dispenser_id not in self.dispensers:
            self.logger.error(f"Dispenser {dispenser_id} not found")
            return None
        return self.dispensers[dispenser_id].calibrate(excepted_output, actual_output)
    
    def run_maintenance_check(self) -> Dict[str, str]:
        """
        Kör underhållskontroll på alla dispenser

        Returns:
            Dict[str, str]: Underhållsstatus per dispenser
        """
        maintenance_results = {}

        for dispenser_id, dispenser in self.dispensers.items():
            # Kontrollera olika problem
            if dispenser.current_level <= 5:
                maintenance_results[dispenser_id] = "CRITICAL - Vary low level"
            elif dispenser.current_level <= 20:
                maintenance_results[dispenser_id] = "WARNING - Low level"
            elif dispenser.status == DispenserStatus.JAMMED:
                maintenance_results[dispenser_id] = "ERROR - Jammed, needs manual int ervention"
            elif dispenser.status == DispenserStatus.ERROR:
                maintenance_results[dispenser_id] = "ERROR - Technical issue"
            elif dispenser.config.calibration_factor < 0.8 or dispenser.config.calibration_factor > 1.2:
                maintenance_results[dispenser_id] = "WARNING - Needs calibration"
            else:
                maintenance_results[dispenser_id] = "OK"

        # Publicera underhållshändelse
        self.event_bus.publish(
            EventType.MAINTENANCE_CHECK,
            {
                "component": "dispensers",
                "result": maintenance_results
            }
        )

        return maintenance_results
    
    def emergency_stop_all(self):
        """Stoppar alla dispenserar omedelbart (nödstopp)."""
        self.logger.warning("EMERGENCY STOP - Stopping all dispensers")

        for dispenser_id, dispenser in self.dispensers.items():
            if dispenser.status == DispenserStatus.DISPENSING:
                # Stoppa GPIO-utgång om akttiv
                if not dispenser.is_simulated and dispenser.config.gpio_pin:
                    try:
                        GPIO.output(dispenser.config.gpio_pin, GPIO.LOW)
                    except:
                        pass

                dispenser.status = DispenserStatus.DISABLED

            self.event_bus.publish(
                EventType.EMERGENCY_STOP,
                {"component": "all_dispensers"}
            )

    def cleanup_all(self):
        """Städar upp all dispenser."""
        self.logger.info("Cleaning up all dispensers")

        for dispenser in self.dispensers.values():
            dispenser.cleanup()

        if not GPIO_AVAILABLE:
            try:
                GPIO.cleanup()
            except:
                pass

# Testfunktioner
def test_dispenser():
    """Testfunktion för att varifiera dispenser-funktionalitet."""
    print("=== Testing Ingredient Dispenser ===")

    # Skapa testkonfig
    config = DispenserConfig(
        dispenser_id="test_dispenser_1",
        name="Test Dispenser",
        dispenser_type=DispenserType.SOUCE,
        gpio_pin=17,
        portion_size=20,
        dispense_time=0.5
    )

    # Skapa och testa dispenser
    dispenser = IngredientDispenser(config)

    print(f"Created dispenser: {dispenser.get_status()}")

    # Testa dispenser
    success, message = dispenser.dispense()
    print(f"Dispense result: {success} - {message}")

    print(f"After dispense status {dispenser.get_status()}")

    # Testa kalibrering
    new_factor = dispenser.calibrate(excepted_output=20, actual_output=18)
    print(f"Calibrated factor: {new_factor:.3f}")

    # Städda upp
    dispenser.cleanup()
    print("Test completed successfully!")

def test_dispenser_manager():
    """Testfunktion för dispenserManager."""
    print("\n=== Testing dispenser Manager ===")

    manager = DispenserManager()

    # Visa alla dispensrar
    status = manager.get_all_status()
    print(f"Total dispensers: {len(status)}")

    # Visa lediga dispanser
    available = manager.get_available_dispensers()
    print(f"Available dispensers: {available}")

    # Testorder
    test_order = {
        "order_id": "test_order_01",
        "ingredients": [
            {"type": "bread_lower", "portion_size": 1},
            {"type": "meat", "portion_size": 120},
            {"type": "sauce", "portion_size": 20}
        ]
    }

    # Dispensera ingredienser
    results = manager.dispenser_ingredients(test_order)
    print(f"Dispense results: {results}")

    # Kör underhållskontroll
    maintenance = manager.run_maintenance_check()
    print(f"Maintenance check: {maintenance}")

    # Städda upp
    manager.cleanup_all()
    print("Dispenser manager test completed!")

if __name__ == "__main__":
    # Kör tester om filen körs direkt
    print("Running dispenser module tests...")
    try:
        test_dispenser()
        test_dispenser_manager()
        print("\nAll test passed!")
    except Exception as e:
        print(f"\nTest failed with error: {e}")







