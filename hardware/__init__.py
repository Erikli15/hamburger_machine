"""
Hardware Module Package
-----------------------
Innerhåller alla maskinvarurelaterade komponenter för hamburgermaskinen.
"""

from .temperature import sensor_manager
from .temperature import fritös_controller
from .temperature import grill_controller
from temperature import freezer_controller

from .actuators import robotic_arm
from .actuators import conveyor
from .actuators import dispenser

from .payment import payment_interface
from .payment import card_reader

from .sensors import inventory_sensor
from .sensors import safety_sensor

# Definera vad som ska exporteras som standard
__all__ = [
    # Temperaturmoduler
    "sensor_manager",
    "fritös_controller",
    "grill_controller",
    "freezer_controller",

    # Aktuatormoduler
    "robotic_arm",
    "conveyor",
    "dispenser",

    # Betalninsmoduler
    "payment_interface",
    "card_reader",

    # Sensormoduler
    "inventory_sensor",
    "safety_sensor",
]

# Version av hardware-paketet
__version__ = "1.0.0"