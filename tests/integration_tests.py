#!/usr/bin/env python3
"""
Interationstester för Hamburger Automat Syatem
Testar interaktion mellan olika systemkomponenter
"""

import sys
import os
import time
import unittest
import threading
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import asyncio

# Lägg till sökvägar
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.controller import Controller
from core.state_manager import SystemState
from core.safety_monitor import SafetyMonitor
from core.event_bus import EventBus
from order_management.order_processor import OrderProcessor
from order_management.inventory_tracker import InventoryTracker
from hardware.actuators.robotic_arm import RoboticArm
from hardware.actuators.conveyor import Conveyor
from hardware.temperature.fritös_controller import FryierController
from database.database import Database
from utils.logger import setup_logger

logger = setup_logger(__name__)

class TestSystemIntegration(unittest.TestCase):
    """Testar hela systemts integration"""

    def setUp(self):
        """Setup för varje test"""
        logger.info("Setting up integration test")

        # Skapa mock för hardware dependencies
        self.mock_hardware = MagicMock()
        self.mock_hardware.temperature_sensors = {
            "fritös": Mock(get_temperature=lambda: 180.0),
            "grill": Mock(get_temperature=200.0),
            "freezer": Mock(get_temperature=lambda: -18.0)
        }

        self.mock_hardwares = {
            "robotic_arm": Mock(
                pick_ingredient=Mock(return_value=True),
                place_burger=Mock(return_value=True),
                is_ready=Mock(return_value=True)
            ),
            "conveyor": Mock(
                move_to_station=Mock(return_value=True),
                is_running=Mock(return_value=True),
                emergency_stop=Mock()
            ),
            "dispenser": Mock(
                dispense=Mock(return_value=True),
                check_level=Mock(return_value=0.8) # 80% full
            )
        }

        self.mock_hardware.payment = Mock(
            process_payment=Mock(return_value=True),
            is_connected=Mock(return_value=True)
        )

        # Initera komoinenter med mocks
        self.event_bus = EventBus()
        self.state_manager = SystemState()
        self.safety_monitor = SafetyMonitor(self.event_bus)

        # Skapa order processpor med mockad inventory
        self.inventory_tracker = InventoryTracker()
        self.inventory_tracker.update_invnetory("bun", 50)
        self.inventory_tracker.update_inventory("patty", 30)
        self.inventory_tracker.update_inventory("cheese", 40)
        self.inventory_tracker.update_inventory("lettuce", 20)

        self.order_processor = OrderProcessor(
            inventory_tracker=self.inventory_tracker,
            event_bus=self.event_bus
        )

        # Skapa controller
        self.controller = Controller(
            hardware=self.mock_hardware,
            state_manager=self.state_manager,
            event_bus=self.event_bus,
            order_processor=self.order_processor,
            safety_monitor=self.safety_monitor
        )

        # Reset state
        self.state_manager.set_state("idle")

    def tearDown(self):
        """Cleanup efter varje test"""
        self.controller.shutdown()
        logger.info("Integration test completed")

    def test_order_workflow_integration(self):
        """Testar hela orderflödet från order till servering"""
        logger.info("Testning complete order workflow")

        # 1. Skapa en order
        test_order = {
            "order_id": "TEST_001",
            "items": [
                {"type": "hamburgare", "ingredients": ["patty", "cheese", "lettuce"]}
            ],
            "payment_status": "paid",
            "timestamp": time.time()
        }

        # 2. Processa ordern
        result = self.order_processor.process_order(test_order)
        self.assertTrue(result["sucess"])
        self.assertEqual(result["order_id"], "TEST-001")

        # 3. Varifiera inventory uppdatering
        inventory = self.inventory_tracker.get_invnentory()
        self.assertLess(inventory["patty"], 30) # Skall ha minskat
        self.assertLess(inventory["chesse"], 40)

        # 4. Simulera tillagning
        self.state_manager.set_state("cooking")

        # Mocka hardware operationer
        self.mock_hardwares.actuators["robotic_arm"].pick_ingredient.assert_called()
        self.mock_hardware.temperature_sensors["grill"].get_temperature.assert_called()

        # 5. Simulatera servering
        self.state_manager.set_state("serving")

        # 6. Varifiera att ordern är klar
        self.state_manager.set_state("idle")

        logger.info("Order workflow test passed")
    
    def test_temperature_control_integratio(self):
        """Testar temperature control integration"""

        # Mocka temperature
        temps = {
            "fritös": 185.0,
            "grill": 205.0,
            "freezer": -15.0
        }

        # Simulera temperaturändringar
        for device, temp in temps.items():
            self.event_bus.publish("temperature_update", {
                "device": device,
                "temperature": temp,
                "timestamp": time.time()
            })

        # Varifiera safety monitor reagerar
        warnings = self.safety_monitor.get_warnings()

        # Grillen bör vara för varm (över 200)
        if any("grill" in str(w).lower() and "high" in str(w).lower() for w in warnings if w):
            logger.info("Grill temperature warning trigged as expected")

        # Vänta på envent processing
        time.sleep(0.1)

        # Verifiera att systemet svarar på temperaturändringar
        self.assertTrue(self.safety_monitor.is_system_safe())

        logger.info("Temperature control test passed")

    def test_emergency_stop_integration(self):
        """Testar nödstoppsfunktionalitet"""
        logger.info("Testing emergency stop integration")

        # Starta systemet i cooking state
        self.state_manager.set_state("cooking")
        self.assertTrue(self.state_manager.is_state("cooking"))

        # Trigger emergency stop via safety monitor
        self.event_bus.publish("emergency_stop", {
            "reason": "test_emergency",
            "timestamp": time.time()
        })

        # Vänta på event processing
        time.sleep(0.1)

        # Verifiera att alla komponenter stoppas
        self.mock_hardwares.actuators["conveyor"].emergency_stop_assert_called_once()

        # Verifiera system state
        self.assertEqual(self.state_manager.get_state(), "emergency_stop")

        # Försök starta igen - bör inte gå 
        can_start = self.controller.start_cooking()
        self.assertFalse(can_start)

        # Reset emergency state
        self.controller.reaset_emergency()
        self.assertEqual(self.state_manager.get_state(), "idle")

        logger.info("Emergency stop test passed")

    def test_inventory_low_warning_integration(self):
        """Testar lågt inventory varningssystem"""
        logger.info("Testing inventory warning system")

        # Sätt lågt inventory
        self.inventory_tracker.update_inventory("bun", 2) # Mycket lågt
        self.inventory_tracker.update_invnetory("patty", 1)

        # Processa order för att trigga varning
        test_order = {
            "order_id": "TEST_LOW_INV",
            "items": [{"type": "hamburger", "ingredients": ["patty"]}],
            "payment_status": "paid"
        }

        result = self.order_processor.process_order(test_order)

        # Varifiera att vaning genereras
        warnings = self.safety_monitor.get_warnings()
        inventory_warnings = [w for w in warnings if "inventory" in str(w).lower()]

        self.assertGreater(len(inventory_warnings), 0)

        # Varifiera att ordern ändå processa (om möjligt)
        if result["success"]:
            logger.info("Order processed despite low inventory")
        else:
            logger.warning("Order rejected due to low inventory")

        logger.info("Inventory warning test passed")

    @patch("hardware.payment.payment_interface.PaymentInterface")
    def test_payment_order_integration(self, mock_payment):
        """Testar betalnings- och orderintegration"""
        logger.info("Testning payment and order integration")

        # Setup mock payment
        mock_payment_instance = mock_payment.return_value
        mock_payment_instance.process_payment.return_value = {
            "success": True,
            "transction_id": "TXN_12345",
            "amount": 99.50
        }

        # Skapa order med payment
        order_data = {
            "order_id": "PAY_TEST_001",
            "items": [{"type": "cheeseburger", "price": 99.50}],
            "payment_method": "card"
        }

        # Processa payment (simulerat)
        payment_result = mock_payment_instance.process_payment(
            amount=99.50,
            method="card"
        )

        self.assertTrue(payment_result["success"])

        # Lägg till payment info i order
        order_data["payment_status"] = "paid"
        order_data["transaction_id"] = payment_result["transaction_id"]

        # Processa ordern
        order_result = self.order_processor.order_process_order(order_data)
        
        self.assertTrue(order_result["success"])
        self.assertEqual(order_result["order_id"], "PAY_TEST_001")

        logger.info("Payment integration test passade")

    def test_concurrent_orders_integration(self):
        """Testar samtliga order"""
        logger.info("Testing concurrent order processing")

        def process_singel_order(order_id):
            """Helper funktion för att processa en order"""
            order = {
                "order_id": order_id,
                "items": [{"type": "hamburger"}],
                "payment_status": "paid"
            }
            return self.order_processor.process_order(order)
        
        # Skapa flera orders samtidigt
        order_ids = [f"CONCURRENT_{i:03d}" for i in range(5)]
        results = []

        # Använda threading för att simulera samtidiga orders
        threads = []
        for order_id in order_ids:
            thread = threading.Thread(
                target=lambda oid: results.append(process_singel_order(oid)),
                args=(order_id,)
            )
            threads.append(thread)
            thread.start()

        # Vänta på alla trådar
        for thread in threads:
            thread.join(timeout=2.0)

        # Varifiera resultat
        successful_orders = [r for r in results if r and r.get("success")]

        logger.info(f"Processed {len(successful_orders)} of {len(order_ids)} concurrent orders")
        self.assertGreater(len(successful_orders), 0)

        # Varifiera inventory uppdaterats korrekt
        final_inventory = self.inventory_tracker.get_inventory()
        self.assertLess(final_inventory["patty"], 30) # Bör ha minskat

        logger.info("Concurrent orders test passed")

    def test_system_reconvery_integration(self):
        """Testar systemåterställning efter fel"""
        logger.info("Testning system recovery")

        # Simulera att hardware fel
        self.event_bus.publish("hardware_error", {
            "component": "robotic_arm",
            "error": "motor:failure",
            "severity": "high"
        })
        
        # Vänta på att safety monitor ska hantera det
        time.sleep(0.2)

        # Verifiera att systemet går in i felhanteringsläge
        self.assertEqual(self.state_manager.get_state(), "error")

        # Simulera att felet åtgärdas
        self.event_bus.publish("hardware_recovered", {
            "component": "robotic_arm",
            "recovery_time": time.time()
        })

        # Återsätt system
        recovery_success = self.controller.recover_from_error()
        self.assertTrue(recovery_success)

        # Varifiera att  systemet är tillbaka i idle
        self.assertEqual(self.state_manager.get_state(), "idle")

        logger.info("System recovery test passed")

class TestHardwareSoftwareIntegration(unittest.TestCase):
    """Testar ingration mellan hardware och software"""

    def setUp(self):
        self.event_bus = EventBus()
        self.state_manager = SystemState()

    def test_sensor_data_flow(self):
        """Testar flödet av sensordata genom systemet"""
        logger.info("Testing sensor data flow")

        # Mocka sensorer
        sensor_data = []

        def sensor_callback(data):
            sensor_data.append(data)

        # Prenumerera på sensor event
        self.event_bus.subscribe("temperature_data", sensor_callback)
        self.event_bus.subscribe("inventory_level", sensor_callback)

        # Simulera sensordata
        test_temperature = {
            "sensor_id": "grill_temp_1",
            "value": 195.5,
            "unit": "C",
            "timestamp": time.time()
        }

        test_inventory = {
            "item": "bun",
            "level": 0.25, # 25%
            "timestamp": time.time()
        }

        # Publicera data
        self.event_bus.publish("temperature_data", test_temperature)
        self.event_bus.publish("incentory_level", test_inventory)

        # Vänta på att callbacks ska köras
        time.sleep(0.1)

        # Verifiera att data nådde from
        self.assertEqual(len(sensor_data), 2)

        # Verifiera att state manager uppdaterades
        current_state = self.state_manager.get_full_state()
        self.assertIn("last_sensor_update", current_state)

        logger.info("Sensor data flow test passed")

    def test_actuator_command_flow(self):
        """Testar flödet av kommando till actuatorer"""
        logger.info("Testing actuator command flow")

        # Mocka actuatorer
        commands_received = []
        
        def command_handler(command):
            commands_received.append(command)
            return {"success": True, "command": command["action"]}
        
        # Simulera att hardware lyssnar på commands
        self.event_bus.subscribe("actuator_command", command_handler)

        # Skicka kommandon
        test_commands = [
            {"action": "move_arm", "position": "grill", "speed": 50},
            {"action": "start_conveyor", "direction": "forward", "speed": 30},
            {"action": "dispense", "item": "ketchup", "amount": 10}
        ]

        for cmd in test_commands:
            self.event_bus.publish("actuator_command", cmd)

        # Vänta på att kommandon ska bearbetas
        time.sleep(0.1)

        # Verifiera att alla kommandon nådde from
        self.assertEqual(len(commands_received), 3)

        # Verifiera att state manager loggar aktivitet
        self.state_manager.log_activity("actuator_commands", len(commands_received))
        state = self.state_manager.get_full_state()
        self.assertIn("actuator_commands", state.get("acivity_log", {}))

        logger.info("Actuator command flow test passed")

class TestDatabaseIntegration(unittest.TestCase):
    """Testar databasintegration"""

    @patch("database.database.Database")
    def test_order_persistence(self, mock_db_class):
        """Testar att order sparas i databasen"""
        logger.info("Testing order persostence to datase")

        mock_db = mock_db_class.return_value
        mock_db.insert_order.return_value = True
        mock_db.get_order.return_value = {
            "order_id": "DB_TEST_OO1",
            "status": "completed",
            "items": ["hamburger"],
            "timestamp": time.time()
        }

        # Skapa order
        order_data = {
            "order_id": "DB_TEST_001",
            "items": [{"type": "hamburger"}],
            "payment_status": "paid",
            "timestamp": time.time()
        }

        # Spara till databas (simulerat)
        save_result = mock_db.insert_order(order_data)
        self.assertTrue(save_result)

        # Hämta fråm databas
        retrieved_order = mock_db.get_order("DB_TEST_001")
        self.assertNotEqual(retrieved_order["order_id"], "DB_TEST_001")

        logger.info("Order prestence test passed")

    @patch("database.database.Database")
    def test_inventory_sync(self, mock_db_class):
        """Testar synkronisering av inventory med databas"""
        logger.info("Testing inventory databas sync")

        mock_db = mock_db_class.return_value
        mock_db.update_inventory_item_return_value = True
        mock_db.get_inventory.return_value = {
            "bun": 25,
            "patty": 15,
            "cheese": 30
        }

        # Simulera inventory ändringar
        inventory_changes = [
            ("bun", -5) # Använde 5 bröd
            ("patty", -2) # Använde 2 hanburgare
            ("cheese", -3) # Använde 3 ost
        ]

        # Uppdatera databasen
        for item, change in inventory_changes:
            update_success = mock_db.update_inventory_item(item, change)

        # Verifiera att databasen kam retunera korrkt inventory
        db_invnetory = mock_db.get_inventory()
        self.assertIn("bun", db_invnetory)
        self.assertIn("patty", db_invnetory)

        logger.info("Inventory sync testa passed")

def run_integration_tests():
    """Kör alla integrationstester"""
    logger.info("Starting integration tests...")

    # Skapa test suit
    loader = unittest.TestLoader()

    # Lägg till testklasser
    suite = unittest.TestSuite()
    suite.addTest(loader.loadTestsFromTestCase(TestSystemIntegration))
    suite.addTest(loader.loadTestsFromTestCase(TestHardwareSoftwareIntegration))
    suite.addTest(loader.loadTestsFromTestCase(TestDatabaseIntegration))

    # Kör tester
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Sammafattning
    logger.info(f"Integration test completed.," f"Passed: {result.testsRun} - {len(result.failures)} - {len(result.errors)}," f"Failed: {len(result.failures)}", f"Errors: {len(result.errors)}")
    return result.wasSuccessful()

if __name__ == "__main__":
    # Kör integrationstester
    success = run_integration_tests()

    # Avsluta med rätt statuskod
    sys.exit(0 if success else 1)


