"""
Valideringsmodul för hamburger-automaten.
Hanterar validering av indata, konfiguration, sensorvärden och systemtillstånd.
"""

import re
import json
import yaml
from typing import Any, Dict, List, Optional, Union, Tuple
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import ipaddress
from enum import Enum
import inspect

from utils.logger import get_logger

logger = get_logger(__name__)

class ValidationError(Exception):
    """Anpassa undantag för valideringsfel."""

    def __init__(self, message: str, field: str = None, value: Any = None):
        self.msessage = message
        self.field = field
        self.value = value
        super().__init__(self.msessage)

class TemperatureRanges(Enum):
    """Temperaturintervall för olika enheter."""
    FRYER = (-20, 220) # Celsius
    GRILL = (50, 300)
    FREEZER = (-30, 5)
    AMBIENT = (10, 40)

class ValidationRules:
    """Statisla valideringsregler."""

    # Regex-mönster
    ORDER_ID_PATTER = r"^ORD-\d{8}-\d{6}-\w{4}$"
    INVENTORY_ID_PATTERN = r"^INGR-\w{3}-\d{6}$"
    EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    PHONE_PATTERN = r"^\+?[\d\s\-\(\)]{7,}$"

    # Gränser
    MAX_INGREDIENTS_PER_BURGER = 10
    MAX_BURGER_PER_ORDER = 20
    MAX_ORDER_TOTAL = 1000.00 # SEK
    MIN_PAYMENT_AMOUNT = 10.00 # SEK

    # Tidsbegränsningar
    MAX_ORDER_AGE_MINUTES = 30 # Max tid för att bearbeta en order
    MAX_PREPARATION_TIME_MINUTES = 15

class Validator:
    """Huvudvalideringsklass."""

    @staticmethod
    def validate_not_none(value: Any, field_name: str) -> None:
        """Validerar att värde inte är None."""
        if value is None:
            raise ValidationError(
                f"{field_name} får inte vara None",
                field=field_name,
                value=value
            )
        
    @staticmethod
    def validate_string(value: str, field_name: str, min_length: int = 1, max_length: int = 255, allow_empty: bool = False) -> str:
        """Validerar strängvärden."""
        if value is None:
            raise ValidationError(
                f"{field_name} får inte vara None",
                field=field_name,
                value=value
            )
        
        if not isinstance(value, str):
            raise ValidationError(
                f"{field_name} måste vara en sträng",
                field=field_name,
                value=value
            )
        
        if not allow_empty and len(value.strip()) == 0:
            raise ValidationError(
                f"{field_name} får inte vara tom",
                field=field_name,
                value=value
            )
        
        if len(value) < min_length:
            raise ValidationError(
                f"{field_name} måste vara minst {min_length} tecken",
                field=field_name,
                value=value
            )
        
        if len(value) > max_length:
            raise ValidationError(
                f"{field_name} får inte överstiga {max_length} tecken",
                field=field_name,
                value=value
            )
        
        return value.strip()
    
    @staticmethod
    def validate_interger(value: Any, field_name: str, min_value: int = None, max_value: int = None) -> int:
        """Validerar heltalsvärden."""
        try:
            int_value = int(value)
        except (ValidationError, TypeError):
            raise ValidationError(
                f"{field_name} måste vara ett heltal",
                field=field_name,
                value=value
            )
        
        if min_value is not None and int_value < min_value:
            raise ValidationError(
                f"{field_name} måste vara minst {min_value}",
                field=field_name,
                value=int_value
            )
        
        if max_value is not None and int_value > max_value:
            raise ValidationError(
                f"{field_name} får inte överstiga {max_value}",
                field=field_name,
                value=int_value
            )
        
        return int_value
    
    @staticmethod
    def valideate_float(value: Any, field_name: str, min_value: float = None, max_value: float = None, precision: int = 2) -> float:
        """Validerar flyttalsvärden."""
        try:
            float_value = float(value)
        except (ValidationError, TypeError):
            raise ValidationError(
                f"{field_name} måste vara ett numeriskt värde",
                field=field_name,
                value=value
            )
        
        if min_value is not None and float_value < min_value:
            raise ValidationError(
                f"{field_name} måste vara minst {min_value}",
                field=field_name,
                value=value
            )

        if max_value is not None and float_value > max_value:
            raise ValidationError(
                f"{field_name} får inte översktiga {max_value}",
                field=field_name,
                value=value
            )

        # Använda till specificerad precision
        return round(float_value, precision)
    
    @staticmethod
    def validate_decimal(value: Any, field_name: str, min_value: Decimal = None, max_value: Decimal = None):
        """Validerar decimalvärden (för pengar)."""
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValidationError):
            raise ValidationError(
                f"{field_name} måste vara ett decimaltal",
                field=field_name,
                value=value
            )
        
        if min_value is not None and decimal_value < min_value:
            raise ValidationError(
                f"{field_name} måste vara minst {min_value}",
                field=field_name,
                value=decimal_value
            )
        
        if max_value is not None and decimal_value > max_value:
            raise ValidationError(
                f"{field_name} får inte överstiga {max_value}",
                field=field_name,
                value=decimal_value
            )
        
        return decimal_value

    @staticmethod
    def validate_boolean(value: Any, field_name: str) -> bool:
        """Validerar booleska värden."""
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            if value.lower() in ("true", "1", "yes", "on"):
                return True
            elif value.lower() in ("false", "0", "no", "off"):
                return False

        raise ValidationError(
            f"{field_name} måste vara ett booleskt värde",
            field=field_name,
            value=value
        )
    
    @staticmethod
    def validate_enum(value: Any, field_name: str, enum_clas) -> Enum:
        """Validerar enum-värden."""
        try:
            if isinstance(value, enum_clas):
                return value
            elif isinstance(value, str):
                return enum_clas[value.upper()]
            elif isinstance(value, int):
                return enum_clas(value)
        except (KeyError, ValueError):
            valid_values = [e.name for e in enum_clas]
            raise ValidationError(
                f"{field_name} måste vara en av: {", ".join(valid_values)}",
                field=field_name,
                value=value
            )
        
    @staticmethod
    def validate_list(value: Any, field_name: str, min_items: int = 0, max_items: int = None, item_validator: callable = None) -> List:
        """Validerar listor."""
        if not isinstance(value, list):
            raise ValidationError (
                f"{field_name} måste innehålla minst {min_items} objekt",
                field=field_name,
                value=value
            )
        
        if len(value) < min_items:
            raise ValidationError(
                f"{field_name} måste innehålla minst {min_items} objekt",
                value=value
            )
        
        if max_items is not None and len(value) > max_items:
            raise ValidationError(
                f"{field_name} får inte innehålla fler än {max_items} objekt",
                field=field_name,
                value=value
            )
        
        if item_validator:
            validated_items = []
            for i, item in enumerate(value):
                try:
                    validated_item = item_validator(item, f"{field_name[{i}]}")
                    validated_items.append(validated_item)
                except ValidationError as e:
                    raise ValidationError(
                        f"Ogiltigt objekt i {field_name}: {e.msessage}",
                        field=f"{field_name}[{i}]",
                        value=item
                    )
                
            return validated_items
        
        return value
    
    @staticmethod
    def validate_dict(value: Any, field_name: str, required_keys: List[str] = None, key_validators: Dict[str, callable] = None) -> Dict:
        """Validera dictionaries."""
        if not isinstance(value, dict):
            raise ValidationError(
                f"{field_name} måste vara en dictionary",
                field=field_name,
                value=value
            )
        
        if required_keys:
            missing_keys = [key for key in required_keys if key not in value]
            if missing_keys:
                raise ValidationError(
                    f"{field_name} saknar obligatoriska nycklar: {",".join(missing_keys)}",
                    field=field_name,
                    value=value
                )
            
        if key_validators:
            vlidated_dict = {}
            for key, validator in key_validators.items():
                if key in value:
                    try:
                        vlidated_dict[key] = validator(value[key], f"{field_name}.{key}")
                    except ValidationError as e:
                        raise ValidationError(
                            f"Ogiltigt värde för {key}: {e.msessage}",
                            field=f"{field_name}.{key}",
                            value=value[key]
                        )
                    return vlidated_dict
                
                return value
            
    @staticmethod
    def validate_datetime(value: Any, field_name: str, min_date: datetime = None, max_date: datetime = None) -> datetime:
        """Validera datum/tid-värden."""
        if isinstance(value, str):
            try:
                # Försöka med vanliga format
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%/%m/%Y", "%Y-%m-%d%H:%M%S"):
                    try:
                        dt_value = datetime.strftime(value, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError
            except ValueError:
                raise ValidationError(
                    f"{field_name} har ogiltigt datumformat",
                    field=field_name,
                    value=value
                )
        elif isinstance(value, datetime):
            dt_value = value
        else:
            raise ValidationError(
                f"{field_name} måste vara ett datetime-objekt eller sträng",
                field=field_name,
                value=value
            )
        
        if min_date is not None and dt_value < min_date:
            raise ValidationError(
                f"{field_name} måste vara efter {min_date}",
                field=field_name,
                value=dt_value
            )
        
        if max_date is not None and dt_value > max_date:
            raise ValidationError(
                f"{field_name} måste vara för {max_date}",
                field=field_name,
                value=dt_value
            )
        
        return dt_value
    
    @staticmethod
    def valididate_ip_adress(value: str, field_name: str) -> str:
        """Validerar IP-adress."""
        try:
            ip = ipaddress.ip_address(value)
            return str(ip)
        except ValidationError:
            raise ValidationError(
            f"{field_name} måste vara en giltig IP-adress.",
            field=field_name,
            value=value
        )

    @staticmethod
    def validate_email(value: str, field_name: str) -> str:
        """Validerar e-postaress."""
        value = Validator.validate_string(value, field_name, min_length=3)

        if not re.match(ValidationRules.EMAIL_PATTERN, value):
            raise ValidationError(
                f"{field_name} måste vara en giltig e-postadres",
                field=field_name,
                value=value
            )
        
        return value.lower()

    @staticmethod
    def validate_phone(value: str, field_name: str) -> str:
        """Validerar telefonnummr."""
        value = Validator.validate_string(value, field_name, min_length=5)

        # Ta bort alla icke-numeriska tecken för validering
        digits = re.sub("r\D", "", value)

        if len(digits) < 7:
            raise ValidationError(
                f"{field_name} måste vara ett giltigt telefonnummer",
                field=field_name,
                value=value
            )
        
        return value
    
class BurgerValidators:
    """Valideringar specifika för hamburger-tillverkning."""

    @staticmethod
    def valideate_order_id(order_id: str) -> str:
        """Validerar order-ID."""
        if not re.match(ValidationRules.ORDER_ID_PATTER, order_id):
            raise ValidationError(
                "Order-ID måste följa formatet ORD-YYYYMMDD-HHMMSS-XXXX",
                field="order_id",
                value=order_id
            )
        return order_id
    
    @staticmethod
    def validate_inventory_id(inventory_id: str) -> str:
        """Validerar inventory-ID."""
        if not re.match(ValidationRules.INVENTORY_ID_PATTERN, inventory_id):
            raise ValidationError(
                "Inventorings-ID måste följa formatet INGER-XXX-XXXXXX",
                field="inventory_id",
                value=inventory_id
            )
        return inventory_id
    
    @staticmethod
    def validate_ingredient_amount(amount: Union[int, float], ingredient: str) -> float:
        """Validerar mängd ingrediens."""
        if amount <= 0:
            raise ValidationError(
                f"Mängd av {ingredient} måste vara sörre än 0",
                field=f"ingredients.{ingredient}",
                value=amount
            )
        
        # Maxgränser beroende på ingredienstyp
        max_amounts = {
            "bröd": 2,
            "nötkött": 300, # gram
            "sallad": 100,
            "tomat": 100,
            "lök": 50,
            "ost": 100,
            "bacon": 100,
            "sås": 50,
            "gurka": 50,
            "jalapeno": 30
        }

        ingredient_key = ingredient.lower()
        if ingredient_key in max_amounts and amount > max_amounts[ingredient_key]:
            raise ValidationError(
                f"Mängd av {ingredient} får inte överstiga {max_amounts[ingredient_key]}",
                field=f"ingredients.{ingredient}",
                value=amount
            )
        
        return float(amount)
    
    @staticmethod
    def validate_burger_recipe(recipe: Dict) -> Dict:
        """Validerar ett helt hamburger-recipt."""
        required_ingredients = ["bröd", "nötkött"]

        for ing in required_ingredients:
            if ing not in recipe or recipe[ing] <= 0:
                raise ValidationError(
                    f"Recept måste innehålla {ing}",
                    field=f"recipe.{ing}",
                    value=recipe.get(ing)
                )
            
        if len(recipe) > ValidationRules.MAX_INGREDIENTS_PER_BURGER:
            raise ValidationError(
                f"Recept får inte innehålla fler än {ValidationRules.MAX_INGREDIENTS_PER_BURGER} ingredienser",
                field="recipe",
                value=recipe
            )
        
        validated_recipe = {}
        for ingredient, amount in recipe.items():
            validated_recipe[ingredient] = BurgerValidators.validate_ingredient_amount(amount, ingredient)
            return validated_recipe
        
    @staticmethod
    def validate_order_items(items: List[Dict]) -> List[Dict]:
        """Validerar orderobjekt."""
        if not items:
            raise ValidationError(
                "Order måste innehålla minst em hamburger",
                field="items",
                value=items
            )
        
        if len(items) > ValidationRules.MAX_BURGER_PER_ORDER:
            raise ValidationError(
                f"Order får inte innehålla mer än {ValidationRules.MAX_BURGER_PER_ORDER} hamburgare",
                field="items",
                value=items
            )
        
        validated_items = []
        for i, item in enumerate(items):
            try:
                validated_items = BurgerValidators.validate_burger_recipe(item)
                validated_items.append(validated_items)
            except ValidationError as e:
                raise ValidationError(
                    f"Ogiltig recept i position {i}: {e.msessage}",
                    field=f"items[{i}]",
                    value=item
                )
            
            return validated_items
        
class HardwareValidators:
    """Valideringar för maskinvarukomponenter."""

    @staticmethod
    def validate_temperature(temperature: float, device: str) -> float:
        """validerar temperaturvärde för specifik enhet."""
        try:
            temp_range = TemperatureRanges[device.upper()].value
        except KeyError:
            # Standardintervall för okända enheter
            temp_range = (-50, 400)

        if not (temp_range[0]) <= temperature <= temp_range([1]):
            raise ValidationError(
                f"Temperatur för {device} måste vara mellan {temp_range[0]} och {temp_range[1]}°C",
                field=f"temperature.{device}",
                value=temperature
            )
        
        return round(temperature, 1)
    
    @staticmethod
    def validate_sensor_reading(value: Any, sensore_type: str, excepted_type: type = None) -> Any:
        """Validerar sensorläsning."""
        if value is None:
            raise ValidationError(
                f"Sensoravläsning för {sensore_type} får inte vara None",
                field=f"sensor.{sensore_type}",
                value=value
            )
        
        if excepted_type and not isinstance(value, excepted_type):
            raise ValidationError(
                f"Sensoravläsning för {sensore_type} måste vara av typ {excepted_type.__name__}",
                field=f"sensor.{sensore_type}",
                value=value
            )
        
        return value
    
    @staticmethod
    def validate_actuator_position(position: Dict, actuator: str) -> Dict:
        """Validerar aktuatorposition."""
        required_keys = ["x", "y", "z"]
        for key in required_keys:
            if key not in position:
                raise ValidationError(
                    f"Position för {actuator} saknar {key}-koordinat",
                    field=f"{actuator}.podition.{key}",
                    value=position.get(key)
                )
            
        # Validera koordinatintervall
        limits = {
            "x": (-1000, 1000), # mm
            "y": (-500, 500),
            "z": (0, 300)
        }

        validated_position = {}
        for axis, (min_val, max_val) in limits.items():
            value = position[axis]
            if not (min_val <= value <= max_val):
                raise ValidationError(
                    f"{axis}-koordinat för {actuator} måste vara mellan {min_val} och {max_val}",
                    field=f"{actuator}.podition.{axis}",
                    value=value
                )
            validated_position[axis] = value
        
        return validated_position
    
    @staticmethod
    def validate_payment_amount(amount: float) -> Decimal:
        """Validerar betalningsbelopp."""
        validator = Validator()
        decimal_amount = validator.validate_decimal(
            amount,
            "payment_amount",
            min_value=Decimal(str(ValidationRules.MIN_PAYMENT_AMOUNT)),
            max_value=Decimal(str(ValidationRules.MAX_ORDER_TOTAL))
        )

        # Kontrollera att det är en giltig valuta (max 2 decimaler)
        if decimal_amount.as_tuple().exponent < -2:
            raise ValidationError(
                "Betalningsbelopp får inte ha fler än 2 decimaler",
                field="payment_amount",
                value=decimal_amount
            )
        
        return decimal_amount
    

class ConfigurationValidators:
    """Valideringar för systemkonfiguration."""

    @staticmethod
    def validate_config_structure(config: Dict) -> Dict:
        """Validerar grundläggande konfigurationsstruktur."""
        required_sections = ["system", "hardware", "tenperatures", "timings"]

        for section in required_sections:
            if section not in config:
                raise ValidationError(
                    f"Konfiguration saknar obligstorisk sektion: {section}",
                    field=f"config.{section}",
                    value=None
                )
            
            return config
        
    @staticmethod
    def validate_temperature_config(temps: Dict) -> Dict:
        """Validerar temperaturkonfiguration."""
        validated_temps = {}

        for device, settings in temps.items():
            if not isinstance(settings, dict):
                raise ValidationError(
                    f"Temperautrinstäkkningar för {device} måste vara ett objekt",
                    field=f"temperatures.{device}",
                    value=settings
                )
            
            required_keys = ["target", "tolerance", "max_safe"]
            for key in required_keys:
                if key not in settings:
                    raise ValidationError(
                        f"Temperaturinställningar för {device} saknar {key}",
                        field=f"temperautres.{device}.{key}",
                        value=None
                    )
                
            # Valisera värden
            try:
                validated_temps[device] = {
                    "target": HardwareValidators.validate_temperature(
                        settings["target"], device
                    ),
                    "tolerance": Validator.valideate_float(
                        settings["tolerance"],
                        f"temperatures.{device}.tolerance",
                        min_value=0.1,
                        max_value=20.0
                    ),
                    "max_safe": HardwareValidators.validate_temperature(
                        setattr["max_safe"], device
                    )
                }

                # Kontrollera att max_safe är större än target
                if settings["max_safe"] <= settings["target"]:
                    raise ValidationError(
                        f"max_safe för {device} måste vara större än target",
                        field=f"temperatures.{device}.max_safe",
                        value=settings["max_safe"]
                    )
                
            except ValidationError as e:
                raise e
            
        return validated_temps
    
    @staticmethod
    def validate_timing_config(timings: Dict) -> Dict:
        """Validerar tidskonfiguration."""
        validated_timings = {}

        required_timings = {
            "grill_time": (30, 600), # sekunder
            "fry_time": (120, 900),
            "assembly_time": (10, 300),
            "order_timeout": (60, 3600)
        }

        for timing, (min_val, max_val) in required_timings.items():
            if timing not in timings:
                raise ValidationError(
                    f"Tidskonfiguration saknar: {timing}",
                    field=f"timings.{timing}",
                    value=None
                )
            
            validated_timings[timing] = Validator.validate_interger(
                timings[timing],
                f"timings.{timing}",
                min_value=min_val,
                max_value=max_val
            )

        return validated_timings
    
class DataIntegrityValidators:
    """Valideringar för dataintegritet."""

    @staticmethod
    def validate_inventory_levels(inventory: Dict) -> Dict:
        """Validerar inventeringsnivåer."""
        validate_inventory = {}
        
        for item, level in inventory.items():
            if not isinstance(level, dict):
                raise ValidationError(
                    f"Inventeringsnivå för {item} måste vara ett objekt",
                    field=f"inventory.{item}",
                    value=level
                )
            
            required_keys = ["current", "minimum", "maximum"]
            for key in required_keys:
                if key not in level:
                    raise ValidationError(
                        f"Inventeringspost för {item} saknar {key}",
                        field=f"inventory.{item}.{key}",
                        value=None
                    )
                
            # Validera att minimum <= current <= maximum
            if not (level["minimum"] <= level["current"] <= level["maximum"]):
                raise ValidationError(
                    f"Inventeringsnivå för {item} måste vara mellan minimum och maximum",
                    field=f"inventory.{item}.current",
                    value=level["current"]
                )
            
            validate_inventory[item] = {
                "current": Validator.valideate_float(level["current"], f"inventory.{item}.current", min_value=0),
                "minimum": Validator.valideate_float(level["minimum"], f"inventory.{item}.minimum", min_value=0),
                "maximum": Validator.valideate_float(level["maximum"], f"inventory.{item}.maximum", min_value=level["minimum"])
            }

        return validate_inventory
    
    @staticmethod
    def validate_order_integrity(order: Dict) -> Dict:
        """Validerar orderintegritet."""
        required_fields = ["order_id", "items", "total_amount", "timestamp"]

        for field in required_fields:
            if field not in order:
                raise ValidationError(
                    f"Order saknar obligatoriskt fält: {field}",
                    field=f"order.{field}",
                    value=None
                )
            
        # Validera order-ID
        order["order_id"] = BurgerValidators.valideate_order_id(order["order_id"])

        # Validera items
        order["items"] = BurgerValidators.valideate_order_id(order["items"])

        # Validera totalbolopp
        order["total_amount"] = HardwareValidators.validate_payment_amount(
            order["total_amount"]
        )

        # Validera timestamp
        order["timestamp"] = Validator.validate_datetime(
            order["timestamp"],
            "order.timestamp",
            min_date=datetime.now() - timedelta(days=7), # Max 7 dagar gammal
            max_date=datetime.now() + timedelta(minutes=5) # Max 5 minuter framåt
        )

        return order
    
class SchemaValidator:
    """Validering baserad på JSON Schema."""

    @staticmethod
    def validate_with_schema(data: Any, schema: Dict, data_name: str = "data") -> Any:
        """
        Validerar data mot JSON Schema.
        Förenklad implementering - i produktion, använd ett biblotek som jsonschema.
        """
        if "type" not in schema:
            raise ValidationError(
                "Schema måste innehålla 'type'",
                field="schema",
                value=schema
            )
        
        excepted_type = schema["type"]

        # Typvalidering
        type_validators = {
            "string": lambda x: isinstance(x, str),
            "interger": lambda x: isinstance(x, int),
            "number": lambda x: isinstance(x, (int, float)),
            "boolean": lambda x: isinstance(x, bool),
            "array": lambda x: isinstance(x, list),
            "object": lambda x: isinstance(x, dict),
            "null": lambda x: x is None
        }

        if excepted_type not in type_validators:
            raise ValidationError(
                f"Okänt type i schema: {excepted_type}",
                field=f"{data_name}.schema.type",
                value=excepted_type
            )
        
        if type_validators[excepted_type](data):
            raise ValidationError(
                f"{data_name} måste vara av typ {excepted_type}",
                field=data_name,
                value=data
            )
        
        # ytterligare validering baserat på typ 
        if excepted_type == "string":
            if "minlength" in schema and len(data) < schema["minlength"]:
                raise ValidationError(
                    f"{data_name} måste vara minst {schema['minlength']} tecken",
                    field=data_name,
                    value=data
                )
            
            if "maxlegth" in schema and len(data) > schema["maxlegth"]:
                raise ValidationError(
                    f"{data_name} får inte överstiga {schema['maxlegth']} tecken",
                    field=data_name,
                    value=data
                )
            
            if "pattern" in schema and not re.match(schema["pattern"], data):
                raise ValidationError(
                    f"{data_name} matchar inte det förväntarde mönstet",
                    field=data_name,
                    value=data
                )
        
        elif excepted_type in ["integer", "namber"]:
            if "minimum" in schema and data < schema["minlength"]:
                raise ValidationError(
                    f"{data_name} får inte överstiga {schema['minimum']}",
                    field=data_name,
                    value=data
                )
            
            if "maximum" in schema and data > schema["maximum"]:
                raise ValidationError(
                    f"{data_name} får inte översiga {schema['maximum']}",
                    field=data_name,
                    value=data
                )
            
            elif excepted_type == "arrey":
                if "items" in schema:
                    item_schema = schema["items"]
                    for i, item in enumerate(data):
                        try:
                            SchemaValidator.validate_with_schema(
                                item, item_schema, f"{data_name}[{i}]"
                            )
                        except ValidationError as e:
                            raise ValidationError(
                                f"Ogiltigt element i array: {e.msessage}",
                                field=e.field,
                                value=e.value
                            )
                        
                if "minItems" in schema and len(data) < schema["minItems"]:
                    raise ValidationError(
                        f"{data_name} måste innehålla minst {schema["minItems"]} element",
                        field=data_name,
                        value=data
                    )
                
                if "maxItems" in schema and len(data) > schema["maxItems"]:
                    raise ValidationError(
                        f"{data_name} får inte innehålla fler än {schema["maxItems"]} element",
                        field=data_name,
                        value=data
                    )
                
            elif excepted_type == "object":
                if "properties" in schema:
                    for prop, prop_schema in schema["properties"].items():
                        if prop in data:
                            try:
                                SchemaValidator.validate_with_schema(
                                    data[prop], prop_schema, f"{data_name}.{prop}"
                                )
                            except ValidationError as e:
                                raise e
                
                if "required" in schema:
                    for req_prop in schema["required"]:
                        if req_prop not in data:
                            raise ValidationError(
                                f"{data_name} saknarmobligatorisk egenskap: {req_prop}",
                                field=f"{data_name}.{req_prop}",
                                value=None
                            )
            return data
        
def validate_input(func: callable) -> callable:
    """
    Decorator för att automatiskst validera funktionsargument
    baserat på typannoteringar.
    """
    def wrapper(*args, **kwargs):
        signature = inspect.signature(func)
        bound_args = signature.bind(*args, **kwargs)
        bound_args.apply_defaults()

        for param_name, param in signature.parameters.items():
            if param_name in bound_args.arguments:
                value = bound_args.arguments[param_name]

                # Validera baserat på typannptation
                if param.annotation != inspect.Parameter.empty:
                    except_type = param.annotation

                    # Hantera Optional[]
                    origin = getattr(except_type, "__orgin__", None)
                    if origin is Union:
                        # Kolla om det är Optional (Union[..., None])
                        args = except_type.__args__
                        if len(args) == 2 and type(None) in args:
                            except_type = args[0] if args[1] is type(None) else args[1]

                    # Validera typ
                    if not isinstance(value, except_type):
                        if value is not None or "Optional" not in str(param.annotation):

                            raise ValidationError(
                                f"Parameter {param_name} måste vara av typ {except_type.__name__}",
                                field=param_name,
                                value=value
                            )

            return func(*args, **kwargs)

        return wrapper

# Snabbvalideringsfunktioner för vanliga användningsfel
def quick_validate_order(data: Dict) -> Tuple[bool, str, Optional[Dict]]:
    """Snabbvalidering av orderdata. Returnerar (success, message, validated_data)"""
    try:
        validated = DataIntegrityValidators.validate_order_integrity(data)
        return True, "Order validerad framgångsrikt", validated
    except ValidationError as e:
        logger.warning(f"Ordervalidering misslyckades: {e.msessage}")
        return False, e.msessage, None
    
def quick_validate_temperature(temperature: float, device: str) -> Tulpe[bool, str, Optional[float]]:
    """Snabbvalidering av temperature"""
    try:
        validated = HardwareValidators.validate_temperature(temperature, device)
        return True, f"Temperatur för {device} validerad", validated
    except ValidationError as e:
        logger.warning(f"Temperaturvalidering misslyckades: {e.message}")
        return False, e.msessage, None

def quick_validate_config(config: Dict) -> Tuple[bool, str, Optional[Dict]]:
    """Snabbvalidering av konfiguration. Returnerar (success, message, validated_config)."""
    try:
        validated = ConfigurationValidators.validate_config_structure(config)

        if "temperatures" in config:
            validated["temperatures"] = ConfigurationValidators.validate_temperature_config(
                config["temperatures"]
            )
        
        if "timings" in config:
            validated["timings"] = ConfigurationValidators.validate_temperature_config(
                config["timings"]
            )
        
        return True, "Konfiguration validerad framgångsrikt", validated
    except ValidationError as e:
        logger.error(f"Konfigurationsvalidering misslyckades: {e.msessage}")
        return False, e.msessage, None

# Exceptera huvudsakliga klasser och funktioner
__all__ = [
    "ValidationError",
    "Validator",
    "BurgerValidators",
    "HardwareValidators",
    "ConfigurationValidators",
    "DataIntegrityValidators",
    "SchemaValidators",
    "TemperatureRanges",
    "ValidationRules",
    "validate_input",
    "quick_validate_order",
    "quick_validate_temperature",
    "quick_validate_config"
]

if __name__ == "__main__":
    # Enkel testning av valideringsfunktionerna
    test_order = {
        "order_id": "ORD-20231201-143000-ABCD",
        "items": [
            {"bröd": 2, "nötkött": 150, "ost": 50},
            {"bröd": 2, "nötkött": 200, "sallad": 30, "tomat":40}
        ],
        "total_amount": 199.50,
        "timestamp": datetime.now().isoformat()
    }

    success, message, validated = quick_validate_order(test_order)
    print(f"Test 1 - Ordervalidering: {success}, {message}")

    sucess, message, temp = quick_validate_temperature(180.5, "GRILL")
    print(f"Test 2 - Temperaturvalidering: {success}, {message}")