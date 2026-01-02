"""
Huvudkontroller för Hamburgermaskinen
Samordnar alla subsystem och ansvarar för hela processflödet
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum, auto
import threading

from core.state_manager import SystemState, StateManager
from core.safety_monitor import SafetyMonitor
from core.event_bus import EventBus, EventType
from hardware.temperature.fritös_controller import FryerController
from hardware.temperature.grill_controller import GrillController
from hardware.temperature.freezer_controller import FreezerController
from hardware.actuators.robotic_arm import RoboticArm
from hardware.actuators.conveyor import Conveyor
from hardware.actuators.dispenser import Dispenser
from order_management.order_processor import OrderProcessor
from order_management.inventory_tracker import InventoryTracker
from utils.logger import setup_logger
from utils.config_lodaer import ConfigLoader

class MachineStatus(Enum):
    """Status för hela maskinen"""
    BOOTING = auto()
    READY = auto()
    PROCESSING_ORDER = auto()
    MAINTENANCE = auto()
    ERROR = auto()
    EMERGENCY_STOP = auto()

@dataclass
class SystemMetrics:
    """Systemmått och prestandadata"""
    total_orders_processed: int = 0
    avg_order_time: float = 0.0
    system_uptime: float = 0.0
    current_temperature: Dict[str, float] = None
    ingredient_levels: Dict[str, float] = None

    def __post_init__(self):
        if self.current_temperature is None:
            self.current_temperature = {}
        if self.ingredient_levels is None:
            self.ingredient_levels = {}

class HamburgermaskinController:
    """
    Huvudkontrollerklass som samordnar alla delsystem
    """

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initiera huvudkontrollern

        Arges:
            config_path: Sökväg till konfigurationsfilen
        """
        self.logger = setup_logger(__name__)
        self.config = ConfigLoader.load_config(config_path)

        # Initiera komponenter
        self.state_manager = StateManager()
        self.safety_monitor = SafetyMonitor()
        self.event_bus = EventBus()

        # Initiera hardware-kontroller
        self.fryer = FryerController()
        self.grill = GrillController()
        self.freezer = FreezerController()
        self.robotic_arm = RoboticArm()
        self.conveyor = Conveyor()
        self.dispensers = {
            "bun": Dispenser("bun"),
            "patty": Dispenser("patty"),
            "cheese": Dispenser("cheese"),
            "lettuce": Dispenser("lettuce"),
            "tomato": Dispenser("tomato"),
            "sauce": Dispenser("sauce")
        }

        # Initiera orderhantering
        self.order_processor = OrderProcessor()
        self.inventory_tracker = InventoryTracker()

        # Systemtillstånd
        self.machine_status = MachineStatus.BOOTING
        self.metrics = SystemMetrics()
        self.current_order = None
        self.order_queue = []

        # Kontrollvariabler
        self._is_running = False
        self._main_loop_task = None
        self._lock = threading.Lock()

        # Prestandavariabler
        self.start_time = time.time()

        self.logger.info("Hamburgermaskin Controller initierad")

    async def initialize(self) -> bool:
        """
        Initiera hela systemet

        Returns:
            bool: True om initieringen lyckades
        """
        self.logger.info("Startar systeminitiering...")

        try:
            # 1. Starta säkerhetsövervakning
            await self.safety_monitor.start_monitoring()

            # 2. Värm upp utrustning 
            await self._warm_up_equipment()

            # 3. Kontrollera inventering
            inventory_ok = await self._check_inventory()
            if not inventory_ok:
                self.logger.error("Lågt inventeringsnovå")
                return False
            
            # 4. Kalibrera robortarm
            await self.robotic_arm.calibrate()

            # 5. Starta event bus subscribers
            self._setup_event_handlers()

            # 6. Uppdatera systemstatus
            self.machine_status = MachineStatus.READY
            self._is_running = True

            self.logger.info("System initierat och redo")
            return True
        
        except Exception as e:
            self.logger.error(f"Initering misslyckdes: {e}")
            self.machine_status = MachineStatus.ERROR
            return False
        
    async def _warm_up_equipment(self):
        """Värm upp all utrusning till arbetstemperatur"""
        tasks = [
            self.fryer.heat_to_temperature(180), # 180°C för fritösen
            self.grill.heat_to_temperature(200), # 200°C grillen
            self.freezer.maintain_temperature(-18) # -18°C gör frysen
        ]

        await asyncio.gather(*tasks)
        self.logger.info("All utrustning uppvärmd")

    async def _check_inventory(self) -> bool:
        """Kontrollera att alla ingredienser finns tillräckligt"""
        inventory = await self.inventory_tracker.get_inventory_status()

        for item, level in inventory.items():
            if level < self.config["inventory"]["main_threshold"]:
                self.logger.warning(f"Lågt nivå för {item}: {level}%")
                await self.event_bus.publish(
                    EventType.INVENTORY_LOW,
                    {"item": item, "level": level}
                )

            # Kontrollera kritiska ingredienser
            critical_items = ["bun", "patty"]
            for item in critical_items:
                if inventory.get(item, 0) < 10: # Under 10%
                    self.logger.error(f"Kritiskt lågt nivå för {item}")
                    return False
                
                return True
            
    def _setup_event_handlers(self):
        """Ställ in event handlers för systemhändälser"""

        @self.event_bus.subscribe(EventType.ORDER_RECEIVED)
        async def handle_new_order(event_data):
            """Hantera ny order"""
            self.logger.info(f"Ny order mottagen: {event_data["order_id"]}")

            if self.machine_status == MachineStatus.READY:
                self.order_queue.append(event_data)
                await self._process_next_order()

        @self.event_bus.subscribe(EventType.SAFETY_TRIGGERED)
        async def handle_safety_event(event_data):
            """Hantera säkerhetshändelser"""
            self.logger.warning(f"Säkerhetshändelse: {event_data["type"]}")

            if event_data["type"] == "emergency_stop":
                await self.emergency_stop()

        @self.event_bus.subscribe(EventType.HARDWARE_ERROR)
        async def handle_hardware_error(event_data):
            """Hantera hardware-fel"""
            self.logger.error(f"Hardware-fel: {event_data}")
            self.machine_status = MachineStatus.ERROR

            # Försök att återsälla
            await self._recover_from_error(event_data)

    async def _process_next_order(self):
        """Berabeta nästa order i kön"""
        if not self.order_queue or self.machine_status != MachineStatus.READY:
            return
        
        while self._lock:
            self.current_order = self.order_queue.pop(0)
            self.machine_status = MachineStatus.PROCESSING_ORDER

        try:
            order_id = self.current_order["order_id"]
            self.logger.info(f"Startar bearbeting av order {order_id}")

            start_time = time.time()

            # 1. Hämta receptinformation
            recipe = await self.order_processor.get_recipe(
                self.current_order["burger_type"]
            )

            # 2. Processa varje steg i receptet
            for step in recipe["steps"]:
                await self._execute_maunfacturing_step(step)

            # 3. Slutför order
            await self._complete_order(order_id)

            # 4. Uppdatera statistik
            processing_time = time.time() - start_time
            self._update_metrics(processing_time)

            self.logger.info(f"Order {order_id} slutförd på {processing_time:.2f} sekunder")

        except Exception as e:
            self.logger.error(f"Fel vid bearbetning av order: {e}")
            await self.event_bus.publish(
                EventType.ORDER_FAILED,
                {"order_id": order_id, "error": str(e)}
            )

        finally:
            with self._lock:
                self.current_order = None
                self.machine_status = MachineStatus.READY

            # Bearbeta nästa order om det finns
            if self.order_queue:
                await self._process_next_order()

        async def _execute_manufacturing_step(self, step: Dict[str, Any]):
            """Exektera ett tillverkningssteg"""
            step_type = step["type"]

            if step_type == "grill_patty":
                await self._grill_patty(step["duration"])

            elif step_type == "fry_fries":
                await self._fry_fries(step["duration"])

            elif step_type == "dispense_ingredient":
                await self._dispense_ingredient(
                    step["ingredient"],
                    step["amount"]
                )

            elif step_type == "assemble":
                await self._assemble_burger(step["layers"])

            elif step_type == "package":
                await self._package_order(step["container_type"])

            else:
                raise ValueError(f"Okänt steg-type: {step_type}")
            
    async def _grill_patty(self, duration: int):
        """Grilla hamburgere"""
        self.logger.info(f"Grillar hamburgare i {duration} sekunder")

        # Aktivera grillen
        await self.grill.activate()

        # Vänta under grillingen
        await asyncio.sleep(duration)

        # Stäng av grillen
        await self.grill.deactivate()

    async def fry_fries(self, duration: int):
        """Fritera pommes frites"""
        self.logger.info(f"Friterar pommes i {duration} sekunder")

        # Sänk korgen i fritösen
        await self.fryer.lower_basket()

        # Vänta under friteringen
        await asyncio.sleep(duration)

        # Lyft upp korgen
        await self.fryer.lift_bssket()

        # Låt rinna av
        await asyncio.sleep(10) # 10 sekunder avrinning

    async def _dispense_ingredient(self, ingredint: str, amount: float):
        """Dispensera en ingrediens"""
        self.logger.info(f"Dispenserar {amount}g {ingredint}")

        if ingredint in self.dispensers:
            await self.dispensers[ingredint].dispense(amount)
        else:
            self.logger.error(f"Okänt ingrediens: {ingredint}")

    async def _assemble_burger(self, layers: List[Dict]):
        """Montera hamburgaren med robotarm"""
        self.logger.info(f"Monterar hamburgare")

        # Plocka upp inderdel av bulle
        await self.robotic_arm.pick_up("bun_bottom")
        await self.robotic_arm.place_on_conveyor()

        # Lägg på varje lager
        for layer in layers:
            await self.robotic_arm.pick_up(layer["item"])
            await self.robotic_arm.place_on_conveyor()

            # Applicera sås om specificerat
            if "sauce" in layer:
                await self.robotic_arm.apply_sauce(layer["sauce"])

        # Lägg på överdel av bulle
        await self.robotic_arm.pick_up("bun_top")
        await self.robotic_arm.place_on_conveyor()

        # Pressa ihop hamburgaren
        await self.robotic_arm.press_burger()

async def _package_order(self, container_type: str):
    """Packa ordern"""
    self.logger.info(f"Packar order i {container_type}")

    # Flytta hamburgare till förpackning
    await self.conveyor.move_to_packing()

    # Placera i förpackning
    await self.robotic_arm.package_in_container(container_type)

    # Lägg till pommes om ingått
    if self.current_order.get("include_fries", False):
        await self.robotic_arm.add_fries_to_package()

async def _complete_order(self, order_id: str):
    """Slutför orderprocessen"""
    # Uppdatera inventering
    await self.inventory_tracker.update_after_order(
        order_id,
        self.current_order["burger_type"]
    )

    # Uppdatera orderstatus i databas
    await self.order_processor.mark_order_completed(order_id)

def _update_metrics(self, order_time: float):
    """Uppdatera systemått"""
    self.metrics.total_orders_processed +=1

    # Beräkna rullande medeltid
    if self.metrics.total_order_time == 0:
        self.metrics.avg_order_time = order_time
    else:
        # Exponentiellt glidande medelvärde
        alpha = 0.1
        self.metrics.avg_order_time = (
            alpha * order_time +
            (1 - alpha) * self.metrics.avg_order_time
        )


    # Uppdatera uppetid
    self.self.metrics.system_uptime = time.time() - self.start_time

    # Uppdatera temperaturer
    self.metrics.current_temperature = {
        "fryer": self.fryer.get_current_temperature(),
        "grill": self.grill.get_current_temperature(),
        "freezer": self.freezer.get_current_temperature()
    }

    # Uppdatera ingrediensnivåer
    self.metrics.ingredient_levels = self.inventory_tracker.get_current_levels()

async def emergency_stop(self):
    """Nödstopp av hela systemet"""
    self.logger.critical("Utför nödstopp!")

    with self._lock:
        self.machine_status = MachineStatus.EMERGENCY_STOP

    # Stoppa aööa rörliga delar
    stop_tasks = [
        self.conveyor.emergency_stop(),
        self.robotic_arm.emergency_stop(),
        self.fryer.emergency_stop(),
        self.grill.emergency_stop()
    ]

    await asyncio.gather(*stop_tasks)

    # Töm orderkö
    self.order_queue.clear()
    self.current_order = None

    self.logger.info("System i nödstoppsläge")

async def _recover_from_error(self, error_data: Dict[str, Any]):
    """Försöka att återställa från fel"""
    self.logger.info("Försöker återställa från fel...")

    # Vänta lite
    await asyncio.sleep(5)

    try:
        # Försök att återinitera systemet
        success = await self.initialize()

        if success:
            self.logger.info("Återställning lyckades")
            await self.event_bus.publish(
                EventType.SYSTEM_RECOVERED,
                {"error": error_data}
            )
        else:
            self.logger.error("Återställning misslyckades")
            # Behöver manuell återställning

    except Exception as e:
        self.logger.error(f"Fel vid återställning: {e}")

async def shutdown(self):
    """Stänger ner systemet säkert"""
    self.logger.info("Startar säker nedstängning...")

    self._is_running = False

    # Avsluta pågånde order
    if self.current_order:
        self.logger.warning("Avbryter pågånde order...")
        await self.emergensy_stop()

    # Stäng av utrustning
    shutdown_tasks = [
        self.fryer.shutdown(),
        self.grill.shutdown(),
        self.freezer.shutdown(),
        self.robotic_arm.shutdown(),
        self.conveyor.shutdown()
    ]

    await asyncio.gather(*shutdown_tasks)

    # Stäng event bus
    await self.event_bus.shutdown()

    # Stäng aäkerhetsövervakning
    await self.safety_monitor.stop_monitoring()

    self.logger.info("System nedstämgt")


async def get_status(self) -> Dict[str, Any]:
    """Hämta aktuell systemstatus"""
    return {
        "machine_status": self.machine_status.name,
        "current_order": self.current_order,
        "queue_length": len(self.order_queue),
        "metrics": {
            "total_orders": self.metrics.total_orders_processed,
            "avg_order_time": round(self.metrics.avg_order_time, 2),
            "uptime_hours": round(self.metrics.system_uptime / 3600, 2)
        },
        "temperatures": self.metrics.current_temperature,
        "inventory": self.metrics.ingredient_levels
    }
async def run_main_loop(self):
    """Huvudkontrlloop för systemet"""
    self.logger.info("Startar huvudkontrolloop")

    while self._is_running:
        try:
            # 1. Kontrollera säkerhet
            safety_status = await self.safety_monitor.check_all_senesors()
            if not safety_status["all_ok"]:
                await self._handle_safety_issues(safety_status)

            # 2. Uppdatera inventeringsstatus
            await self._check_inventory()

            # 3. Laggstatus varje minut
            if int(time.time()) % 60 == 0: # Varje minut
                self.logger.info(f"Systemstatus: {self.get_status()}")

            # 4. Vänta innan nästa iteration
            await asyncio.sleep(1)

        except Exception as e:
            self.logger.error(f"Fel i huvudloop: {e}")
            await asyncio.sleep(5) # Vänta lite vid fel

async def _handle_safety_issues(self, safety_status: Dict[str, Any]):
    """Hantera säkerhetsproblem"""
    if safety_status.get("emergency_stop_triggered", False):
        await self.emergency_stop()

    elif safety_status.get("temperature_warning", False):
        self.logger.warning("Temperaturvarning aktiverad")
        await self.event_bus.publish(
            EventType.TEMPERATURE_WARNING,
            safety_status["temperature_data"]
        )

def add_order(self, order_data: Dict[str, Any]):
    """Lägg till en ny order i systemet"""
    with self._lock:
        self.order_queue.append(order_data)

    self.logger.info(f"Order tillagd: {order_data["order_id"]}")

    # Starta bearbetning om systemet är redo
    if self.machine_status == MachineStatus.READY:
        asyncio.create_task(self._process_next_order())

# Singleton-instans för enkel åtkomst
_controller_instance = None

def get_controller() -> HamburgermaskinController:
    """Hämta singleton-instans av kontrollern"""
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = HamburgermaskinController()
    return _controller_instance

async def main():
    """Huvudfunktion för att köra systemet"""
    controller = get_controller()

    try:
        # Initiera system
        success = await controller.initialize()
        if not success:
            logging.error("Kunde inte initiera systemet")
            return
        
        # Starta huvudloop
        main_loop_task = asyncio.create_task(controller.run_main_loop())

        # Kör tills avbrott
        await main_loop_task

    except KeyboardInterrupt:
        logging.info("Mottagen avbrottssignal")
    finally:
        # Stäng ner säkert
        await controller.shutdown()


if __name__ == "__main__":
    asyncio.run(main())



