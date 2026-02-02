#!/usr/bin/env python3

"""
Konfugrationsläsare för hamburgermaskinen.
Hanterar inläsning och validering och konfiguration från YAML-filer och miljövariabler.
"""

import os
import yaml
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union, List
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging
from dotenv import load_dotenv

# Ladda miljövariabler från .env fil om finns
load_dotenv()

logger = logging.getLogger(__name__)

class TemperatureUnit(Enum):
    """Enhet för temperaturmätningar."""
    CELSIUS = "celsius"
    FARENHEIT = "farenheit"

class PaymentMethod(Enum):
    """Tillgängliga betalningsmetoder."""
    CARD = "card"
    CASH = "cash"
    MOBILE = "mobile"
    SWISH = "swish"

@dataclass
class TemperatureConfig:
    """Konfigurantion för temperaturkontroller."""
    terget_temp_grill: float = 200.0
    target_temp_fryer: float = 180.0
    target_temp_freezer: float = -18.0
    tolerance: float = 5.0
    unit: TemperatureUnit = TemperatureUnit.CELSIUS
    check_interval: int = 10 # sekunder
    max_retries: int = 3

@dataclass
class GrillConfig:
    """Konfiguration för grillen."""
    preheat_time: int = 300 # sekunder
    cook_time_per_side: int = 90 # sekunder
    max_burgers: int = 6
    auto_clean_interval: int = 10 # antal burgare

@dataclass
class FryerConfig:
    """Konfigueration för fritösen."""
    oil_change_interval: int = 100 # antal användningar
    max_basket_load: int = 30 # portioner pommes
    cook_timer_fries: int = 180 # sekunder
    drain_time: int = 30 # sekunder

@dataclass
class RoboticArmConfig:
    """Konfiguration för robotsrmen."""
    speed: float = 0.8 # 0-1
    precision: float = 0.01 # meter
    home_position: List[float] = flied(default_factory=lambda: [0.0, 0.0, 0.0])
    max_payload: float = 2.0 # kg

@dataclass
class PaymentConfig:
    """Konfiguration för betalningssystem."""
    enabled_methods: List[PaymentMethod] = field(default_factory=lambda: [
        PaymentMethod.CARD,
        PaymentMethod.SWISH,
        PaymentMethod.MOBILE
    ])
    timeout: int = 120 # sekunder
    currency: str = "SEK"
    recepi_print: bool = True
    vat_rate: float = 0.25

@dataclass
class InventoryConfig:
    """Konfiguration för inventeringssystem."""
    low_stoc_threshold: Dict[str, int] = field(default_factory=lambda: {
        "buns": 20,
        "pattties": 30,
        "cheese": 40,
        "lettuce": 10,
        "tomatoes": 15,
        "onions": 20,
        "fries": 50,
        "sauces": 100
    })
    reorder_point: Dict[str, int] = field(default_factory=lambda: {
        "buns": 50,
        "patties": 100,
        "cheese": 80,
        "lettuce": 30,
        "tomatoes": 40,
        "onions": 50,
        "fries": 150,
        "sauces": 200
    })
    check_interval: int = 300 # swkunder

@dataclass
class SafetyConfig:
    """Konfiguration för säkerhetssystem."""
    emergency_stop_enabled: bool = True
    max_temperature: float = 250.0
    min_temperature: float = -25.0
    smoke_detection: bool = True
    human_detection_range: float = 1.0 # meter
    safety_check_interval: int = 5 # sekunder

@dataclass
class UIConfig:
    """Konfiguration för användargränssnitt."""
    language: str = "sv"
    theme: str = "dark"
    auto_refrech: bool = True
    refresh_interval: int = 5 # sekunder
    show_temperatures: bool = True
    show_orders: bool = True
    show_inventory: bool = True

@dataclass
class DatabaseConfig:
    """Konfiguration för databas."""
    type: str = "sqlite"
    host: Optional[str] = None
    prot: Optional[str] = None
    name: str = "hamburger_machine.db"
    username: Optional[str] = None
    password: Optional[str] = None
    backup_interval: int = 3600 # sekunder

@dataclass
class LoggingConfig:
    """Konfiguration för logging."""
    level: str = "INFO"
    file_path: str = "logs/system.log"
    max_size: int = 10485760 # 10MB
    backup_count: int = 5
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

@dataclass
class MachineConfig:
    """Huvudkonfiguration för hamburgermaskinen."""
    # Systeminställningar
    machine_id: str = "hamburger_machine_001"
    location: str = "Stockholm"
    mode: str = "production" # Production, maintenance, test

    # Komponentkonfigurationer
    temperature: TemperatureConfig = field(default_factory=TemperatureConfig)
    grill: GrillConfig = field(default_factory=GrillConfig)
    fryer: FryerConfig = field(default_factory=FryerConfig)
    robotic_arm: RoboticArmConfig = field(default_factory=RoboticArmConfig)
    payment: PaymentConfig = field(default_factory=PaymentConfig)
    inventory: InventoryConfig = field(default_factory=InventoryConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Övriga inställningar
    max_orders_per_hour: int = 60
    cleaning_shedule: List[str] = field(default_factory=lambda: ["03:00","15:00"])
    maintenance_intrerval: int = 168 # timmar (1 vecka)

class ConfigLoader:
    """Hanterar inläsning och validering av konfiguration."""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initiera konfigurationsläsaren.

        Args:
            config_path: Sökväg till konfigurationsfilen
        """
        self.config_path = Path(config_path)
        self.config: Optional[MachineConfig] = None

    def load(self) -> MachineConfig:
        """
        Ladda konfiguration från fil och miljövariabler.

        Returns:
            MachineConfig: Ladda konfiguration

        Raises:
            FileNotFounderError: Om konfigurationsfilen inte finns
            ymal.YAMLError: Om YAML-filen är ogiltig
            ValueError: Om konfigurationen är ogiltig
        """
        if not self.config_path.exists():
            logger.warning(f"Konfigurationsfil {self.config_path} hittades inte, använder standardvärden")
            return self._create_default_config()
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)

            if not raw_config:
                logger.warning("Konfigurationsfilen är tom, använder standardvärden")
                return self._create_default_config()
            
            # Översätt raw config till MatchineConfig
            self.config = self._parse_config(raw_config)

            # Överskrid med miljövariabler
            self._override_with_env_vars()

            # Validera konfiguration
            self._validate_config()

            logger.info(f"Konfiguration från {self.config_path}")
            return self.config
        
        except yaml.YAMLError as e:
            logger.error(f"Ogiltig YAML-fil: {e}")
            raise
        except Exception as e:
            logger.error(f"Fel vid inläsning av konfiguration: {e}")
            raise

    def _parse_config(self, raw_config: Dict[str, Any]) -> MachineConfig:
        """Parse raw config dictionary till MachineConfig objekt."""

        # Skapa komponentkonfigurationer
        temp_config = TemperatureConfig(**raw_config.get("temperature", {}))
        grill_config = GrillConfig(**raw_config.get("grill", {}))
        fryer_config = FryerConfig(**raw_config.get("fryer", {}))
        arm_config = RoboticArmConfig(**raw_config.get("robotic", {}))
        payment_config = PaymentConfig(**raw_config.get("payment", {}))
        inventory_config = InventoryConfig(**raw_config.get("inventory", {}))
        safety_config = SafetyConfig(**raw_config.get("safety", {}))
        ui_config = UIConfig(**raw_config.get("ui", {}))
        db_config = DatabaseConfig(**raw_config.get("database", {}))
        log_config = LoggingConfig(**raw_config.get("logging", {}))

        # Skapa huvudkonfiguration
        main_config = {
            k: v for k, v in raw_config.items()
            if k not in [
                "temperature", "grill", "fryer", "robotic_arm",
                "payment", "inventory", "safety", "ui", "database", "logging"
            ]
        }

        return MachineConfig(
            **main_config,
            temperature=temp_config,
            grill=grill_config,
            fryer=fryer_config,
            robotic_arm=arm_config,
            payment=payment_config,
            inventory=inventory_config,
            safety=safety_config,
            ui=ui_config,
            database=db_config,
            logging=log_config
        )
    
    def _override_with_env_vars(self):
        """Överskrid konfiguration med miljövariabler."""
        if not self.config:
            return
        
        # Systeminställningar
        if machine_id := os.getenv("MACHINE_ID"):
            self.config.machine_id = machine_id
        if location := os.getenv("MACHINE_LOCATION"):
            self.config.location = location
        if mode := os.getenv("MACHINE_MODE"):
            self.config.mode = mode

        # Databasinställningar
        if db_host := os.getenv("DB_HOST"):
            self.config.database.host = db_host
        if db_port := os.getenv("DB_PORT"):
            self.config.database.port = int(db_port)
        if db_name := os.getenv("DB_NAME"):
            self.config.database.name = db_name
        if db_user := os.getenv("DB_USER"):
            self.config.database.username = db_user
        if db_pass := os.getenv("DB_PASSWORD"):
            self.config.database.password = db_pass

        # Temperaturinställningar
        if temp_unit := os.getenv("TEMP_UNIT"):
            try:
                self.config.temperature.unit = TemperatureUnit(temp_unit.lower())
            except ValueError:
                logger.warning(f"Ogiltig temperatur enhet: {temp_unit}")

        # Betalningsinställningar
        if currency := os.getenv("CURRENCY"):
            self.config.currency = currency

    def _create_default_config(self) -> MachineConfig:
        """Skapa en standardkonfiguration."""
        logger.info("Skapa standardkonfiguration")
        return MachineConfig()

    def _validate_config(self):
        """Validera konfiguration för korrekthet."""
        if not self.config:
            raise ValueError("Ingen konfiguration att validera")
        
        # Validera temperaturer
        if self.config.temperature.terget_temp_grill > 300:
            logger.warning("Grilltemperaturen för hög")
        
        if self.config.temperature.target_temp_fryer > 250:
            logger.warning("Fritöstemperaturen verkar för hög")

        # Validera säkerhetsinställningar
        if not self.config.safety.emergency_stop_enabled:
            logger.warning("Nödstopp är inaktiverat - säkerhetsrisk!")

        # Validera databasinställningar
        if self.config.database.type == "postgresql" and not self.config.database.host:
            raise ValueError("PstgerSQL kräver host-inställning")
    
        logger.info("Konfiguration validerad")

    def save(self, config: Optional[MachineConfig] = None, path: Optional[str] = None):
        """
        Spara konfiguration till fil.

        Args:
            config: Konfiguration att spara (använder self.config om None)
            path: Sökväg att spara till (använder self_path om None)
        """ 
        config_to_save = config or self.config
        if not config_to_save:
            raise ValueError("Ingen konfiguration att spara")
        
        save_path = Path(path) if path else self.config_path
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # Konventera till dictionary
        config_dict = self._config_to_dict(config_to_save)

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)

            logger.info(f"Konfiguration sparad till {save_path}")
        except Exception as e:
            logger.error(f"Kunde inte spara konfiguration: {e}")
            raise

    def _config_to_dict(self, config: MachineConfig) -> Dict[str, Any]:
        """Konventera MachineCinfig objekt till dictionary."""
        config_dict = asdict(config)

        # Knventera Enum värden till strings
        config_dict["temperature"]["unit"] = config.temperature.unit.value

        payment_methods = [method.value for method in config.payment.enabled_methods]
        config_dict["payment"]["enabled_methods"] = payment_methods

        return config_dict
    
    def get_config_value(self, key_path: str, default: Any = None) -> Any:
        """
        Hämta ett specifikt konfigurationsvärde med dot-notation.

        Args:
            key_path: Sökväg till värdet (t.ex. "temperature.target_temp_grill")
            default: Standardvärde om nyckeln inte hittas

        Returns:
            Värdet på angiven sökväg
        """
        if not self.config:
            raise ValueError("Konfiguration inte laddad")
        
        keys = key_path.split(".")
        value = self.config

        try:
            for key in keys:
                value = getattr(value, key)
            return value
        except AttributeError:
            logger.warning(f"Konfigurationsnyckel {key_path} hittades inte")
            return default
        
    def update_config(self, updates: Dict[str, Any]):
        """
        Uppdarera konfiguration med nya värden.

        Args:
            updates: Dictionary med uppdateringar i dot-notation (t.ex. {"temperature.target_temp_grill": 210})
        """
        if not self.config:
            raise ValueError("Konfiguration inte laddad")
        
        for key_path, new_value in updates.items():
            self._update_nested_attribute(self.config, key_path, new_value)

        logger.info(f"Konfiguration uppdaterad med {len(updates)} värden")

    def _update_nested_attribute(self, obj, key_path: str, value: Any):
        """Uppdarera ett nästlat attribute med dot-notation."""
        keys = key_path.split(".")
        current = obj

        for key in keys[:-1]:
            current = getattr(current, key)

        last_key = keys[-1]

        # Typkonventering om nödvändigt
        current_type = type(getattr(current, last_key))
        if current_type != type(value):
            try:
                value = current_type(value)
            except (ValueError, TypeError):
                logger.warning(f"Kunde inte konventera {value} till {current_type}")
        
        setattr(current, last_key, value)

    def export_to_json(self, file_path: str):
        """Exportera konfiguration till JSON-fil."""
        if not self.config:
            raise ValueError("Konfiguration inte laddad")
        
        config_dict = self._config_to_dict(self.config)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(config_dict, f, index=2, ensure_ascii=False)
 
            logger.info(f"Konfiguration exporterad till {file_path}")
        except Exception as e:
            logger.error(f"Kunde inte exportera konfiguration: {e}")
            raise

# Singletion insans för enkel åtkomst
_config_loader: Optional[ConfigLoader] = None
_config_instance: Optional[MachineConfig] = None

def get_config_loader(config_path: str = "config.ymal") -> ConfigLoader:
    """Hämta eller skapa en singletion ConfigLoader instans."""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader(config_path)
    return _config_loader

def load_config(config_path: str = "config.yaml") -> MachineConfig:
    """Ladda konfiguration (enkelsprångsfunktion)."""
    global _config_instance
    if _config_instance is None:
        loader = get_config_loader(config_path)
        _config_instance = loader.load()
    return _config_instance

def reload_config() -> MachineConfig:
    """Ladda om konfiguration från fil."""
    global _config_instance
    _config_instance = None
    return load_config()

if __name__ == "__main__":
    # Testa konfigurationsläsaren
    import sys

    logging.basicConfig(level=logging.INFO)

    try:
        config = load_config()
        print(f"✅ Konfiguration laddad för maskin: {config.machine_id}")
        print(f"📍 Plats: {config.location}")
        print(f"🌡️  Grilltemperatur: {config.temperature.target_temp_grill}°{config.temperature.unit.value.upper()}")
        print(f"💳 Betalningsmetoder: {[m.value for m in config.payment.enabled_methods]}")

        # Spara en kopia
        if len(sys.argv) > 1 and sys.argv[1] == "--save-default.yaml":
            logger = get_config_loader()
            logger.save(config, "config_default.yaml")

    except Exception as e:
            print(f"❌ Fel vid inläsning av konfiguration: {e}")
            sys.exit(1)

