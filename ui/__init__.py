"""
Hamburgare Machine - Användargränssnittsmodul

Detta modul innehåller alla UI-kompinenter för hamburgarmaskinen:
- Webbaseratgrännsitt (Flask/Django)
- Lokalt admin-panel (Tkinter)
- Dashboard och övervakningsverktyg
"""

__version__ = "1.0.0"
__author__ = "Hamburger Machine Team"
__all__ = ["web_app", "admin_panel"]

# UI-konstanter
UI_REFRESH_RATE = 1.0 # Sekunder mellan UI-uppdateringar
THEME_PRIMARY = "#FF6B35" # Hamburgarkärnas primärfärg
THEME_SECONDARY = "#1A535C" # Sekundärfärg
THEME_BACKGROUND = "#F7FFF7" # Bakgrunds färg

# UI-tillstånd
class UIState:
    """Håller UI-relaterad tillstånd"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    MAINTENANCE = "maintenance"

# UI-meddelanden
MESSAGES = {
    "welcome": "Välkommen till Hamburger Maskinen",
    "system_ready": "Systemet är redo att ta emot beställningar",
    "maitenance_mode": "Underhållsläge - Ingen beställning möjlig",
    "error_detected": "Fel upptäckt - Kontrollera systemloggar",
    "order_complete": "Beställning klar för hämtning",
    "temperature_warning": "Varning: Temperatur utanför optimalt område",
    "inventory_low": "Varning: Ingrediser låga",
    "payment_success": "Betalning godkänd",
    "patment_failed": "Betalning misslyckades",
    "safety_trigger": "Säkerhetssystem aktiverat",
}

def init_ui():
    """Initerar alla UI-komponenter"""
    from . import logger
    logger.info("Initialiserar UI-komponenter...")

    # Kontrollera beromden
    try:
        # Webb-UI beronen
        import flask
        logger.debug("Flask hittad för webb-UI")
    except ImportError:
        logger.warning("Flask ej installerad - UI kommer inte vara tillgängligt")

    try:
        # Desktop UI beronden
        import tkinter
        logger.debug("Tkinter hittade för desktop-UI")
    except ImportError:
        logger.warning("Tkinter ej tillgängligt - desktop kommer inte vara tillgängligt")

    return True

def get_ui_mode():
    """Retunerar aktuellt UI-läge baserat på konfiguration"""
    from ..utils.congig_loader import load_config

    config = load_config()
    return config.get("ui", {}).get("mode", "web") # "web", "desktop", eller "both"

def validate_ui_config(config):
    """Validera UI-konfiguration"""
    errors = []

    # Validera UI-läge
    valid_modes = ["web", "desktop", "both", "none"]
    if config.get("ui", {}).get("mode") not in valid_modes:
        errors.append(f"Ogiltigt UI-läge.Måste vara ett av {valid_modes}")

    # Valudera portar
    web_config = config.get("ui", {}).get("web", {})
    if web_config.get("enabled", False):
        port = web_config.get("port", 5000)
        if not 1024 <= port <= 65535:
            errors.append(f"Ogiltig webbport: {port}. Måste vara mellan 1024 och 65535")

    return errors

class UIManager:
    """Hanterar flera UI-instanser och koordinerar kommunikation"""

    def __init__(self):
        self.interfaces = {}
        self.active_interface = None
        self.event_handlers = {}

    def register_interface(self, name, interface):
        """Registrera ett UI-gränssnitt"""
        self.interfaces[name] = interface

    def set_active_interface(self, name):
        """Sätter aktiv UI-gränssnitt"""
        if name in self.interfaces:
            self.active_interface = self.interfaces[name]
            return True
        return False
    
    def broadcast_update(self, data):
        """Skickar uppdatering till alla registrerade UI:er"""
        for name, interface in self.interface.items():
            try:
                interface.update(data)
            except Exception as e:
                from . import logger
                logger.error(f"Fel vid uppdatering av UI {name}: {e}")

    def register_event_handler(self, event_type, handler):
        """Registrera händelsehanterare"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    def trigger_event(self, event_type, data=None):
        """Utlöser en händels till alla registrerade hanterare"""
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    handler(data)
                except Exception as e:
                    from . import logger
                    logger.error(f"Fel i händelsehanterare för {event_type}: {e}")
            
# Skapa global UI-manager
ui_manager = UIManager()

# Dekorator för UI-händelser
def ui_event(evnt_type):
    """Dekorator för att registrera funktioner som UI-hädelser"""
    def decorator(func):
        ui_manager.register_event_handler(evnt_type, func)
        return func
    return decorator

# Exportera viktiga funktioner
__all__ = [
    "init_ui",
    "get_ui_config",
    "UIState",
    "MESSAGES",
    "ui_manager",
    "ui_event",
    "UIManager"
]

# Inirering vid import
try:
    init_ui()
    from . import logger
    logger.info("UI-modul initialiserad")
except Exception as e:
    import sys
    print(f"Fel vid initiering av UI-modul: {e}", file=sys.stderr)

