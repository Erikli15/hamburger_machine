"""
API-paket för hamburgerautomaten.
Hanterar intergerar med externa system med betalningsgateway, kassasystem och sensorer.
"""

from .kiosk_api import KioskAPI
from .payment_api import PaymentAPI
from .external_sensors import ExternalSensors

__all__ = [
    "KioskAPI",
    "PaymentAPI",
    "ExternalSensors"
]

__version__ = "1.0.0"
__author__ = "Hamburger Machin Team"

# Initiering API-instanser
kiosk_api = KioskAPI()
payment_api = PaymentAPI()
external_sensors = ExternalSensors()

# Exportera vanliga funktioner för enkel import
def initialize_apis(config):
    """Initierar alla API-anslutningar"""
    kiosk_api.initialize(config.get("kiosk_api", {}))
    payment_api.initialize(config.get("payment_api", {}))
    external_sensors.initialize(config.get("external_sensors", {}))
    return True

def shutdown_apis():
    """Stänger ner alla API-anslutningar på säkert sätt"""
    kiosk_api.disconnect()
    payment_api.disconnect()
    external_sensors.disconnect()
    return True

def get_api_status():
    """Returnerar status för alla API-anslutningar"""
    return {
        "kiosk_api": kiosk_api.get_status(),
        "payment_api": payment_api.get_status(),
        "external_sensors": external_sensors.get_status()
    }