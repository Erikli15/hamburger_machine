#!/usr/bin/env python3
"""
Hardware Setup Script för hamnburgermskinen
Skript att kongigura, testa och kalibrera maskinvarukomponentrt
"""

import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime

# Lägg till projektets rot i sökväg
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Impotera projektmoduler
try:
    from utils.logger import setup_logger
    from utils.config_loader import load_config
    from hardware.temperature.sensore_manager import TemperatureSensorManager
    from hardware.temperature.fritös_controller import FryerController
    from hardware.temperature.grill_controller import GrillController
    from hardware.temperature.freezer_controller import FreezerController
    from hardware.actuators.robotic_arm import RoboticArm
    from hardware.actuators.conveyor import Conveyor
    from hardware.actuators.dispenser import Dispenser
    from hardware.sensors.inventory_sensor import InventorySensor
    from hardware.sensors.safety_sensor import SafetySensor
    from hardware.payment.card_reader import CardReader
except ImportError as e:
    print(f"Importfel: {e}")
    print("Se till att alla nödvändiga paket är inställerade:")
    print("pip install -r requirements.txt")
    sys.exit(1)


class HardwareSetup:
    """KLass för att hantera maskinvaruinsallation och konfiguration"""

    def __init__(self, config_file="config.yaml"):
        """Initiera setup-verktyget"""
        self.config = load_config(config_file)
        self.logger = setup_logger("hardware_setup")

        # Komponenter ska initieras
        self.components = {}
        self.test_results = {}

        # Skapa setup-mapp om den inte finns
        self.setup_dir = project_root / "setup_data"
        self.setup_dir.mkdir(exist_ok=True)

        print("\n" + "="*60)
        print("HAMBURGER MASKIN - HARDWARE SETUP")
        print("="*60)

    def run_interactive_setup(self):
        """Kör interaktiv installationsguide"""
        print("\nVÄLKOMMEN TILL HARDWARE SETUP")
        print("Denna guid hjälper dig att instalera och konfigura maskinvaran.")

        while True:
            print("\nHUVUDMENY:")
            print("1. Fullstädig automatisk installation")
            print("2. Manuell steg-för-steg installation")
            print("3. Testa specifika komponenter")
            print("4. Kaligrera sensorer")
            print("5. Generera installationsrapporter")
            print("6. Avsluta")

            choice = input("\Välj alternativ (1-6): ").strip()

            if choice == "1":
                self.automatic_setup()
            elif choice == "2":
                self.manual_setup()
            elif choice == "3":
                self.test_components_menu()
            elif choice == "4":
                self.calibrate_sensors()
            elif choice == "5":
                self.generate_report()
            elif choice == "6":
                print("\nAvslutar setup...")
                break
            else:
                print("Ogiltigt val. Försöker igen.")

        def automatic_setup(self):
            """Utför fullständig automatisk installation"""
            print("\n" + "="*60)
            print("AUTOMATISK INSTALLATION")
            print("="*60)

            steps = [
                ("Kontrollerar systemkrav", self.check_system_requirements),
                ("Initierar loggning", self.setup_logging),
                ("Konfigurerar temperaturkontroller", self.setup_temperature_controllers),
                ("Initierar aktuatorer", self.setup_actuators),
                ("Konfigurerar sensorer", self.setup_sensors),
                ("Testar betalningssystem", self.setup_payment),
                ("Utför grundläggande testar", self.run_basic_tests),
                ("Spara konfiguration", self.save_configuratio),
            ]

            for step_name, step_func in steps:
                print(f"\n▶ {step_name}...")
                try:
                    success = step_func()
                    print(f"  ✗ {step_name} - MISSLYCKADES")
                    retry = input(" Försöka igen? (j/n): ").lower()
                    if retry == "j":
                        step_func()
                except Exception as e:
                    print(f"  ✗ Fel: {e}")

            print("\n" + "="*60)
            print("AUTOMATISK INSTALLATION SLUTFÖRD")
            print("="*60)

            self.generate_report()

        def checl_system_requirements(self):
            """Kontrollera systemkrav"""
            print("\nKontrollerar systemkrav:")

            requirements = {
                "Python version": sys.version_info >= (3, 8),
                "OS": sys.platform in ["linux", "linux2", "dravin"],
                "GPIO access": self.check_gpio_access(),
                "Config file": (project_root / "config.yaml").exists(),
                "Log directory": (project_root / "logs").exists(),
            }

            all_met = True
            for req, status in requirements.items():
                status_sumbol = "✓" if status else "✗"
                print(f" {status_sumbol} {req}")
                if not status:
                    all_met = False
            
            if not all_met:
                print("\nVarning: Visst systemkrav är inte uppfyllda.")
                print("Vill du fortsätta ändå? (ja/nej)", end="")
                if input().lower() != "j":
                    return False
            
            return True
        
        def check_gpio_access(self):
            """Kontrollera GPIO-åtkomst (för Rasoberry Pi)"""
            try:
                import RPi.GPIO as GPIO
                return True
            except (ImportError, RuntimeError):
                # Simulerad GPIO för utvecklingsmiljö
                print(" Info: GPIO inte tillgängligt - använder simuletingsläge")
                return True
            
        def setup_temperature_controllers(self):
            """Initiera och konfigurera temperaturkontroller"""
            print("\nInitierar temperaturkontroller:")

            try:
                # Temperatursensorhanterare
                temp_manager = TemperatureSensorManager(self.config)
                temp_manager.initialize()
                self.components["temperature_manager"] = temp_manager
                print("  ✓ Temperatursensorhanterare")

                # Fritös
                fryer = FryerController(self.config)
                fryer.initialize()
                self.components["fryer"] = fryer
                print("  ✓ Fritöskontroller")

                # Grill
                grill = GrillController(self.config)
                grill.initialize()
                self.components["grill"] = grill
                print("  ✓ Grillkontroller")

                # Frysfack
                freezer = FreezerController(self.config)
                freezer.initialize()
                self.components["freezer"] = freezer
                print("  ✓ Frysfackskontroller")

                # Testa temperaturläsning
                self.test_temperature_sensors()

                return True
            
            except Exception as e:
                print(f"  ✗ Fel vid initiering: {e}")
                return False

        def setup_actuators(self):
            """Initiera aktuatorer"""
            print("\nInitierar aktuatorer:")

            try:
                # Robotarm
                robotic_arm = RoboticArm(self.config)
                robotic_arm.initialize()
                self.components["robotic_arm"] = robotic_arm
                print("  ✓ Robotarm")

                # Transportband 
                conveyor = Conveyor(self.config)
                conveyor.components["conveyor"] = conveyor
                print("  ✓ Transportband")

                # Dispensrar
                dispenser = Dispenser(self.config)
                dispenser.initialize()
                self.components["dispenser"] = dispenser
                print("  ✓ Ingrediensdispensrar")

                return True
            
            except Exception as e:
                print(f"  ✗ Fel vid initiering: {e}")
                return False
            
        def setup_robotic_arm(self):
            """Konfigurera robotarm specifikt"""
            if "robotic_arm" not in self.components:
                self.setup_actuators()

            arm = self.components["robotic_arm"]

            print("\nKalibrerar robotarm...")
            arm.calibete()

            print("\nTestar rörelser:")
            movements = ["home", "pickup", "grill", "assembly", "delivery"]

            for movement in movements:
                print(f" Testar {movement} position...")
                success = arm.move_to_position(movement)
                status = "✓" if success else "✗"
                print(f" {status} {movement}")
                time.sleep(1)

            arm.return_home("  ✓ Robotarm kalibrerad")

        def setup_conveyor(self):
            """Kontrollera transportband"""
            if "conveyor" not in self.components:
                self.setup_actuators()

            conveyor = self.components["conveyor"]

            print("\nTestar transportband:")

            # Testa olika hastigheter
            speeds = [30, 50, 80, 100]
            for speed in speeds:
                print(f" Hästighet {speed}%...")
                conveyor.set_speed(speed)
                conveyor.move_forward(2) # rör sig i 2 sekunder
                time.sleep(1)

            conveyor.stop()
            print("  ✓ Transportband testat")

        def setup_dispensers(self):
            """Konfigurera dispensrar"""
            if "dispenser" not in self.components:
                self.setup_actuators()

            dispenser = self.components["dispenser"]

            print("\Testera dispensrar:")

            # Testa varje ingrediensdispenserar
            ingredients = self.config["dispenser"]["ingrediens"]

            for ingredient in ingredients:
                print(f" Testar {ingredient} dispenserar...")
                success = dispenser.dispense(ingredient, 1) # 1 portion
                status = "✓" if success else "✗"
                print(f" {status} {ingredient}")
                time.sleep(0.5)

            print("  ✓ Alla dispensrar testade")

        def setup_sensors(self):
            """Initiera alla sensorer"""
            print("\nInitierar sensorer:")

            try:
                # Inventeringsensorer
                inventory_sensor = InventorySensor(self.config)
                inventory_sensor.initialize()
                self.commponents["inventory_sensor"] = inventory_sensor
                print("  ✓ Säkerhetssensorer")

                return True
            
            except Exception as e:
                print(f"  ✗ Fel vid initiering: {e}")
                return False
            
        def set_inventory_sensors(self):
            """Konfigurera inventoriesensorer"""
            if "inventory_sensor" not in self.components:
                self.setup_sensors()

            sensor = self.components["inventory_sensor"]

            print("\nKaligrerar inventeriesensorer...")
            sensor.calibrate()

            print("\nLäser sensorvärden:")
            levels = sensor.read_all_levels()

            for ingredient, level in levels.items():
                status = "OK" if level > 20 else "LÅG"
                print(f" {ingredient}: {level}% - {status}")

            print("  ✓ Inventeriesensorer konfigurerade")

        def setup_safety_sensors(self):
            """Konfigurera säkerhetssensorer"""
            if "safety_sensor" not in self.components:
                self.setup_sensors()

            sensor = self.components["safety_sensor"]

            print("\nTestar säkerhetssensorer:")

            # Testa varje säkerhetsfunktion
            tests = [
                ("Nödstopp", sensor.test_emergency_stop),
                ("Dörrkontakt", sensor.test_door_sensor),
                ("Rökdeteltor", sensor.test_smoke_detector),
                ("Temperaturövervakning", sensor.test_temperature_safety),
            ]

            for test_name, test_func in tests:
                print(f" Testar {test_name}...")
                try:
                    success = test_func()
                    status = "✓" if success else "✗"
                    print(f" {status} {test_name}")
                except Exception as e:
                    print(f"    ✗ Fel: {e}")

            print("  ✓ Säkerhetssensorer testade")

        def setup_payment(self):
            """Konfigurera betalningssystem"""
            print("\Initierar betalningssystem:")

            try:
                card_reader = CardReader(self.config)
                card_reader.initialize()
                self.components["card_reader"] = card_reader
                print("  ✓ Kortläsare")

                # Testa kortläsaren
                print(" Testar kortläsare...")
                print(" INFO: Placera testkort i läsaren")
                time.sleep(2)

                # Simulerad läsning för test
                test_result = card_reader.test_reader()
                if test_result:
                    print("  ✓ Kortläsare fungerar")
                else:
                    print("  ⚠ Kortläsare test misslyckades (kontrollera anslutning)")
                
                return True

            except Exception as e:
                print(f"  ✗ Fel vid initiering: {e}")
                return False
            
        def test_components_menu(self):
            """Meny för att testa specifika komponenter"""
            print("\n" + "="*60)
            print("KOMPONENTTESTER")
            print("="*60)

            test_options = [
                ("1", "Temperatursensorer", self.test_temperature_sensors),
                ("2", "Robotarm", self.test_robotic_arm),
                ("3", "Transportband", self.test_conveyor),
                ("4", "Dispenserar", self.test_dispensers),
                ("5", "Inventeriesensorer", self.test_inventory_sensors),
                ("6", "Säkerhetssystem", self.test_safety_system),
                ("7", "Betalningssystem", self.test_payment_system),
                ("8", "Kommunikationsbuss", self.test_communication),
                ("9", "Alla kompobebter", self.run_all_tests),
                ("0", "Tillbaka", None)
            ]

            while True:
                print("\nVälj kokponent att testa:")
                for num, name, _ in test_options:
                    print(f" {num}. {name}")

                choice = input("\nVal (0-9): ").strip()

                if choice == 0:
                    break

                for num, name, func in test_options:
                    if choice == num and func:
                        print(f"\n▶ Testar {name}...")
                        func()
                        break
                    else:
                        print("Ogiltigt val")

        def test_temperature_sensors(self):
            """Testa temperaturkontroller:"""
            print("\nTestar temperaturkontroller")

            if "temperature_manager" not in self.components:
                print(" Temperaturhanterare inte initirad")
                return
            
            manager = self.components["temperature_manager"]

            # Läs temperaturer från alla zoner
            temperatures = manager.read_all_temperatures()

            for zone, temp in temperatures.items():
                status = "OK" if 20 <= temp <= 250 else "FEL"
                print(f" {zone}: {temp:.1f}°C - {status}")

            print("  ✓ Temperaturläsning klar")

        def test_robotic_arm(self):
            """Testa robotiarmens funkationalitet"""
            print("\nTestar robotarm:")

            if "robotic_arm" not in self.components:
                print(" Robotarm inte initierad")
                return
            
            arm = self.components["robotic_arm"]

            # Testa olika rörelser
            test_positions = ["home", "pickup", "grill", "assembly", "delivery"]

            for pos in test_positions:
                print(f" Flyttar till {pos}...")
                success = arm.move_to_position(pos)
                status = "✓" if success else "✗"
                print(f" {status} Position {pos}")
                time.sleep(1)

            arm.return_home()
            print("  ✓ Robotarmtest slutfört")

        def test_conveyor(self):
            """Testa transportband"""
            print("\nTestar transportband:")

            if "conveyor" not in self.components:
                print(" Transportband inte initierat")
                return
            
            conveyor = self.components["conveyor"]

            # Testa framåt och bakåt
            directions = [
                ("framåt", conveyor.move_forward),
                ("bakåt", conveyor.move_backward)
            ]

            for direction_name, direction_func in directions:
                print(f" Rör sig {direction_name}...")
                direction_func(3) # 3 sekunder
                conveyor.stop()
                time.sleep(1)

            # Testa hastighetskontroll
            print(" Testar hastigheterkontroll...")
            for speed in [30, 50, 75, 100]:
                conveyor.set_speed(speed)
                conveyor.stop()
                time.sleep(0.5)

            print("  ✓ Transportbandtest slutfört")

        def test_dispensars(self):
            """Testa dispensar"""
            print("\nTestar dispensrar:")

            if "despenser" not in self.components:
                print(" Dispensrar inte initierade")
                return 
            dispenser = self.components["dispenser"]

            # Testa varje dispensertyp
            ingredients = self.config["dispenser"]["ingredients"]

            for ingredient in ingredients:
                print(f" Testar {ingredient} dispensrar...")
                success = dispenser.dispense(ingredient, 1)
                status = "✓" if success else "✗"
                print(f" {status} {ingredient}")
                time.sleep(0.5)

            print("  ✓ Dispersertest slutfört")

        def test_inventory_sensors(self):
            """Testa inventeriesensorer"""
            print("\nTestar invneteriesensorer:")

            if "inventory_sensor" not in self.components:
                print(" Inventeriesensorer inte initierade")
                return
            
            sensor = self.components["inventory_sensor"]

            # Läs alla nivåer
            levels = sensor.read_all_levels()

            print(" Aktuella nivåer:")
            for ingredient, level in levels.items():
                if level > 75:
                    status = "HÖG"
                elif level > 25:
                    status = "OK"
                else:
                    status = "LÅG"
                print(f" {ingredient}: {level}% - {status}")
            
            print("  ✓ Inventeriesensortest slutfört")

        def test_safety_system(self):
            """Testa säkerhetssystem"""
            print("\nTestar säkerhetssystem:")

            if "safety_sensor" not in self.components:
                print(" Säkerhetssensorer inte initierade")
                return
            
            sensor = self.components["safety_sensor"]

            print(" Säkerhetsstatus:")

            # Kontrollera alla säkerhetsfunktioner
            safety_checks = [
                ("Nödstopp", sensor.is_emergency_stop_active),
                ("Dörrstängd", sensor.is_door_closed),
                ("Rökfrit", sensor.is_smoke_detected),
                ("Temperatur OK", sensor.is_temperature_safe),
                ("Alla säkerheter OK", sensor.is_all_safe),
            ]

            all_ok = True
            for check_name, check_func in safety_checks:
                try:
                    result = check_func()
                    status = "✓" if result else "✗"
                    print(f" {status} {check_name}")
                    if not result and check_name != "Alla säkerheter OK":
                        all_ok = False
                except Exception as e:
                    print(f"    ✗ {check_name}: Fel - {e}")
                    all_ok = False

            if all_ok:
                 print("  ✓ Alla säkerhetskontroller godkända")
            else:
                print("  ⚠ Varning: Vissa säkerhetskontroller misslyckades")

        def test_payment_system(self):
            """Testa betalningssystem"""
            print("\nTestar betalningssystem:")

            if "card_reader" not in self.components:
                print(" Betalningssystemet inte initierat")
                return 
            
            card_reader = self.components["card_reader"]

            print(" Testar kortläsare...")
            print(" INFO: Använd testkort eller tryck Enter för att simulera")

            # Simulerad test
            test_amount = 99.50 # Testbelopp
            print(f" Testtransaktion: {test_amount} SEK")

            success = card_reader.process_payment(test_amount)

            if success:
                print("  ✓ Betalning godkänd (simulerad)")
            else:
                print("  ✗ Betalning nekad (simulerad)")

            print("  ✓ Betalningstest slutfört")

        def test_communication(self):
            """Testa kommunikation mellan koponenter"""
            print("\nTestar systemkommunikation:")

            # Testa att alla komponenter svarar
            components_to_test = [
                ("Temperaturhanterare", "temperature_manager"),
                ("Robortarm", "robotic_arm"),
                ("Transportband", "conveyor"),
                ("Dispensrar", "dispenser"),
                ("Inventeriesensorer", "inventory_sensor"),
                ("Säkerhetssensorer", "safety_sensor"),
            ]

            all_responding = True
            for comp_name, comp_key in components_to_test:
                if comp_key in self.components:
                    print(f"  ✓ {comp_name} ansluten")
                else:
                    print(f"  ✗ {comp_name} inte ansluten")
                    all_responding = False

            if all_responding:
                print("  ✓ Alla komponenter kommunicerar")
            else:
                print("  ⚠ Varning: Vissa komponenter svarar inte")
        
        def run_all_testas(self):
            """Kör alla tester"""
            print("\n" + "="*60)
            print("KOMPLETT SYSTEMTEST")
            print("="*60)

            tests = [
                ("Temperatursystem", self.test_temperature_sensors),
                ("Robotarm", self.test_robotic_arm),
                ("Transportband", self.test_connveyor),
                ("Dispensrar", self.test_dispensers),
                ("Invneteriensorer", self.test_inventory_sensors),
                ("Säkerhetssystem", self.test_safety_system),
                ("Betalningssystem", self.test_payment_system),
                ("Systemkommunikation", self.test_communcation),
            ]

            self.test_results = {}

            for test_name, test_func in tests:
                print(f"\n▶ Testar {test_name}...")
                try:
                    start_time = time.time()
                    test_func()
                    elapsed = time.time() - start_time
                    self.test_results[test_name] = {"status": "PASS", "time": elpased}
                    print(f"  ✓ {test_name} - KLAR ({elapsed:.1f}s)")
                except Exception as e:
                    self.test_results[test_name] = {"status": "FAIL", "error": str(e)}
                    print(f"  ✗ {test_name} - MISSLYCKADES: {e}")
                
            print("\n" + "="*60)
            print("TEST SAMMANFATTNING")
            print("="*60)

            passed = sum(1 for r in self.test_result_values() if r["status"] == "PASS")
            total = len(self.test_results)

            print(f"\nResultat: {passed}/{total} tester godkända")

            if passed == total:
                print("✓ ALLA TEST GODKÄNDA - Systemet är redo!")
            else: 
                print("⚠ VARNING: Vissa tester misslyckades")
                for test_name, result in self.test_result.items():
                    if result["status"] == "FAIL":
                        print(f"  ✗ {test_name}: {result.get('error', 'Okänt fel')}")

        def run_basic_tester(self):
            """Köra grundläggande systemtest"""
            print("\nKör grundläggande systemtest...")

            basic_tests = [
                self.test_temperature_sensors,
                self.test_safety_system,
                self.test_communication,
            ]

            for test_func in basic_tests:
                try:
                    test_func()
                except Exception as e:
                    print(f" Test misslyckades: {e}")
                    return False
                
            return True

        def calibrate_sensors(self):
            """Kalibrera sensorer"""
            print("\n" + "="*60)
            print("SENSORKALIBRERING")
            print("="*60)

            print("\nVARNING: Se till att ingen befinner sig nära maskinen!")
            print("Kalibrerinf kan involvera rörelser och temperaturändringar.")

            confirm = input("\nFortsätta med kalibrering? (j/n): ").lower()
            if confirm != "j":
                print("Kaligrering avbruten")
                return
            
            calibrate_steps = [
                ("Temperatursensorer", self.calibrate_temperature_snsorse),
                ("Robotarm", self.calibrate_robotic_arm),
                ("Inventeriesensorerer", self.caibrate_inventory_sensorers),
            ]

            for step_name, step_func in calibrate_steps:
                print(f"\n▶ Kalibrerar {step_name}...")
                try:
                    step_func()
                    print(f"  ✓ {step_name} kalibrerade")
                except Exception as e:
                     print(f"  ✗ Kalibrering misslyckades: {e}")

            print("\n✓ Alla sensorer kalibrerade")

        def calibrate_temeperatur_sensors(self):
            """Kalibrera temperatur sensorer"""
            if "temperature_manager" in self.components:
                manager = self.components["temperature_manager"]
                manager.calibrate_all_sensors()

        def calibrate_robotic_arm(self):
            """Kalibrera roboticarm"""
            if "robotic_arm" in self.components:
                arm = self.components["robotic_arm"]
                arm.calibrate()

        def calibrate_invnetory_sensors(self):
            """Kalibrera inventeriesensorer"""
            if "inventory_sensor"  in self.components:
                sensor = self.components["inventory_sensor"]
                sensor.calibrate()

        def setup_logging(self):
            """Konfigurera loggning"""
            print("\nKonfigurerar loggning...")

            # Skapa loggmappar om det inte finns
            log_dir = project_root / "logs"
            log_dir.mkdir(exist_ok=True)

            # Skapa setup-loggen
            setup_log_path = log_dir / "setup.log"
            with open(setup_log_path, "a") as f:
                f.write(f"\n{"="*60}\n")
                f.write(f"Setup startad at {datetime.now()}\n")

            print(f"  ✓ Loggmapp: {log_dir}")
            print(f"  ✓ Setup-log: {setup_log_path}")

            return True
        
        def save_configuration(self):
            """Spara systemkonfiguratio"""
            print("\nSparar konfiguration...")

            config_data = {
                "setup_data": datetime.now().isoformat(),
                "components": list(self.components.keys()),
                "test_result": self.test_results,
                "config": self.config.get("hardware", {})
            }

            config_file = self.setup_dir / "hardware_config.json"

            with open(config_file, "w") as f:
                json.dump(config_data, f, indent=2, default=str)
            
            print(f"  ✓ Konfiguration sparad: {config_file}")
            return True
        
        def generate_report(self):
            """Generera installationsrapport"""
            print("\mGenererar installationsrapport...")

            rebort_data = {
                "setup_date": datetime.now.isformat(),
                "system_info": {
                    "python_version": sys.version,
                    "platform": sys.platform,
                    "working_directory": str(project_root)
                },
                "componnents_installed": list(self.components.keys()),
                "test_results": self.test_results,
                "recommendations": self.generate_recommendateions(),
            }

            report_file = self.setup_dir / f"setup_report_{datetime.now().strptime("%Y%m%d_%H%M%S")}.json"

            with open(report_file, "w") as f:
                json.dump(rebort_data, f, indent=2, default=str)

            # Skapa em läsbar sammanfattning
            summary_file = self.setup_dir / "setup_summary.txt"
            with open(summary_file, "w") as f:
                f.write("="*60 + "\n")
                f.write("HAMBURGER MASKIN - INSTALLATIONS RAPPORT\n")
                f.write("="*60 + "\n\n")

                f.write(f"Datum: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n")
                f.write(f"System; {sys.platform} - Python {sys.version}\n\n")

                f.write("INSATLLERADE KOMPONENTER:\n")
                f.write("-" * 40 + "\n")
                for comp in self.components.keys():
                    f.write(f" * {comp}\n")

                f.write("\nTESTRESULTAT:\n")
                f.write("-" * 40 + "\n")
                if self.test_results:
                    for test_name, result in self.test_results.items():
                        status = result.get("status", "OKÄND")
                        f.write(f" {test_name}: {status}\n")
                    else:
                        f.write(" Inga tester utfärda\n")

                    f.write("\nREKOMMENDARIONER:\n")
                    f.write("-" * 40 + "\n")
                    for rec in rebort_data["recommendations"]:
                        f.write(f" * {rec}\n")

            print(f"  ✓ Rapport genererad: {report_file}")
            print(f"  ✓ Sammanfattning: {summary_file}") 

            # Visa sammanfattning
            print("\n" + "-"*60)
            print("INSTALLATIONS SAMMANFATTNING")
            print("="*60)
            with open(summary_file, "r") as f:
                print(f.read())

        def generate_recommendations(self):
            """Generera rekommandtioner basserat på testresultat"""
            recommandation = []

            # Grundläggande rekommendationer
            recommandation.append("Utför regelbundat underhåll varje vecka")
            recommandation.append("Kalibrera sendorer minst en gång per månad")
            recommandation.append("Kontrollera inventeringsnivåer dagligen")

            # Specifika rekommendatiomer baserat på tester
            if self.test_results:
                for test_name, result in self.test_result.items():
                    if result.get("status") == "FAIL":
                        recommandation.append(f"Återgärda problem med {test_name}")

                    # Ytterligare rekommendationer
                    if "temperature_manager" not in self.components:
                        recommandation.append("Inirira temperaturkontroller")
                    if "safety_sensor" not in self.components:
                        recommandation.append("Konfigurera säkerhetssystem")

                    return recommandation

def main():
    """Huvudfunktion"""
    print("Hamburger Machine Hardware Setup")
    print("Version 1.0.0")

    try:
        setup = HardwareSetup()

        # Kontrollera om skriptet körs med argument
        if len(sys.argv) > 1:
            if sys.argv[1] == "--auto":
                setup.automatic_setup()
            elif sys.argv[1] == "--test":
                setup.run_all_test()
            elif sys.argv[1] == "--calibrate":
                setup.calibrate_sensors()
            elif sys.argv[1] == "--report":
                setup.generate_report()
            else:
                print(f"Okänt argument: {sys.argv[1]}")
                print("Tillagängliga argument:")
                print(" --auto  :Kör automatiska installation")
                print(" --test  : Kör alla tester")
                print(" --calibrate :Kalibrera sensorer")
                print("  --report  :Generera rapport")
        else:
            # Interaktivet läge
            setup.run_interactive_setup()
    except KeyboardInterrupt:
        print("\n\nSetup avbruten av användaren")
        sys.exit(0)
    except Exception as e:
        print(f"\nKritiskt fel {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

