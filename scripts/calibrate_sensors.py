#!/usr/bin/ env python3
"""
Sensor Calibration Script för Hamburgarmaskinen

Detta skript utför kalibrering av olika sensorer i systemet.
Körs regelbundet eller vid behov för att säkerställa noggrannhet.
"""

import sys
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

# Lägg till systemvägar
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import setup_logger
from utils.config_loader import load_config
from hardware.temperature.sensor_manager import TemperatureSensorManager
from hardware.sensors.inventory_sensor import InventorySensor
from hardware.sensors.safety_sensor import Safetysensor
from database.database import DatabaseConnection

class SensorCalibrator:
    """Huvudklass för sensorkalibrering"""

    def __init__(self, config_path="config.yaml"):
        """Initiera kalibratorn"""
        self.config = load_config(config_path)
        self.logger = setup_logger("sensor_calibrator", "logs/calibration.log")

        # Initiera sensorhanterare
        self.temp_manager = TemperatureSensorManager()
        self.inventory_sensor = InventorySensor()
        self.safety_sensor = Safetysensor()

        # Databasanslutning
        self.db = DatabaseConnection()

        # Kalibreringsresultat
        self.calibration_result = {
            "timestamp": datetime.now().isoformat(),
            "sensors": {},
            "overall_status": "pending"
        }

        self.logger.info("SensorCalibrator initiserad")

    def calibrate_temperature_sensors(self, reference_temps=None):
        """
        Kalibrera temperatur sensorer

        Args:
            reference_temps: Dictionary med förväntande temperaturer per zon
        """
        self.logger.info("Startar temperatur sensorkalibrering...")

        if reference_temps is None:
            reference_temps = {
                "fryer": 180.0, # Standard fritöstemp
                "grill": 200.0, # Standard grilltemp
                "freezer": -18.0, # Standard frysfacktemp
                "assembly": 22.0 # Rums temperatur
            }

            results = {}
            try:
                # Stäng av värmare för kalibrering
                self.logger.info("Stänger av varmare för kalibrering...")
                # Här skulle vi kolla på metod för att stänga av värmar

                # Vänta på att temperatur stabiliseras
                time.sleep(10)

                # Kalibrera varje zon
                for zone, expected_temp in reference_temps.items():
                    self.logger.info(f"Kalibrerar {zone}...")

                    # Ta flera mättningar för noggrannhet
                    readings = []
                    for i in range(5):
                        try:
                            temp = self.temp_manager.get_temperature(zone)
                            if temp is not None:
                                reading.append(temp)
                                time.sleep(1)
                        except Exception as e:
                            self.logger.error(f"Fel vid avläsning {zone}: {e}")

                    if readings:
                        avg_temp = sum(readings) / len(readings)
                        offset = avg_temp - expected_temp

                        # Justera kalibrering om avvikelsen är för stor
                        if abs(offset) > self.config.get("calibration", {}).get("max_temp_offset", 2.0):
                            self.logger.warning(f"Stor avikelse i {zone}: {offset:.2f}°C")

                            # Spara kalibreringsoffset
                            self.temp_manager.set_calibration_offset(zone, -offset)
                            adjusted = True
                        else:
                            adjusted = False

                        results[zone] = {
                            "expected": expected_temp,
                            "measured": avg_temp,
                            "offset": offset,
                            "adjusted": adjusted,
                            "readings": readings,
                            "status": "success" if abs(offset) <= 5.0 else "warning"
                        }

                        self.logger.info(
                            f"{zone}: Förväntat={expected_temp}°C,"
                            f"Mätt={avg_temp:1f}°C,"
                            f"Offset={offset:2f}°C"
                            f"Justerad={adjusted}"
                        )
                    else:
                        results[zone] = {
                            "status": "error",
                            "error": "Inga giltiga avläsningar"
                        }
                        self.logger.error(f"Kunde inte läsa temperatur för {zone}")

                # Återsäll värmare till driftstemperatur
                self.logger.info("Återställer värmare...")
                # När skulle vi kolla på för att återställa

            except Exception as e:
                self.logger.error(f"Fel vid temperaturkalivrering {e}")
                results["error"] = str(e)

            self.calibration_result["sensors"]["temperature"] = results
            return results
        
    def calibrate_inventory_sensors(self):
        """Kalibrera inventeringssensorer (vikt/avstånd)"""
        self.logger.info("Startar inventeringssensorkalibering...")


        results = {}
        try:
            # Kalibera varje ingredispenseras sensor
            ingredients = self.config("inventrory", {}).get("ingredients", [])

            for ingredient in ingredients:
                name = ingredient.get("name")
                sensor_type = ingredient.get("sensor_type", "weight")

                self.logger.info(f"Kalibrerar {name} ({sensor_type})...")

                if sensor_type == "weight":
                    # Utför nollställning av våg
                    success = self.inventory_sensor.calibrate_weight_sensor(name)

                    # Verifiera med testvikter om tillgängligt
                    if self.config.get("calibration", {}).get("use_test_weights", False):
                         test_weight = ingredient.get("test_weight", 100) # Gram
                         varified = self.inventory_sensor.verify_calibration(name, test_weight)
                    else:
                        varified = True
                        
                    results[name] = {
                        "sensore_type": sensor_type,
                        "calibrated": success,
                        "status": "success" if success else "waening"
                    } 

                self.logger.info(f"{name}: Kalibrerad={results[name]["calibrated"]}")

        except Exception as e:
            self.logger.error(f"Fel vid inventeringskalibrering: {e}")
            results["error"] = str(e)

        self.calibration_result["sensors"]["inventory"] = results
        return results
        
    def calibrate_safety_sensors(self):
        """Kalibtrera säkerhetssensorer (nödstopp, dörrar, rökdetektor)"""
        self.logger.info("Startar säkerhetssensorkalibrering...")

        results = {}
        try:
            # Testa nödstoppsknappar
            emergency_buttons = self.config.get("safety", {}).get("emergency_buttons", [])

            for button in emergency_buttons:
                location = button.get("lovation")
                self.logger.info(f"Testar nödstopp {location}...")

                # Simulera knapptryckning (i verkligheten skulle vi aktivera en testfunktion)
                test_result = self.safety_sensor.test_emergency_button(location)

                results[f"emergency_{location}"] = {
                    "type": "emergency_button",
                    "tested": test_result,
                    "status": "success" if test_result else "error"
                }
            # Testa säkerhetsgrännser
            safety_limits = self.config.get("safety", {}).get("limits", {})

            for limit_name, limit_value in safety_limits.items():
                self.logger.info(f"Verifierar säkerhetsgräns {limit_name}...")

                # varifiera att gränsvärderna är korrekt konfigurerade
                verified = self.safety_sensor.varify_safety_limit(limit_name, limit_value)

                results[f"limit_{limit_name}"] = {
                    "type": "selfty_limit",
                    "value": limit_value,
                    "verified": verified,
                    "status": "success" if verified else "warning"
                } 

            # Testa rökdetektor
            if self.config.get("safety", {}).get("smoke_dector", False):
                self.logger.info("Testar rökdetektor...")

                # Starta självtest på detektor
                test_result = self.safety_sensor.test_smoke_detector()

                results["smoke_detector"] = {
                    "type": "smoke_detector",
                    "tested": test_result,
                    "status": "success" if test_result else "error"
                }

        except Exception as e:
            self.logger.error(f"Fel vid säkerhetskalibrering: {e}")
            results["error"] = str(e)

        self.calibration_results["sensors"]["safety"] = results
        return results
        
    def calibrate_all(self):
        """Utför komplett kalibrering av alla sensorer"""
        self.logger.info("=== STARTAR KOMPLETT SENSORKALIBRERING ===")

        start_time  = time.time()

        # Kalibrera alla sensortyper
        temp_results = self.calibrate_temperature_sensors()
        inventory_results = self.calibrate_inventory_sensors()
        safety_results = self.calibrate_safety_sensors()

        # Uttvärdera totalstatus
        all_results = [temp_results, inventory_results, safety_results]

        has_errors = any(
            any(r.get("status") == "error" for r in results.values()
                if isinstance(r, dict))
                for results in all_results
        )

        has_warnings = any(
            any(r.get("status") == "warning" for r in results.values()
                if isinstance(r, dict))
                for results in all_results
        )

        if has_errors:
            overall_status = "error"
        elif has_warnings:
            overall_status = "warning"
        else:
            overall_status = "success"
        
        self.calibration_result["overall_status"] = overall_status
        self.calibration_result["duration_seconds"] = time.time() - start_time

        # Spara resultat
        self.save_calibration_results()

        self.logger.info(f"=== KALIBRERING SLUTFÖRD: {overall_status.upper()} ===")
        self.logger.info(f"Tid: {self.calibration_result["duration_seconds"]:1f} sekunder")

        return self.calibration_result
    
    def save_calibration_results(self):
        """Spara kalibreringsresultat till fil och databas"""
        try:
            # Spara till JSON-fil
            result_dir = Path("logs/calibrations")
            result_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = result_dir / f"calibration_{timestamp}. json"

            with open(filename, "w") as f:
                json.dump(self.calibration_result, f, indent=2, default=str)

            self.logger.info(f"Kalibreringsresultar sparad till {filename}")

            # Spara till databas
            if self.db.is_connected():
                self.db_save_caibration_record(self.calibration_result)
                self.logger.info("Kalibreringsresultat sparad till {filename}")

        except Exception as e:
            self.logger.error(f"Kunde inte spara kalibreringsresultar: {e}")

    def generate_report(self):
        """Generara en läsbar rapport av kalibretingen"""
        report = []
        report.append("=" * 60)
        report.append("SENSORKALIBRERIMG - SAMMANFATTNING")
        report.append("=" * 60)
        report.append(f"Datum: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}")
        report.append(f"Status: {self.calibration_result.get("duration_sconds", 0):.1f} sekunder")
        report.append("")

        for sensor_type, sensors in self.calibration_result.get("sensors", {}).items():
            report.append(f"{sensor_type.upper()} SENSORER:")
            report.append("-" * 40)

            for name, data in sensors.items():
                if isinstance(data, dict):
                    status_symbol = {
                        "success": "✓",
                        "warning": "⚠",
                        "error": "✗",
                        "pending": "?"
                    }.get(data.get("status", "pending"), "?")

                    if sensor_type == "temperature":
                        if "offset" in data:
                            report.append(
                                f"{status_symbol} {name}: "
                                f"{data.get("measured", 0):.1f}°C"
                                f"(offset: {data.get("offset", 0):2f}°C)"
                            )
                        else:
                            report.append(
                                f"{status_symbol} {name}"
                                f"{data.get("status", "unknown")}"
                            )

                    report.append("")

            return "\n".join(report)
        
    def cleanup(self):
        """Stänger ner resurser"""
        try:
            self.db.close()
            self.logger.info("Kalibratitor stängd")
        except Exception as e:
            self.logger.error(f"Fel vid strägning: {e}")

def main():
    """Huvudfunktion för skriptet"""
    parser = argparse.ArgumentParser(description="Kalibrera hamburgarmaskinens sensorer")
    parser.add_argument("--type", choices=["all", "temp", "inventory", "safety"],
                        default="all", help="Typ av kalibrering att utföra")
    parser.add_argument("--config", default="config.ymal",
                        help="Sökväg till konfigurationsfill")
    parser.add_argument("--report", action="store_true",
                        help="Visa rapport efter kalibrering")
    parser.add_argument("--save-only", action="store_true",
                        help="Spara bara resultat utan att utföra kalivrering")

    args = parser.parse_args()

    # Initiera kalibrator
    calibrator = SensorCalibrator(args.config)

    try:
        if args.save_only:
            # Endast spara existerande resultat
            calibrator.save_calibration_results()
            print("Resultat sparade")
            return
        
        # Utför vald kalibrering
        if args.type == "all":
            results = calibrator.calibrate_all
        elif args.type == "temp":
            results = calibrator.calibrate_temperature_sensors()
        elif args.type == "inventory":
            results = calibrator.calibrate_inventory_sensors()
        elif args.type == "safety":
            results = calibrator.calibrate_safety_sensors()
        else:
            print(f"Okänd kalibreringstyp {args.type}")
            return

        # Visa rapport om begärd
        if args.report:
            print(calibrator.generate_report())

        # Visa sammanfattning
        status = results.get("överall_status", "unknown")
        status_color = {
            "success": "\033[92m", # Grön
            "warning": "\033[93m", # Gul
            "error": "\033[91m", # Röd
        }.get(status, "\033[0m") # Standard

        print(f"\n{status_color}Kalibrering status: {status.uppor()}\033[0m")

        # Ansluta med lämplig exit-kod
        if status == "error":
            sys.exit(1)
        elif status == "warning":
            sys.exit(2)
    except KeyboardInterrupt:
        print("\nKalibrering avbruten av användare")
        sys.exit(130)
    except Exception as e:
        print(f"Kritiskt fel: {e}")
        calibrator.logger.error(f"Kritisk fel: {e}", exc_info=True)
        sys.exit(1)
    finally:
        calibrator.cleanup()

if __name__ == "__main__":
    main()

