#!/usr/bin/env python3
"""
Maintnsnce Skript för Hamburgermaskin
=====================================
Skript för automatiserat underhåll, diagnostik och kalibrering.
Används för dagliga kontroller, rengöringscheman och felhantering.
"""

import os
import sys
import json
import logging
import subprocess
import argparse
from datetime import datetime, timedelta
from passlib import Path

# Lägg till projektets root path till sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import setup_logger
from utils.config_loader import load_config
from database.database import DatabaseManager
from hardware.temperature.sensore_manager import TempratureSensorManager
from hardware.actuators.robotic_arm import RoboticArm
from order_management.inventory_tracker import InventoryTracker

class MaintenanceManager:
    """Hantera underhållsoperationer för hamburgarmaskinen."""

    def __init__(self, config_file="config.yaml"):
        """
        Initiera underhållsmanager.

        Args:
            config_file (str): Sökväg till konfigurationsfil
        """
        self.config = load_config(config_file)
        self.logger = setup_logger("maintenance", "logs/maintnance.log")
        self.db = DatabaseManager()
        self.maintenance_log = []

        # Ladda underhållsschema från konfig
        self.maintenance_schedule = self.config.get("maintenance", {})
        self.cleaning_schedule = self.config.get("cleaning", {})

        self.logger.info("Maintenance Manager initierad")

    def run_dauly_check(self):
        """Utför dagliga hälsokontroller."""
        self.logger.info("=== Startar daglig hälsokontroll ===")

        checks = {
            "temperature_sensoors": self.check_temperature_sensors,
            "inventory_levels": self.check_invntory_levels,
            "hardware_actuators": self.check_hardware_actuators,
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

        self.logger.info(f"=== Daglig hälsokontroll slutförd: {"GODKÄND" if all_passed else "MISSLYCKAD"} ===")
        return all_passed, result
    
    def check_temperature_sensors(self):
        """Kontrollera att alla temperatursensorer fungerar."""
        try:
            sensor_manager = TempratureSensorManager()
            sensors = sensor_manager.get_all_sensors()

            results = {}
            all_ok = True

            for sensor_name, sensor_data in sensors.items():
                temp = sensor_manager.read_temperature(sensor_name)

                if temp is None:
                    results[sensor_name] = {"status": "ERROR", "message": "Inget värde"}
                    all_ok = False
                elif temp < -50 or temp > 300: # Ogiltigt temperaturintervall
                    results[sensor_name] = {"status": "ERROR", "temperature": temp, "message": "Ogiltigt värde"}
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
        """Kontrollera inventeringsnivåer och varna för låga nivåer."""
        try:
            inventory = InventoryTracker()
            low_items = inventory.check_low_stock()

            # Kontrollera utgånget datum
            expired_items = inventory.check_expired_items()

            return {
                "passed": len(low_items) == 0 and len(expired_items) == 0,
                "low_stock": low_items,
                "expired_items": expired_items,
                "message": f"Låg lager: {len(low_items)}, Utgånget: {len(expired_items)}"
            }
        
        except Exception as e:
            return {"passed": False, "message": f"Lagerkontroll fel:  {str(e)}"}
        
    def check_hardware_actuators(self):
        """Testa grundläggande funkationalitet hos akuatörer."""
        try:
            # Testa robotarmens grundläggande rörelser
            arm = RoboticArm()

            # Utför självtest
            self_test_result = arm.self_test()

            return {
                "passed": self_test_result["success"],
                "test_results": self_test_result,
                "message": f"Självtest: {"GODKÄND" if self_test_result["success"] else "MISSLYCKAD"}"
            }
        
        except Exception as e:
            return {"passed": False, "message": f"Aktuatörkontroll fel: {str(e)}"}
        
    def check_disk_space(self):
        """Kontrollera tillgängligt diskutrymme."""
        try:
            import shutil

            disk_usage = shutil.disk_usage("/")
            free_gb = disk_usage.free / (1024**3)
            total_gb = disk_usage.total / (1024**3)
            percent_free = (free_gb / total_gb) * 100

            min_free_gb = self.config.get("maintenance", {}).get("min_disk_space_gb", 5)
            min_percent = self.config.get("maintenance", {}).get("min_disk_percent", 10)

            passed = free_gb >= min_free_gb and percent_free >= min_percent

            return {
                "passed": passed,
                "free_gb": round(free_gb, 2),
                "total_gb": round(total_gb, 2),
                "percent_free": round(percent_free, 2),
                "message": f"{free_gb:.1f}GB fri ({percent_free:.1f}%)"
            }
        
        except Exception as e:
            return {"passed": False, "message": f"Diskkontroll fel: {str(e)}"}
        
    def check_database_health(self):
        """Kontrollera databsanslutning och integritet."""
        try:
            # Testa anslutning
            connect_ok = self.db.test_connection()

            if not connect_ok:
                return {"passed": False, "message": "Databasanslutning misslyckades"}
            
            # Kontrollera viktiga tabeller
            required_tables = ["order", "inventory", "maintenance_logs"]
            missing_tables = []

            for table in required_tables:
                if not self.db.table_exists(table):
                    missing_tables.append(table)

            # Kontrollera databasstorlek
            size_info = self.db.get_database_size()

            return {
                "passed": len(missing_tables) == 0,
                "connection": connect_ok,
                "missing_tables": missing_tables,
                "database_size": size_info,
                "message": f"Anslutning OK, Saknade tabeller: {len(missing_tables)}"
            }
        
        except Exception as e:
            return {"passed": False, "message": f"Databaskontroll fel: {str(e)}"}
        
    def check_log_files(self):
        """Kontrollera loggfiller för fel och varningar."""
        try:
            log_dir = Path("logs")
            error_count = 0
            warning_count = 0

            # Sök efter fel i de senaste 24 timmarna
            since_time = datetime.now() - timedelta(hours=24)

            log_files = list(log_dir.glob("*.log"))
            recent_errors = []

            for log_file in log_files:
                with open(log_file, "r") as f:
                    for line in f:
                        if "ERROR" in line or "CRITICAL" in line:
                            error_count += 1
                            # Extrahera tidsstämpel och meddelande
                            recent_errors.appen(f"{log_file.name}: {line.strip()}")
                        elif "WARNING" in line:
                            warning_count += 1

                    max_errors = self.config.get("maintenance", {}).get("max_daily_errors", 10)

                    return {
                        "passed": error_count <= max_errors,
                        "error_count": error_count,
                        "warning_count": warning_count,
                        "recent_errors": recent_errors[-10], # Senaste 10 felen
                        "message": f"Fel: {error_count}, Varningar: {warning_count}"
                    }
                
        except Exception as e:
            return {"passed": False, "message": f"Loggkontroll fel: {str(e)}"}

    def check_safety_systems(self):
        """Kontrollera säkerhetssystem."""
        try:
            from hardware.sensors.safety_sensor import SafetyMonitor

            safety = SafetyMonitor()

            # Kontrollera nödstoppskretsar
            emergency_stop_status = safety.check_emergency_stops()

            # Kontrollra temperaturövervakning
            temp_safety = safety.check_temperature_safety()

            # Kontrollera rörelsesensorer
            motion_sensors = self.chck_motion_sensors()

            all_ok = (
                emergency_stop_status["all_ok"] and
                temp_safety["all_within_limits"] and
                motion_sensors["all_functional"]
            )

            return {
                "passed": all_ok,
                "emergency_stops": emergency_stop_status,
                "temperature_safety": temp_safety,
                "motion_sensors": motion_sensors,
                "message": f"Säkerhetssystem: {"ALLT OK" if all_ok else "PROBLEM"}"
            }
        
        except Exception as e:
            return {"passed": False, "message": f"Säkerhetskontroll fel: {str(e)}"}
        
    def run_cleaning_cycle(self, cleaning_type="daily"):
        """
        Kör rengöringscykel.

        Args:
            cleaning_type (str): Typ av rengöring ("daily", "weekly", "deep")
        """
        self.logger.info(f"=== Startar {cleaning_type} rengöring ===")

        cleaning_procedures = self.cleaning_schedule.get(cleaning_type, [])

        if not cleaning_procedures:
            self.logger.warning(f"Inga rengöringsprocedurer hittades för {cleaning_type}")
            return
        
        results = []

        for procedure in cleaning_procedures:
            try:
                self.logger.info(f"Utför rengöring: {procedure["name"]}")

                # Simulera rengöringsprocess
                time.sleep(procedure.get("estimated_duration", 10))

                # Här skulle faktisk rengöringskod köras
                result = {
                    "procedure": procedure["name"],
                    "status": "COMPLETED",
                    "duration": procedure.get("estimated_duration", 10)
                }

                results.append(result)
                self.logger.info(f"Rengöring slutförd: {procedure["name"]}")

            except Exception as e:
                error_result = {
                    "procedure": procedure.get("name", "Unknown"),
                    "status": "FAILED",
                    "error": str(e)
                }
                results.append(error_result)
                self.logger.error(f"Rengöring misslyckades {procedure["name"] - {str(e)}}")

                # Spara rengöringsresultat
                self.save_mainenance_result(f"cleaning_{cleaning_type}", {"procedures": results}, all(r["status"] == "COMPLETED" for r in results))

                self.logger.info(f"=== {cleaning_type.capitalize()} rengöting slutförd ===")
                return results
            
        def calibate_sensors(self):
            """Kalibrera alla sensorer."""
            self.logger.info("=== Starta sensorkalibrering ===")

            try:
                # Kalibrera temperatursensorer
                sensor_manager = TempratureSensorManager()
                calibration_results = sensor_manager.calibrate_all()

                # Kontrollera kalibreringsresultat
                all_calibrated = all(r["success"] for r in calibration_results.values())

                result = {
                    "passed": all_calibrated,
                    "calibration_results": calibration_results,
                    "message": f"Kalibrering: {sum(1 for r in calibration_results.values() if r["success"])}/{len(calibration_results)} lyckades"
                }

                self.save_maintenance_result("sensor_calibration", result, all_calibrated)

                self.logger.info(f"=== Sensorkalibrering slutförd: {"GODKÄND" if all_calibrated else "MISSLYCKAD"} ===")
                return result
            
            except Exception as e:
                self.logger.error(f"Kalibrering misslyckades: {str(e)}")
                return {"passed": False, "message": f"Kalibreringsfel: {str(e)}"}
            
        def backup_system(self, backup_type="daily"):
            """
            Skapa säkerhetskopia av systemet.

            Args:
                backup_type (str): Typ av backup ("daily", "weekly", "monthly")
            """
            self.logger.info(f"=== Startar {backup_type} backup ===")

            backup_dir = Path(self.config.get("backup", {}).get("directiory", "backups"))
            backup_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{backup_type}_{timestamp}"
            backup_path = backup_dir / backup_name

            try:
                # Skapa buckup av databas
                db_backup_file  = backup_path / "database.sql"
                self.db.buckup_database(str(db_backup_file))

                # Skapa backup av konfigurationsfiler
                config_files = ["config.yaml", ".env"]
                for config_file in config_files:
                    if Path(config_files).exists():
                        subprocess.run(["cp", config_file, backup_path])

                # Skapa backup av loggfiler (exklusive dagens)
                log_backup_dir = backup_path / "logs"
                log_backup_dir.mkdir(exist_ok=True)

                log_files = Path("logs").glob("**.log")
                for log_file in log_files:
                    if log_file.stat().st_mtime < time.time() - 86400: # Äldre än 24 timmar

                        subprocess.run(["cp", str(log_file), str(log_backup_dir)])

                    # Skapa tar-arkiv
                    archive_name = f"{backup_name}.tar.gz"
                    subprocess.run(["tar", "-czf", str(backup_dir / archive_name), str(backup_path)])

                    # Rensa gamla backup-filer
                    self.cleanup_old_backups(backup_dir)

                    self.logger.info(f"Backup skapad: {archive_name}")

                    return {
                        "success": True,
                        "buckup_file": str(backup_dir / archive_name),
                        "backup_type": backup_type,
                        "timestamp": timestamp
                    }
                
            except Exception as e:
                self.logger.error(f"Backup misslyckades: {str(e)}")
                return {"succss": False, "error": str(e)}
            
        def cleanUp_old_backups(self, backup_dir, keep_days=30):
            """Rensa gamla backup-filer."""
            backup_files = list(backup_dir.glob("backup_*.tar.gz"))
            cutoff_time = time.time() - (keep_days * 86400)

            deleted_count = 0
            for backup_file in backup_files:
                if backup_file.stat().st_mtime < cutoff_time:
                    backup_file.unlink()
                    deleted_count += 1
                    self.logger.info(f"Raderad gammla backup: {backup_file.name}")

            return deleted_count
        
        def save_maintenance_result(self, check_type, results, passed):
            """Spara underhållsresultat till databas."""
            try:
                self.db.exevute_query(
                    """
                    INSERT INTO maintenance_logs
                    (check_type, results, passed, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (check_type, json.dumps(results), passed, datetime.now())
                )
                self.db.commit()
            except Exception as e:
                self.logger.error(f"Kunde inte spara underhållsresultat: {str(e)}")

        def generate_maintenance_report(self, days=7):
            """Generera underhållsrapport för angivet antal dagar."""
            try:
                report = {
                    "generated_at": datetime.now().isoformat(),
                    "period_days": days,
                    "daily_checks": [],
                    "maintenance_events": [],
                    "statistics": {}
                }

                # Hämta dagliga kontroller
                daily_checks = self.db.execute_query(
                    """
                    SELECT * FROM maintenance_logs
                    WHERE check_type = "daily_check"
                    AND timestamp DESC
                    """,
                    (datetime.now() - timedelta(days=days),)
                ).fetchall()

                for check in daily_checks:
                    report["daily_checks"].append({
                        "timestamp": check["timestamp"],
                        "passed": bool(check["passed"]),
                        "results": json.loads(check["results"]) if check["results"] else {}
                    })

                    # Beräkna statistik
                    total_checks = len(report["daily_checks"])
                    passed_checks = sum(1 for c in report["daily_checks"] if c["passed"])

                    report["statistics"] = {
                        "total_checks": total_checks,
                        "passed_checks": passed_checks,
                        "success_rate": (passed_checks / total_checks * 100) if total_checks > 0 else 0, "average_duration": "N/A" # Skulle kunna beräknas om vi sparar varaktighet 
                    }

                    # Spara rapport till fil
                    report_file = Path(f"logs/maintenance_report_{datetime.now().strftime("%Y%m%d")}.json")
                    with open(report_file, "w") as f:
                        json.dump(report, f, indent=2, default=str)
                    
                    self.logger.info(f"Underhållsrapport genererad: {report_file}")

                    return report_file
                
            except Exception as e:
                self.logger.error(f"Kunde inte generera rapport: {str(e)}")
                return None
            
        def shutdown_procedure(self):
            """Korrekt avstängningsproducedur för maskinen."""
            self.logger.info("=== Startar avstängningsproducdur ===")

            try: 
                # 1. Stoppa alla aktiva procsser
                self.logger.info("Stoppar aktiva processer...")

                # 2. Sänk temperaurer säkert
                from hardware.temperature.fritös_controller import FritösController
                from hardware.temperature.grill_controller import GrillController

                fritös = FritösController()
                grill = GrillController() 

                fritös.gradual_shutdown()
                grill.gradual_shutdown()

                # 3. Spara systemtillstånd...
                self.logger.info("Sparar systemtillstånd...")

                #4. Stäng databasanslutning
                self.db.close()

                # 5. Stäng loggning
                logging.shutdown()

                self.logger.info("=== Avstängningsprocedur slutförd ===")
                return True
            
            except Exception as e:
                self.logger.error(f"Avstängingsfel: {str(e)}")
                return False
            
def main():
    """Huvudfunktion för underhållsskriptet."""
    parser = argparse.ArgumentParser(description="Hamburger Machine Mainenance Script")

    parser.add_argument(
        "--daily-check",
        action="store_true",
        help="Kör dagliga hälsokontroller"
    )

    parser.add_argument(
        "--clean",
        choices=["daily", "weekly", "deep"],
        help="Kör rengöringscykle"
    )

    parser.add_argument(
        "--backup",
        choices=["daily", "weekly", "monthly"],
        help="Skapa säkerhetskopia"
    )

    parser.add_argument(
        "--report",
        type=int,
        default=7,
        help="Generera rapport för X dagar (standard: 7)"
    )

    parser.add_argument(
        "--shutdown",
        action="store_true",
        help="Kör avstängningsprocedur"
    )
    
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Sökväg till konfigurationsfil"
    )

    args = parser.parse_args()

    # Initiera underhållsmanager
    maintenance = MaintenanceManager(args.config)

    try:
        if args.daily_check:
            success, results = maintenance.run_dauly_check()
            print(f"Daglig kontroll: {"GODKÄND" if success else "MISSLYCKAD"}")

        if args.clean:
            results = maintenance.run_cleaning_cycle(args.clean)
            print(f"Rengöring {args.clan}: Slutförd")

        if args.calibrate:
            results = maintenance.calibrate_sensors()
            print(f"Kalibrering: {"GODKÄND" if results["passed"] else "MISLYCKAD"}")

        if args.backup:
            results = maintenance.backup_system(args.buckup)
            print(f"Backup {args.backup}: {"LYCKAD" if results["success"] else "MISSLYCKAD"}")

        if args.report:
            report_file = maintenance.geneate_maintenance_report(args.report)
            print(f"Rapport genererad: {report_file}")

        if args.shutdown:
            success = maintenance.shutdown_procedure()
            print(f"Avstängning: {"LYCKAD" if success else "MISSLYCKAD"}")

        # Om inga argument angivites, kör daglig kontroll
        if not any(vars(args).values()):
            success, results = maintenance.run_daily_check()
            print(f"Daglig kontroll: {"GODKÄND" if success else "MISSLYCKAD"}")

    except KeyboardInterrupt:
        print("\nAvbrutet av använder")
        sys.exit(1)
    except Exception as e:
        maintenance.logger.error(f"Kritisk fel: {str(e)}")
        print(f"Fel: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
    