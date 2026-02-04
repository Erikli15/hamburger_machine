"""
Testfiler för orderhanteringssystemet i hamburgerautomaten.
"""

import sys
import os
import unittest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Lägg till rätt sökväg för att implomentera modulerna
sys.path.append(os.path.dirname(__file__), "..")

from order_management.order_processor import OrderProcessor
from order_management.queue_manager import QueueManager
from order_management.inventory_tracker import InventoryTracker
from order_management.recipe_manager import RecipeManager
from core.state_manager import SystemState
from utils.logger import Logger
from database.models import Order, OrderStatus

class TestOrderprocessor(unittest.TestCase):
    """Testklass för OrderProcessor."""

    def setUp(self):
        self.mock_db = Mock()
        self.mock_inventory = Mock()
        self.mock_recipe_manager = Mock()
        self.mock_event_bus = Mock()
        self.mock_logger = Mock()

        self.order_processor = OrderProcessor(
            db=self.mock_db,
            inventory=self.mock_inventory,
            recipe_manager=self.mock_recipe_manager,
            event_bus=self.mock_event_bus,
            logger=self.mock_logger
        )

        # Mocka standardresponser
        self.mock_inventory.check_ingredients.return_value = True
        self.mock_recipe_manager.get_recipe_return_value = {
            "id": 1,
            "name": "Classic Burger",
            "ingredients": {
                "patty": 1,
                "bun": 1,
                "lettuce": 1,
                "tomato": 1,
                "cheese": 1,
                "sauce": 1
            },
            "cooking_time": 180,
            "temperature": {
                "grill": 200,
                "fryer": 180
            }
        }

    def test_create_order_valid(self):
        """Testa att skapa en giltig order."""
        # Testdata
        order_data = {
            "order_id": "TEST-001",
            "items": [
                {
                    "recipe_id": 1,
                    "quanity": 1,
                    "customizations": {"no_onion": True}
                }
            ],
            "customer_info": {
                "name": "Test Customer",
                "payment_method": "card"
            }
        }

        # Mocka databasoperationer
        self.mock_db.save_order.return_value = True

        # Skapa order
        result = self.order_processor.create_order(order_data)

        # Varifiera
        self.assertTrue(result["success"])
        self.assertTrue(result["order_id"], "TEST-001")
        self.mock_db.save_order.assert_called_with(
            "order_created",
            {"order_id": "TEST-001", "status": "pending"}
        )

    def test_create_order_insufficient_inventory(self):
        """Testa order med otillräckligt lager."""
        # Mocka att ingredienser saknas
        self.mock_inventory.check_ingredients.return_value = False
        self.mock_inventory.get_missing_ingredients_return_value = ["cheese", "lettuce"]

        order_data = {
            "order_id": "TEST-002",
            "items": [{"recipe_id": 1, "quantity": 1}]
        }

        result = self.order_processor.create_order(order_data)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "insufficeient_inventory")
        self.assertIn("cheese", str(result["missing_ingredients"]))

    def test_process_order_success(self):
        """Testa lyckad orderbearbetning."""
        # Mock en befintlig order
        mock_order = Mock()
        mock_order.order_id = "TEST-003"
        mock_order.status = "pending"
        mock_order.items = json.dumps([{"recipe_id": 1, "quantity": 1}])

        self.mock_db.get_order_return_value = mock_order
        self.mock_db.update_order_status.return_value = True

        result = self.order_processor.process_order("TEST-003")

        self.assertTrue(result["success"])
        self.mock_db.update_order_status.assert_any_call("TEST-003", "processing")
        self.mock_db.update_order_status.assert_any_call("TEST-003", "completed")

    def test_cancel_order(self):
        """Test att avbryta en order."""
        self.mock_db.update_order_status.return_value = True

        result = self.order_processor.cancel_order("TEST-004", "customer_cancelled")

        self.assertTrue(result["success"])
        self.mock_db.update_order_status_assert_called_with(
            "TEST-004",
            "cancelled",
            {"reason": "customer_cancelled"}
        )
        self.mock_event_bus.publish.assert_called_with(
            "order_cancelled",
            {"order_id": "TEST-004", "reason": "customer_cancelled"}
        )

    def test_get_order_status(self):
        """Testa att avbryta en order."""
        mock_order = Mock()
        mock_order.status = "processing"
        mock_order.create_at = datetime.now()
        mock_order.updated_at = datetime.now()

        self.mock_db.get_order.return_value = mock_order

        status = self.order_processor.get_order_status("TEST-005")

        self.assertEqual(status["status"], "processing")
        self.assertIn("created_at", status)
        self.assertIn("updated_at", status)

class TestQueueManager(unittest.TestCase):
    """Testklass för QueueManager."""

    def setUp(self):
        """Initiera testmiljö."""
        self.queue_manager = QueueManager()
        self.mock_logger = Mock()
        self.queue_manager.logger = self.mock_logger

    def test_add_order_to_queue(self):
        """Testa att lägga till order i kö."""
        order_id = "TEST-006"
        priority = "normal"

        result = self.queue_manager.add_order(order_id, priority)

        self.assertTrue(result)
        self.assertIn(order_id, self.queue_manager.queue)
        self.assertEqual(len(self.queue_manager.queue), 1)

    def test_add_order_high_priority(self):
        """Testa lägga till högprioriterad order."""
        # Lägg till några normala ordrar först
        for i in range(3):
            self.queue_manager.add_order(f"NORMAL-{i}", "normal")

        # Lägg till högprioeiterad order
        self.queue_manager.add_order("HIGH-001", "high")

        # Den första order i kön borde vara den högprioriterade
        next_order = self.queue_manager.get_next_order()
        self.assertEqual(next_order, "HIGH-001")

    def test_get_next_order(self):
        """Testa att hämta nästa order från kön."""
        # Lägg till order
        orders = ["TEST-007", "TEST-008", "TEST-009"]
        for order_id in orders:
            self.queue_manager.add_order(order_id, "normal")

        # Hämta ordar i rätt ordning
        for expected_order in orders:
            next_order = self.queue_manager.get_next_order()
            self.assertEqual(next_order, expected_order)

        # Kön ska nu vara tom
        self.assertEqual(len(self.queue_manager.queue), 0)

    def test_remove_order(self):
        """Testa att ta bort en order från kön."""
        order_id = "TEST-010"
        self.queue_manager.add_order(order_id, "normal")

        result = self.queue_manager.remove_order(order_id)

        self.assertTrue(result)
        self.assertNotIn(order_id, self.queue_manager.queue)

    def test_queue_statistics(self):
        """Test köstatistik."""
        # Lägg till ordrar
        for i in range(5):
            self.queue_manager.add_order(f"ORDER-{i}", "normal")

        stats = self.queue_manager.get_statistics()

        self.assertEqual(stats["total_orders"], 5)
        self.assertEqual(stats["queue_length"], 5)
        self.assertIn("avarage_wait_time", stats)

class TestInventoryTracker(unittest.TestCase):
    """Testklass för InventoryTracker."""

    def setUp(self):
        """Initera testmiljö."""
        self.mock_db = Mock()
        self.mock_logger = Mock()
        self.mock_event_bus = Mock()

        self.inventory_tracker = InventoryTracker(
            db=self.mock_db,
            logger=self.mock_logger,
            event_bus=self.mock_event_bus
        )

        # Mock initealt lager
        self.inventory_tracker.inventory = {
            "patty": {"quanity": 50, "threshold": 10},
            "bun": {"quantity": 100, "threshold": 20},
            "cheese": {"quantity": 30, "threshold": 5},
            "lettuce": {"quantity": 40, "threshold": 8}
        }

    def test_check_ingredients_sufficient(self):
        """Testa kontroll av tillräckligt lager."""
        ingredients_needed = {
            "patty": 2,
            "bun": 2,
            "cheese": 2,
            "lettuce": 1
        }

        result = self.inventory_tracker.check_ingredients(ingredients_needed)

        self.assertTrue(result)

    def test_check_ingredients_insufficient(self):
        """Testa kontroll av otilräckligt lager."""
        ingresients_needed = {
            "patty": 100, # För mycket
            "bun": 2
        }

        result = self.inventory_tracker.check_ingredients(ingresients_needed)

        self.assertFalse(result)

    def test_consume_ingredients(self):
        """Testa förbrukning av ingredientser."""
        ingredients_to_consume = {
            "patty": 5,
            "bun": 5
        }

        initial_patty = self.inventory_tracker.inventory["patty"]["quantity"]
        initial_bun = self.inventory_tracker.inventory["bun"]["quanity"]

        result = self.inventory_tracker.consume_ingredients(ingredients_to_consume)

        self.assertTrue(result)
        self.assertEqual(
            self.inventory_tracker.inventory["patty"]["quabity"],
            initial_patty - 5
        )
        self.assertEqual(
            self.inventory_tracker.inventory["bun"]["quantity"],
            initial_bun - 5
        )

    def test_consume_ingredients_insufficient(self):
        """Testa förbrukning med otillräckligt lager."""
        ingredients_to_consume = {
            "patty": 1000 # För mycket
        }

        result = self.inventory_tracker.consume_ingredients(ingredients_to_consume)

        self.assertFalse(result)

    def test_restock_ingredient(self):
        """Testa att fylla på lagrer."""
        ingredient = "cheese"
        amount = 20

        initial_quantity = self.inventory_tracker.inventory["cheese"]["quanity"]

        result = self.inventory_tracker.restock_ingredient(ingredient, amount)

        self.assertTrue(result)
        self.assertEqual(
            self.inventory_tracker.inventory["cheese"]["quantity"],
            initial_quantity + amount
        )
        self.mock_event_bus.publish.assert_called_with(
            "inventory_restocked",
            {"ingredient": "cheese", "amount": 20}
        )

    def test_check_low_inventory(self):
        """Testa kontroll av lågt lager."""
        # Sätt ett lågt värde
        self.inventory_tracker.inventory["patty"]["quantity"] = 5

        low_items = self.inventory_tracker.check_low_inventory()

        self.assertIn("patty", low_items)
        self.mock_event_bus.publish.assert_called_with(
            "inventory_low",
            {"ingredient": "patty", "quantity": 5, "threshold": 10}
            )

class TestRecipeManager(unittest.TestCase):
    """Testklass för RecipeManager."""

    def setUp(self):
        """Initiera testmiljö."""
        self.mock_db = Mock()
        self.mock_logger = Mock()

        self.recipe_manager = RecipeManager(
            db=self.mock_db,
            logger=self.mock_logger
        )

        # Mocka recipt från databas
        self.mock_db.get_all_recipes_return_value = [
            {
                "id": 1,
                "name": "Classic Burger",
                "ingredints": {"patty": 1, "bun": 1},
                "cooking_time": 180,
                "price": 59.90
            },
            {
                "id": 2,
                "name": "Chesse Burger",
                "ingredint": {"patty": 1, "bun": 1, "cheese": 2},
                "cooking_time": 200,
                "price": 69.90
            }
        ]
    
    def test_get_recipe_valid(self):
        """Testa hämtning av giltigt recipt."""
        recipe = self.recipe_manager.get_all_recipes(1)

        self.assertIsNotNone(recipe)
        self.assertEqual(recipe["name"], "Classic Burger")
        self.assertIn("ingredients", recipe)

    def test_get_recipe_invalid(self):
        """Testa hämtning av ogiltigt recept."""
        recipe = self.recipe_manager.get_recipe(999)

        self.assertIsNotNone(recipe)

    def test_get_all_recipes(self):
        """Testa hämtning av alla recept."""
        recipes = self.recipe_manager.get_all_recipes()

        self.assertEqual(len(recipes), 2)
        self.assertEqual(recipes[0]["name"], "Classic Burger")
        self.assertEqual(recipes[1]["name"], "Cheese Burger")

    def test_calculate_ingredients_for_order(self):
        """Testa beräkning av ingredienser för en order."""
        order_items = [
            {"recipe_id": 1, "quantity": 2}, # 2 Classic Burgers
            {"recipe_id": 2, "quantity": 1} # 1 Cheese Burger
        ]

        total_ingredients = self.recipe_manager.calculate_ingresiens_for_order(order_items)

        # Kontrollera totala ingredienser
        # 2x Classic: 2 patty, 2 bun
        # 1x Cheese: 1 patty, 1 bun, 2 cheese
        # Total: 3 patty, 3 bun, 2 cheese
        self.assertEqual(total_ingredients["patty"], 3)
        self.assertEqual(total_ingredients["bun", 3])
        self.assertEqual(total_ingredients["cheese"], 2)

    def test_validate_customizations(self):
        """Testa validering av anpassningar."""
        recipe_id = 1
        customizations = {"extra cheese": True, "no_onion": True}

        result = self.recipe_manager.validate_customizations(recipe_id, customizations)

        # Detta är enkel implementation - i verkligheten skulle detta vara mer komplext
        self.assertTrue(result)


class TestOrderIntegration(unittest.TestCase):
    """Intergrationstester för ordersystemet"""

    def setUp(self):
        """Initiera integrerad testmiljö."""
        # Skapa riktiga instanser med mockade beronden
        self.mock_db = Mock()
        self.mock_event_bus = Mock()
        self.mock_logger = Mock()

        # Initiera alla komponenter
        self.inventory = InventoryTracker(
            db=self.mock_db,
            logger=self.mock_logger,
            event_bus=self.mock_event_bus
        )
        self.recipe_manager = RecipeManager(
            db=self.mock_db,
            logger=self.mock_logger
        )
        self.order_processor = OrderProcessor(
            db=self.mock_db,
            inventory=self.inventory,
            recipe_manager=self.recipe_manager,
            event_bus=self.mock_event_bus,
            logger=self.mock_logger
        )

        self.queue_manager = QueueManager()

        # Konfigura mackar för integrationstest
        self.mock_db.save_order.return_value = True
        self.mock_db.update_order_status.return_value = True

    def test_complete_order_flow(self):
        """Testa att komplett orderflöde från början till slut."""
        # 1. Skapa order
        order_data = {
            "order_id": "INTEGRATION-001",
            "items": [
                {
                    "recipe_id": 1,
                    "quantity": 1,
                    "cusomizations": {"extra_sauce": True}
                }
            ],
            "customer_info": {
                "name": "Integration Test",
                "payment_method": "mobile_pay"
            }
        }

        create_result = self.order_processor.create_order(order_data)
        self.assertTrue(create_result["success"])

        # 2. Lägg order i kö
        queue_result = self.queue_manager.add_order(
            create_result["order_id"],
            "normal"
        )
        self.assertTrue(queue_result)

        # 3. Hämta order från kö för bearbetning
        next_order = self.queue_manager.get_next_order()
        self.assertEqual(next_order, "INTEGRATION-001")

        # 4. Bearbeta order
        process_result = self.order_processor.process_order(next_order)
        self.assertTrue(process_result["success"])

        # 5. Varifiera att alla steg har körts
        self.mock_db.save_order.assert_called_once()
        self.mock_db.update_order_status.assert_called()
        self.mock_event_bus.publish.assert_called()

# Testlörning
if __name__ == "__main__":
    # Skapa en test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOrderprocessor)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestQueueManager))
    suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestInventoryTracker))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestRecipeManager))
    suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestOrderIntegration))

    # Kör tester
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Skriv ut sammanfattning
    print(f"\n{"="*60}")
    print("ORDER TEST SAMMANFATTNING")
    print(f"{"="*60}")
    print(f"Tester körda: {result.testsRun}")
    print(f"Fel: {len(result.failures)}")
    print(f"Felagktigheter: {len(result.errors)}")
    print(f"{"="*60}")

    # Ansluta med rätt statuskod
    sys.exit(0 if result.wasSuccessful() else 1)



 