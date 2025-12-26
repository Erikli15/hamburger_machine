#!/usr/bin/env python3
"""
Hamburger Maskin - Huvudstartfil
Automatiserad hamburgertillvekninsmaskin
Version 1.0.0
"""

import sys
import os
import signal
import time
from pathlib import Path

# Lägg till projektets root i Python-sökvägen
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.logger import setup_logger
from utils.config_loader import ConfigLoader
from core.controller import MachineController
from core.state_manager import SystemState
from core.safety_monitor import SafetyMonitor
from ui.admin_panel import AdminPanel
from database.database import DatabaseManager
from hardware.sensors.safety_sensor import EnergencyStopMonitor

class HamburgerMachine:
    """Huvudklass maskinen"""

    def __init__(self):
        """Initiera maskinen"""
        self.logger = setup_logger(__name__)
        self.config = None
        self.controller = None
        self.state_manager = None
        self.safety_monitor = None
        self.admin_panel = None
        self.database = None
        self.emergency_stop = None
        self.running = False

        # Registrera signalhanterare för korrekt avslut
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Hantera avslutssignaler"""
        self.logger.info(f"Mottagen signal {signum}, avslutar maskinen...")
        self.shutdown()

    def initialize(self):
        """Initiera alla systemkomponenter"""
        try:
            self.logger.info("=" * 50)
            self.logger.info("Startar Hamburgermaskin System")
            self.logger.info("=" * 50)

            # 1. Ladda konfiguration
            self.logger.info("Läser konfiguration...")
            self.config = ConfigLoader.load_config()

            # 2. Initiera databas
            self.logger.info("Initierar databas...")
            self.database = DatabaseManager(self.config["database"])
            self.database.initialize()

            # 3. Initiera systemtillstånd
            self.logger.info("Initierar systemtillstånd...")
            self.state_manager = SystemState()

            # 4. Initiera nödstopp
            self.logger.info("Initierar säkerhetsövervakning...")
            self.safety_monitor = SafetyMonitor(self.state_manager)

            # 5. Initiera nödstopp
            self.logger.info("Initierar nödstoppssystem...")
            self.emergency_stop = EnergencyStopMonitor(self.safety_monitor)
            self.emergency_stop.start_monitoring()

            # 6. Initiera huvudkontroller
            self.logger.info("Initerar maskinkontroller...")
            self.controller = MachineController(
                config=self.config,
                state_manager=self.state_manager,
                safety_monitor=self.safety_monitor,
                database=self.database
            )

            # 7. Startar kontroller
            self.controller.start()

            # 8. Initiera admin-panel (om aktiverat)
            if self.config.get("ui", {}).get("enable_admin_panel", False):
                self.logger.info("Startar admin-panel...")
                self.admin_panel = AdminPanel(
                    controller=self.controller,
                    state_manager=self.state_manager
                )
                self.admin_panel.start()

            # 9. Starta webbserver (om aktiverat)
            if self.config.get("ui", {}).get("enable_web_ui", False):
                self.logger.info("Startar webbgränssnitt...")
                self.start_web_ui()

                self.running = True
                self.logger.info("✅ Systemet är startat och klart!")

                # Skriv startinformation till loggen
                self.log_startup_info()

        except Exception as e:
            self.logger.error(f"Fel vid initering: {str(e)}", exc_info=True)
            self.shutdown()
            raise

    def start_web_ui(self):
        """Starta webbgränssnittet"""
        try:
            from ui.web_app.app import create_app
            app = create_app(self.controller, self.state_manager)

            # Startar i sepparat tråd eller process baserat på konfiguration
            host = self.config["ui"].get("web_host", "0.0.0.0")
            port = self.config["ui"].get("web_port", 5000)
            debug = self.config["ui"].get("debug", False)

            import threading
            web_thread = threading.Thread(
                target=app.run,
                kwargs={"host": host, "port": port, "debug": debug, "use_reloder": False},
                daemon=True
            )
            web_thread.start()
            self.logger.info(f"Webbgränssnitt startat på http://{host}:{port}")

        except ImportError as e:
            self.logger.warning(f"Kunde inte starta webbgränddnitt: {e}")
        except Exception as e:
            self.logger.error(f"Fel vid start av webbgränssnitt: {e}")
    
    
    def log_startup_info(self):
        """Logga startinformation"""
        self.logger.info("\n" + "="*50)
        self.logger("SYSTEMINFORMATION")
        self.logger.info("="*50)
        self.logger.info(f"Systemstatus: {self.state_manager.get_state()}")
        self.logger.info(f"Temperaturövervakning: {"AKTIV" if self.config["hardware"]["temperature"]["enabled"] else "INAKTIV"}")
        self.logger.info(f"Robertarm: {"AKTIV" if self.config["hardware"]["actuators"]["robotic_arm"]["enabled"] else "INAKTIV"}")
        self.logger.info(f"Betalingssystem: {"AKTIV" if self.config["harware"]["payment"]["enabled"] else "INAKTIV"}")
        self.logger.info("="*50 + "\n")

    def run(self):
        """Huvudkörningsloop"""
        try:
            while self.running:
                # Huvudloop för att hålla programmet igång
                time.sleep(1)

                # Periodiska kontroller och uppdateringar
                self.periodic_checks()

                # Uppdatera systemstatus
                current_state = self.state_manager.get_state()
                if current_state.get("emergency_stop"):
                    self.logger.warning("NÖDSTOPP AKTIVERAT! Väntar på återställning...")
                    self.handle_emergency_stop()

        except KeyboardInterrupt:
            self.logger.info("Avdlutas via tangentbord...")
        except Exception as e:
            self.logger.error(f"Oväntat fel i huvudloop: {e}", exc_info=True)
        finally:
            self.shutdown()

    def periodic_checks(self):
        """Utför periodiska systemkontroller"""
        # Denna metod kan expanderas för regelbundna kontroller
        pass

    def handle_emergency_stop(self):
        """Hantera nödstoppsituation"""
        # Pausa alla operationer
        self.controller.pause_operations()

        # Vänta på att nödstoppet återställs
        while self.state_manager.get_state().get("emergency_stop"):
            time.sleep(0.5)

        # Återuppta operationer
        self.logger.info("Nödstopp återställt, återupptar operationer...")
        self.controller.resume_operations()

    def shutdown(self):
        """Stäng av systemet på ett säkert sätt"""
        if not self.running:
            return
        
        self.logger.info("Inleder säker avstängning...")
        self.running = False

        try:
            # 1. Stoppa alla operationer
            if self.controller:
                self.controller.stop()

            # 2. Stoppa nödstoppsövervakning
            if self.emergency_stop:
                self.emergency_stop.stop_monitoring()

            # 3. stäng admin-panel
            if self.admin_panel:
                self.admin_panel.stop()

            # 4. Säkerställ att alla hårdvarukomponenter är i sälert läge
            self.safe_hardware_shutdown()

            # 5. Stäng databasanslutningar
            if self.database:
                self.database.close()

            self.logger.info("✅ Systemet har avslutats säkert.")

        except Exception as e:
            self.logger.error(f"Fel vid avstängning: {e}")
        finally:
            self.logger.info("="*50)
            self.logger.info("Hamburgermaskin AVSLUTAD")
            self.logger.info("="*50)
    
    def safe_hardware_shutdown(self):
        """Säkerställ att all hårdvara är i säkert läge"""
        try:
            self.logger.info("Stänger ner hårdvara på ett säkert sätt...")

            # Stäng av värmesystem
            from hardware.temperature.fritös_controller import FritösController
            from hardware.temperature.grill_controller import GrillController

            fritös = FritösController()
            grill = GrillController()

            fritös.set_temperature(0)
            grill.set_temperature(0)

            # Stoppa transportband
            from hardware.actuators.conveyor import Conveyor
            conveyor = Conveyor
            conveyor.stop()

            # Återställ robotarm
            from hardware.actuators.robotic_arm import RoboticArm
            arm = RoboticArm()
            arm.return_to_home()

            self.logger.info("✅ Hårdvara i säkert läge.")

        except Exception as e:
            self.logger.warning(f"Varning vid hårdvaruavstängning: {e}")

    def main():
        """Huvudfunktion"""
        machine = HamburgerMachine()

        try:
            # Initiera och starta maskinen
            machine.initialize()

            # Kör huvudloop
            machine.run()

        except Exception as e:
            print(f"Kritiskt fel: {e}")
            sys.exit(1)

        return 0
    if __name__ == "__main__":
        # Kontrollera Python-version
        if sys.version_info < (3, 8):
            print("Fel: Kräver Python 3.8 eller senare")
            sys.exit(1)

        # Kontrollera att vi kör som root om det behöves för GPIO/privilegier
        if os.name != "nt" and os.geteuid() != 0:
            print("Varning: Det rekomenderas att köra som root för hårdvaruåtkomst")

        # Starta prograSmmet
        exit_code = main()
        sys.exit(exit_code)
