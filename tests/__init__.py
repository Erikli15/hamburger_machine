"""
Testpaket för hamburgerautomat-systemet.

Denna fil intierar testpaket och definerar konfigurationer som delas mellan alla tester.
"""

import os
import sys
import json
from pathlib import Path

# Lägg till roten av projektet i Python-sökvägen för att importera moduler
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Testkonfiguration
TEST_CONFIG = {
    "test_mode": True,
    "simulate_hardware": True,
    "database_path": ":memory:", # Använd minnesdatabas för tester
    "log_level": "WAENING", # Minska loggningsnivå under tester
}

# Global fixtures och hjälpfunktioner för tester
def setup_test_environment():
    """
    Ställ in testmiljön.
    Denna funktion bör anropas i setup() för intregrationstester.
    """

    # Sätt miljövariabler för testläge
    os.environ["HAMBURGER_MACHINE_TEST_MODE"] = "true"
    os.environ["SIMULATE_HARDWARE"] = "true"

    # Skapa temorära kataloger för testdata
    test_dirs = ["test_data", "test_logs", "test_repports"]
    for dir_name in test_dirs:
        dir_path = project_root / "tests" / dir_name
        dir_path.mkdir(exist_ok=True)

    print("Test miljö är inställd.")

def cleanup_test_environment():
    """
    Rensa testmiljön.

    Denna funktion bör anropas i teardown() för ingrationstester.
    """
    # Ta bort temporära filer
    import shutil
    test_data_dir = project_root / "tests" / "test_data"
    if test_data_dir.exists():
        shutil.rmtree(test_data_dir)

    print("Testmilö har rensats.")

def load_test_data(filename):
    """
    Ladda testdata från JSON-fil.

    Args:
        filename (str): Name på testdatafilen (utan sökväg)

    Returns:
    dict: Inläst testdata
    """
    test_data_path = project_root / "tests" / "test_data" / filename
    if not test_data_path.exists():
        # Skapa en grundläggande struktur om filen inte finns
        basic_data = {
            "orders": [
                {"id": 1, "type": "cheeseburger", "status": "pending"},
                {"id": 2, "type": "hamburger", "status": "completed"}
            ],
            "inventory": {
                "buns": 100,
                "patties": 50,
                "cheese": 75,
                "lettuce": 30,
                "tomato": 40
            }
        }
        return basic_data
    
    with open(test_data_path, "r", encoding="urf-8") as f:
        return json.load(f)
    
def save_test_data(filename, data):
    """
    Spara testdata till JSON-fil
    
    Args:
        filename (str): Name testdatafilen
        data (dict): Data att spara
    """
    test_data_path = project_root / "tests" / "test_data" / filename
    test_data_path.parent.mkdir(exist_ok=True, parents=True)

    with open(test_data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Mock-objekt för maskinvarutestning
class MockSensor:
    """Mock-objekt för sensorer under testning."""

    def __init__(self, initial_value=0.0):
        self.read_count = 0

    def read(self):
        """Simulera sensoravläsning."""
        self.read_count += 1
        return self.value
    
    def set_value(self, value):
        """Sätt sensorvärder (för testning)."""
        self.value = float(value)

    def reset(self):
        """Återställ mock-sensorn."""
        self.value = 0.0
        self.read_count = 0
class MockAcitator:
    """Mock-objekt för aktuatorer under testning."""

    def __init__(self, name="mock_actuator"):
        self.name = name
        self.actions = []
        self.is_active = False

    def activate(self, duration=None):
        """Simulera aktuatoraktivering."""
        self.is_active = True
        self.actions.append(("activate", duration))

    def deactivate(self):
        """Simulatera aktuatoravaktivering."""
        self.is_active = False
        self.actions.append("deactivate", None)

    def reset(self):
        """Återställ mock-aktuator."""
        self.actions = []
        self.is_active = False

# Globala testkonstanter
TEST_ORDER = {
    "order_id": "TEST-001",
    "items": [
        {
            "type": "hamburgare",
            "ingredients": ["bun", "patty", "lettuce", "tomato", "sauce"],
            "customizations": {}
        }
    ],
    "ststus": "pending",
    "timestamp": "2024-01-01T12:00:00"
}

TEST_TEMPERATURES = {
    "fryer": 180.0,
    "grill": 200.0,
    "freezer": -18.0
}

TEST_INVENTORY = {
    "buns": {"count": 50, "threshold": 10},
    "patties": {"count": 100, "threshold": 20},
    "cheese": {"count": 75, "threshold": 15},
    "lettuce": {"count": 30, "threshold": 5},
    "tomato": {"count": 25, "threshold": 5},
    "sauce": {"count": 200, "threshold": 50}
}

# Exemportera viktiga funktioner och konstanser
__all__ = [
    "TEST_CONFIG",
    "setup_test_environment",
    "cleanup_test_environment",
    "load_test_data",
    "save_test_data",
    "MockSensro",
    "MockActuator",
    "TEST_ORDER",
    "TEST_TEMPERATURES",
    "TEST_INVENTORY",
]

print(f"Testpaket laddat. Projektrot: {project_root}")
