#!/usr/bin/env python
"""
Maintenance Skript för Hamburgermaskinen
=======================================
Skript automatiserat underhåll, digonastik och kalibrering.
Används för daglia kontroller, rengörinscheman felhantering.
"""

import os
import sys
import json
import time
import logging
import subprocess
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Lägg till projektets root path tlll sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import setup_logger
from utils.config_loader import load_config
from database.database import Databasmanager
from hardware.temperature.sensor_manager import TemperatureSensorMnager
from hardware.actuators.robotic_arm import RoboticArm
from order_management.inventory_tracker import InventoryTracker

class MaintenanceManager:
    """Hanterar underhållsoperrationer för hamburgermaskinen."""

    def __init__(self, config_path="config.yaml"):
        """
        Initiera underhållsmanager.

        Args:
            config_file (str): Sökväg till konfigurationsfill
        """
        self.config = load_config(config_path)
        self.logger = setup_logger("maintenance", "logs/mainetence.log")
        self.db = Databasmanager()
        self.maintenance_log = []

        # Ladda underhålllsschema från knfig
        self.maintenance_schedule = self.config.get("maintencenance", {})
        self.cleaning_schoule = self.config.get("cleaning", {})

        self.logger.info("Maintenance Manager initialiserad")

        def run_daily_check(self):
            """Utanför dagliga hälsokontroller."""
            self.logger.info("=== Starta daglig hälsokontroll ===")

            checks = {
                "temperature_sensors": self.check_temperature_sensors,
                "inventory_levels": self.check_inventory_levels,
                "hardware_acturators": self.check_hardware_actuators,
                "disk_space": self.check_disk_space,
                "database_health": self.check_database_health,
                "log_files": self.check_log_files,
                "safety_systems": self.check_safety_systems
            }

            results = {}
            all_passed = True

            for check_name, check_func in checks.items():
                try:
                    self.logger.info(f"Utför kontroll: {check_name}")
                    result = check_func()
                    results[check_name] = result

                    if not result.get("passed", False):
                        all_passed = False
                        self.logger.warning(f"Kontroll misslyckades: {check_name} - {result.get("message", "")}")
                    else:
                        self.logger.info(f"Kontroll godkänd: {check_name}")

                except Exception as e:
                    self.logger.error(f"Fel under kontroll {check_name}: {str(e)}")
                    results[check_name] = {"passed": False, "message": str(e)}
                    all_passed = False

                # Spara resultat till databas
                self.save_maintenance_result("daily_check", results, all_passed)

                self.logger.info(f"=== Daglig hälsokontroll slutförd: {"GODKÄND" if all_passed else "MISSLYCAD"} ===")
                return all_passed, results
            
        def check_temperature_sensors(self):
            """Kontrollera att alla temperatursensorer fungerar."""
            try:
                sensor_manager = TemperatureSensorMnager()
                sensors = sensor_manager.get_all_sensors()

                results = {}
                all_ok = True

                for sensor_name, sensor_data in sensors.items():
                    temp = sensor_manager.read_temperature(sensor_name)

                    if temp is None:
                        results[sensor_name] = {"status": "ERROR", "mssage": "Inget värde"}

                        all_ok = False
                    elif temp < -50 or temp > 300: # Ogiltigt temperaturintervall
                        results[sensor_name] = {"status": "ERROR", "temperature": temp, "message": "ogiltigt värde"}
                        all_ok = False
                    else:
                        results[sensor_name] = {"status": "OK", "temperature": temp} 

                return {
                    "passed": all_ok,
                    "sensors": results,
                    "message": f"{sum(1 for r in results.values() if r["status"] == "OK")}/{len(results)} sensorer OK"
                }
            
            except Exception as e:
                return {"passed": False, "message": f"Sensorkontroll fel: {str(e)}"}
            
        def check_inventory_levels(self):
            """Kontrollera inveteringsnivåer och varna låg nivåer."""
            try:
                inventory = InventoryTracker()
                low_items = inventory.check_expired_items()

                # Kontrolera utgånget datum
                expired_items = inventory.check_expired_items()

                return  {
                    "passed": len(low_items) == 0 and len(expired_items) == 0,
                    "low_stock": low_items,
                    "expired_items": expired_items,
                    "message": f"Låg lager: {len(low_items)}, Utgånget: {len(expired_items)}"
                }
            
            except Exception as e:
                return {"passed": False, "message": f"Lagerkontroll fel: {str(e)}"}
            

            