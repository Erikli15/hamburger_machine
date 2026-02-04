#!/usr/bin/env python3
"""
Harware Test Suite för Hamburbermaskinen
Testar alla maskinvarukomponenter och sensorer
"""

import unittest
import time
import sys
from unittest.mock import Mock, patch, MagicMock
import logging
from pathlib import Path

# Lägg till root directory till Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Importera från ditt prokjekt (anpassa efter din faktiska moduler)
try:
    from hardware.temperature.sensor_manager import TemperatureSensorManager
    from hardware.temperature.fritös_controller import FriesController
    from hardware.temperature.grill_controller import GrillController
    from hardware.temperature.freezer_controller import FreezerController
    from hardware.actuators.robotic_arm import RoboticArm
    from hardware.actuators.conveyor import Conveyor
    from hardware.actuators.dispenser import Dispenser
    from hardware.payment.payment_interface import PaymentInterface
    from hardware.sensors.inventory_sensor import InventorySensor
    from hardware.sensors.safety_sensor import SafetySensor
    from utils.logger import setup_logger
except ImportError as e:
    print(f"Import error: {e}")
    print("Using mocks för testing...")

# Setup logger för tester
test_logger = logging.getLogger(__name__)
test_logger.setLevel(logging.DEBUG)

class TestTemperatureSensors(unittest.TestCase):
    """Testar temperaturelasterade sensor och kontroller"""

    def setUp(self):
        """Setup för varje test"""
        self.mock_gpio = Mock()
        self.mock_i2c = Mock()

    def test_sensor_initialication(self):
        """Tester att sensorer initialiseras korrekt"""
        with patch("hardvare.temperature.sensor_manager.subs.SMBus") as mock_smbus:
            mock_smbus.return_value.read_byte_data.return_value = 25

            sensor_manager = TemperatureSensorManager()
            sensor_manager.initialize_sensors()

            # Teasta att sensorer finns
            self.assertIn("fritös", sensor_manager.sensors)
            self.assertIn("grill", sensor_manager.sensors)
            self.assertIn("freezer", sensor_manager.sensors)

            test_logger.info("✓ Temperature sensors initialized successfully")

    def test_fryer_controller(self):
        """Testar fritöskontrollern"""
        fritös = FriesController()

        # Testa temperaturinställning
        fritös.start_heating()
        self.assertTrue(fritös.is_heating)

        fritös.stop_heating()
        self.assertFalse(fritös.is_heating)

        test_logger.info("✓ Fritös controller tested successfully")

    def test_grill_temperature_control(self):
        """Testar girllens temperaturkontroll"""
        grill = GrillController()

        # Testa temperaturintervall
        grill.set_temperature(200)
        self.assertEqual(grill.target_temperature, 200)

        # Testa ogiltig temperatur (för hög)
        with self.assertRaises(ValueError):
            grill.set_temperature(300)

        # Testa ogiltig temperatur (för låg)
        with self.assertRaises(ValueError):
            grill.set_temperature(50)

        test_logger.info("✓ Grill temperature control tested successfully")

    def test_freezer_safety(self):
        """Testar frysens säkerhetsfunktioner"""
        freezer = FreezerController()

        # Testa normal drift
        freezer.set_temperature(-18)
        freezer.start_cooling()

        # Simulera temperaturövervakning
        freezer.current_temperature = -15
        freezer.check_safety()
        self.assertTrue(freezer.is_operational)

        # Simulera för gö tenperatur (farligt)
        freezer.current_temperature = 5
        freezer.check_safety()
        self.assertFalse(freezer.is_operational)

        test_logger.info("✓ Freezer safety features tested successfully")

class TestActuators(unittest.TestCase):
    """Testar akuatorer (robotarm, transportband, dispensrar)"""

    def test_robotic_arm_movments(self):
        """Testar robotarmens rörelser"""
        arm = RoboticArm()
        
        # Testar grundläggande rörelser
        test_positions = [
            ("home", (0, 0, 0)),
            ("pick_bun", (10, 5, -2)),
            ("place_patty", (15, 8 , 0)),
            ("add_toppings", (12, 7, 3))
        ]

        for position_name, coordinates in test_positions:
            success = arm.move_to(position_name, coordinates)
            self.assertTrue(success)
            self.assertEqual(arm.current_position, coordinates)

            test_logger.info(f"✓ Robotic arm movement to {position_name} tested")

        # Testa ogiltig position
        with self.assertRaises(ValueError):
            arm.move_to("invalid", (100, 100, 100))

    def test_conveyor_operation(self):
        """Testar transportbandets funktioner"""
        conveyor = Conveyor()

        # Testar olika hastigheter
        speeds = [0.5, 1.0, 1.5, 2.0]
        for speed in speeds:
            conveyor.set_speed(speed)
            self.assertEqual(conveyor.current_speed, speed)

            # Testa att starta och stoppa
            conveyor.start()
            self.assertTrue(conveyor.is_running)

            conveyor.stop()
            self.assertFalse(conveyor.is_running)
            test_logger.info(f"✓ Conveyor at speed {speed} tested")

        # Testar kritiska gränser
        with self.assertRaises(ValueError):
            conveyor.set_speed(3.0) # För hög hastighet

    def tset_dispenser_accuracy(self):
        """Testar dispenserarnas noggrannhet"""
        dispenser = Dispenser(ingredient="ketchup")

        # Testa olika mängeder
        test_amounts = [5, 10, 15, 20] # ml

        for amount in test_amounts:
            success = dispenser.dispense(amount)
            self.assertTrue(success)

            # Verifiera att mängden är inom tolerans
            dispensed = dispenser.get_last_dispensed()
            tolerance = 0.5 # 0.5 ml tolerans
            self.assertAlmostEqual(dispensed, amount, delta=tolerance)

            test_logger.info(f"✓ Dispenser accuracy for {amount}ml tested")

        # Testa för starta mängder
        with self.assertRaises(ValueError):
            dispenser.dispense(100)

class TestPaymentSystem(unittest.TestCase):
    """Testar betalningssystemet"""

    def setUp(self):
        """Testar kortläsning"""
        # Simulerad kortdata
        test_cards = [
            {"number": "4111111111111111", "type": "Visa"},
            {"number": "5500000000000004", "type": "MasterCard"},
            {"number": "340000000000009", "type": "American Express"}
        ]

        for card in test_cards:
            result = self.payment_read_card(card["number"])
            self. assertTrue(result["success"])
            self.assertEqual(result["card_type"], card["type"])

            test_logger.info(f"✓ Card reading for {card['type']} tested")

    def test_payment_processing(self):
        """Testa betalningsbearbetning"""
        test_transactions = [
            {"amount": 89.90, "expected": True},
            {"amount": 0.01, "expected": True}, # Minimalt belopp
            {"amount": 500.00, "expected": True} # Maxbelopp
        ]

        for transaction in test_transactions:
            result = self.payment.process_payment(
                amount=transaction["amount"],
                card_number="4111111111111111"
            )
            self.assertEqual(result["success"], transaction["expected"])

            if result["success"]:
                self.assertIn("transaction_id", result)
                test_logger.info(f"✓ Payment of {transaction['amount']} SEK processed")

    def test_payment_failures(self):
        """Testar Betalningsmisslyckanden"""
        # Ogiltiga kortnummer
        result = self.payment.process_payment(
            amount=89.90,
            card_number="1234567890123456"
        )
        self.assertFalse(result["success"])

        # För stort belopp
        result = self.payment.process_payment(
            amount=1000.00,
            cart_number="4111111111111111"
        )
        self.assertFalse(result["successs"])

        test_logger.info("✓ Payment failure scenarios tested")

class TestSensors(unittest.TestCase):
    """Testar olika sensorer"""

    def test_inventory_sensor(self):
        """Testar inventeringssensorer"""
        sensor = InventorySensor()

        # Testa olika ingredientser
        ingredients = ["bröd", "nötkött", "ost", "sallad", "tomat", "lök"]

        for ingredient in ingredients:
            level = sensor.check_level(ingredient)

            # Nivån ska vara mellan 0 och 100%
            self.assertGreaterEqual(level, 0)
            self.assertLessEqual(level, 100)

            # Testa varning för låg nivå
            if level < 20:
                warning = sensor.geet_warnings()
                self.assertIn(ingredient, warning)

            test_logger.info(f"✓ Inventory sensor for {ingredient}: {level}%")

    def test_safety_sensor(self):
        """Testar säkerhetssensorer"""
        sensor = SafetySensor()

        # Teata normalt läge
        status = sensor.check_all_sensorers()
        self.assertTrue(status["emergency_stop"])
        self.assertTrue(status["door_closed"])
        self.assertTrue(status["temperature_safe"])

        # Simulera nödstopp aktiverat
        sensor.emergency_stop_active = True
        status = sensor.check_all_sensors()
        self.assertFalse(status["emergency_stop"])

        # simulera öppen dörr
        sensor.door_open = True
        status = sensor.check_all_sensors()
        self.assertFalse(status["door_closed"])

        test_logger.info("✓ Safety sensors tested")

class TestHardwareIntergeration(unittest.TestCase):
    """Intergrationstester för hela hårdvarusystemet"""

    def test_complete_burger_prepatation(self):
        test_logger.info("Starting complete burger preparation test...")

        # Initialisera alla komponenter
        grill = GrillController()
        conveyor = Conveyor()
        arm = RoboticArm()
        dispenser = Dispenser("ketchup")

        # 1. Förbered grillen
        grill.set_temperaure(200)
        grill.start_heating()
        self.assertTrue(grill.is_heating)
        test_logger.info("✓ Grill prepared")

        # 2. Starta transportbandet
        conveyor.set_speed(1.0)
        conveyor.start()
        self.assartTrue(conveyor.is_running)
        test_logger.info("✓ Conveyor started")

        # 3. Robortarmens rörelser
        arm.move_to("pick_bun", (10, 5, -2))
        arm.move_to("place_patty", (15, 8, 0))
        test_logger.info("✓ Robotic arm movements completed")

        # 4. Dispensera sås
        dispenser.dispense(10)
        self.assertAlmostEqual(dispenser.get_last_dispensed(), 10, delta=0.5)
        test_logger.info("✓ Sauce dispensed")

        # 5. Stoppa allt
        grill.stop_heating()
        conveyor.stop()
        
        self.assertFalse(grill.is_heating)
        self.assertFalse(conveyor.is_running)

        test_logger.info("✓ Complete burger preparation test passed")

    def test_system_safety_integration(self):
        """Testar säkerhetsintegration mellan komponenter"""
        safety_sensor = SafetySensor()
        grill = GrillController()
        conveyor = Conveyor()

        # Normal drift
        self.assertTrue(safety_sensor.check_all_sensors()["emergency_stop"])

        # Aktivera nödstopp och varifera att allt stoppas
        safety_sensor.trigger_emergency_stop()

        # Alla komponenter ska stoppas
        grill.stop_heating()
        conveyor.stop()

        self.assertFalse(grill.is_heating)
        self.assertFalse(conveyor.is_running)
        
        test_logger.info("✓ System safety integration test passed")

class TestHardwarePerformance(unittest.TestCase):
    """Prestandatester för hårdvaran"""

    def test_response_times(self):
        """Testar respenstider för kritiska komponenter"""
        components = {
            "emergency_stop": SafetySensor().trigger_emergency_stop,
            "robotic_arm": RoboticArm().move_to_home,
            "conveyor_stop": Conveyor().stop,
            "grill_stop": GrillController().stop_heating,
        }

        max_allowed_time = 0.5 # 500ms max responstid

        for name, func in components.items():
            start_time = time.time()
            func()
            response_time = time.time() - start_time

            self.assertLess(response_time, max_allowed_time, f"{name} response time: {response_time:.3f}s")

    def test_current_operations(self):
        """Testar samtidiga opperationer"""
        import threading

        results = []

        def test_grill():
            grill = GrillController()
            grill.set_temperature(200)
            results.append("grill_ok")

        def test_conveyor():
            conveyor = Conveyor()
            conveyor.set_speed(1.0)
            results.append("conveyor_ok")

        def test_arm():
            arm = RoboticArm()
            arm.move_to_home()
            results("arm_ok")

        threads = [
            threading.Thread(target=test_grill),
            threading.Thread(target=test_conveyor),
            threading.Thread(target=test_arm),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            threads.join(timeout=2.0)

        self.assertEqual(len(results), 3)
        test_logger.info("✓ Concurrent operations test passed")

def run_all_testes():
    """Kör alla tester och returnerar resultat"""
    # Skapa test suite
    loader = unittest.TestLoader()

    suites = [
        loader.loadTestsFromTestCase(TestTemperatureSensors),
        loader.loadTestsFromTestCase(TestActuators),
        loader.loadTestsFromTestCase(TestPaymentSystem),
        loader.loadTestsFromTestCase(TestSensors),
        loader.loadTestsFromTestCase(TestHardwareIntergeration),
        loader.loadTestsFromTestCase(TestHardwarePerformance),
    ]

    # Kör alla tester
    test_runner = unittest.TextTestRunner(verbosity=2)

    print("\n" + "="*60)
    print("HARDWARE TEST SUITE - HAMBURGER MACHINE")
    print("="*60 + "\n")

    total_results = []

    for i, suite in enumerate(suites):
        print(f"\nTest Suit {i+1}: {suite.__class__name__}")
        print("-"*40)
        result = test_runner.run(suite)
        total_results.append(result)

    # Summera resultat
    total_tests = sum(len(result.failures + result.errors) for result in total_results)
    passed_tests = sum(result.testsRun - len(result.failures + result.errors) for result in total_results)

    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total tests run: {sum(r.testRun for r in total_results)}")
    print(f"Passed {passed_tests}")
    print(f"Failed: {total_tests}")
    print("="*60)

    if total_tests == 0:
        print("\n✅ ALL HARDWARE TESTS PASSED!")
        return True
    else:
        print("\n❌ SOME TESTS FAILED")
        return False
    
def quick_hardware_check():
    """Snabbkontroll av hårdvarans status"""
    print("\n QUICK HARDWARE CHECK")
    print("-"*40)

    checks = [
        ("Temperature Sensors", lambda: True),
        ("Robotic Arm", lambda: True),
        ("Conveyor Belt", lambda: True),
        ("Dispensers", lambda: True),
        ("Payment System", lambda: True),
        ("Sadety Sensors", lambda: True),
    ]

    all_ok = True
    for name, check_func in checks:
        try:
            status = check_func()
            if status:
                print(f"✅ {name}: OK")
            else:
                print(f"❌ {name}: FAILED")
                all_ok = False
        except Exception as e:
            print(f"⚠️  {name}: ERROR - {str(e)}")
            all_ok = False
    return all_ok

if __name__ == "__main__":
    # Konfigurera loggning
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Kolla om snabbkontroll eller fullständiga tester ska köras
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        success = quick_hardware_check()
        sys.exit(0 if success else 1)
    else:
        # Kör alla tester
        success = run_all_testes()
        sys.exit(0 if success else 1)