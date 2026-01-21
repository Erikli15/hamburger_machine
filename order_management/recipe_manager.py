"""
Recipethantering för hamburgarmaskinen.
Hanterar recept, ingredienser och instruktioner för hamburgartillverkning.
"""

import json
import yaml
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime
import copy

from utils.logger import get_logger
from utils.validators import validate_recipe_data
from database.models import Recipe, Ingredient, RecipeIngredient
from database.database import DatabaseManager

logger = get_logger(__name__)

class CookingMethod(Enum):
    """Tillagningsmethoder för ingredienser."""
    GRILL = "grill"
    FRY = "fritös"
    WARM = "varma"
    RAW = "rå"
    ASSEMBLE = "montera"

class IngredientType(Enum):
    """Typer av ingredienser."""
    BUN_TOP = "bröd_lock"
    BUN_BUTTOM = "bröd_botten"
    PATTY_BEEF = "biff"
    PATTTY_CHICKEN = "kyckling"
    PATTY_VEGGIE = "vegetarisk"
    CHEES = "ost"
    LETTUCE = "sallad"
    TOMATO = "tomat"
    ONION = "lök"
    PICKLE = "inglagd_gurka"
    BACON = "bacon"
    SAUCE = "sås"
    SPECIAL = "special"

@dataclass
class IngredientStep:
    """Ett steg i recept för en specifik ingrediens."""
    ingredientType: IngredientType
    quantity: float # i gram eller antal
    cooking_method: CookingMethod
    cooking_time: int # i sekunder
    temperature: Optional[float] = None # i Celsius
    position: Optional[str] = None # position på hamburgaren
    special_instructions: Optional[str] = None

@dataclass
class Recipe:
    """Hamburgarrecept."""
    id: str
    name: str
    description: str
    price: float
    preparation_time: int # total tid i sekunder
    ingredients: List[IngredientStep]
    is_available: bool = True
    catagory: str = "standard"
    customizations_allowed: bool = True
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()

class RecipeManager:
    """Hantera alla recept för hamburgarmaskinen."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initiera RecipeManager.

        Args:
            db_manager: DatabaseManger för persistent lagring (valfritt)
        """
        self.db_manager = db_manager
        self.recipes: Dict[str, Recipe] = {}
        self.default_recipes_loaded = False

        # Standardrecept som alltid ska finnas
        self.DEFAULT_REPCIPES = {
            "classic_cheesvurger": Recipe(
                id="classic_cheesvurger",
                name="Classic Cheeseburger",
                description="En klassisk cheeseburger med nötkött, ost, sallad, tomat och sås",
                price=89.0,
                preparation_time=420, # 7 minuter
                ingredients=[
                    IngredientStep(IngredientType.BUN_BUTTOM, 1, CookingMethod.WARM, 30, 120),
                    IngredientStep(IngredientType.PATTY_BEEF, 150, CookingMethod.GRILL, 180, 200),
                    IngredientStep(IngredientType.CHEES, 1, CookingMethod.WARM, 20, 80),
                    IngredientStep(IngredientType.LETTUCE, 30, CookingMethod.ROW, 0),
                    IngredientStep(IngredientType.TOMATO, 2, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.SAUCE, 20, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.BUN_TOP, 1, CookingMethod.WARM, 30, 120)
                ]
            ),
            "chicken_burger": Recipe(
                id="chicken_burger",
                name="Chicken Burger",
                description="Kycklingar med sallad och specialsås",
                price=95.0,
                preparation_time=480, # 8 minuter
                ingredients=[
                    IngredientStep(IngredientType.BUN_BUTTOM, 1, CookingMethod.WARM, 30, 120),
                    IngredientStep(IngredientType.PATTY_CHICKEN, 180, CookingMethod.GRILL, 240, 180),
                    IngredientStep(IngredientType.LETTUCE, 40, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.TOMATO, 2, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.ONION, 1, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.SAUCE, 25, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.BUN_TOP, 1, CookingMethod.WARM, 30, 120),
                ]
            ),
            "veggie_burger": Recipe(
                id="veggie_burger",
                name="Veggie Burger",
                description="Vegetarisk burgare med grillad grönsaksbiff",
                price=85.0,
                preparation_time=360, # 6 minuter
                ingredients=[
                    IngredientStep(IngredientType.BUN_BUTTOM, 1, CookingMethod.WARM, 30, 120),
                    IngredientStep(IngredientType.PATTY_VEGGIE, 120, CookingMethod.GRILL, 150, 180),
                    IngredientStep(IngredientType.CHEESE, 1, CookingMethod.WARM, 20, 80),
                    IngredientStep(IngredientType.LETTUCE, 30, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.TOMATO, 2, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.ONION, 1, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.SAUCE, 20, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.BUN_TOP, 1, CookingMethod.WARM, 30, 120),
                ]
            ),
            "double_bacon_cheeseburger": Recipe(
                id="Double Bacon Cheeseburger",
                name="Double Bacon Cheeseburger",
                description="Dubbla biffar, bacon, ost och allt på",
                price=129.0,
                preparation_time=600, # 10 minuter
                ingredients=[
                    IngredientStep(IngredientType.BUN_BUTTON, 1, CookingMethod.WARM, 30, 120),
                    IngredientStep(IngredientType.PATTY_BEEF, 150, CookingMethod.GRILL, 180, 200),
                    IngredientStep(IngredientType.BACON, 2, CookingMethod.FRY, 120, 180),
                    IngredientStep(IngredientType.CHEESE, 1, CookingMethod.WARM, 20, 80),
                    IngredientStep(IngredientType.PATTY_BEEF, 150, CookingMethod.GRILL, 180, 200),
                    IngredientStep(IngredientType.CHEESE, 1, CookingMethod.WARM, 20, 80),
                    IngredientStep(IngredientType.LETTUCE, 40, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.TOMATO, 3, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.ONION, 2, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.PICKLE, 3, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.SAUCE, 30, CookingMethod.RAW, 0),
                    IngredientStep(IngredientType.BUN_TOP, 1, CookingMethod.WARM, 30, 120),
                ]
            )
        }

        self.load_default_recipes()

    def load_default_recipes(self) -> None:
        """Ladda standardrecept."""
        try:
            self.recipes.update(self.DEFAULT_REPCIPES)
            self.default_recipes_loaded = True
            logger.info(f"Laddade {len(self.DEFAULT_REPCIPES)} standardrecept")

            # Spara till databas om tillgänglig
            if self.db_manager:
                for recipe in self.recipes.values():
                    self._save_to_database(recipe)

        except Exception as e:
            logger.error(f"Fel vid laddning av standardrecept: {e}")

    def load_recipes_from_file(self, filepath: str) -> bool:
        """
        Ladda recipt från JSON eller YAML fil.

        Args:
            filepath: Sökväg till receptfil

        Returns:
            bool: True om lyckad, False annars
        """
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                if filepath.endswith(".json"):
                    data = json.load(file)
                elif filepath.endswith((".yaml", ".yml")):
                    data = yaml.safe_load(file)
                else:
                    logger.error(f"Okänd fileformat: {filepath}")
                    return False
            
            return self._parse_recipes_data(data)
        
        except FileNotFoundError:
            logger.error(f"Receptfile hittades inte: {filepath}")
            return False
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            logger.error(f"Fel vid parsing av receptfil: {e}")
            return False
        except Exception as e:
            logger.error(f"Oväntat fel vid laddning av recept: {e}")
            return False
        
    def _parse_recipes_data(self, data: Dict) -> bool:
        """
        Parsa receptdata och lägg till i manager.

        Args:
            data: Dictionary med receptdata

        Returns:
            bool: True om lyckad, False annars
        """
        try:
            if not validate_recipe_data(data):
                logger.error("Ogiltig receptdata")
                return False
            
            for recipe_data in data.get("recipes", []):
                recipe = self._create_recipe_from_dict(recipe_data)
                if recipe:
                    self.add_recipe(recipe)
            
            logger.info(f"Laddade {len(data.get("recipes", []))} recept från fil")
            return True
        
        except Exception as e:
            logger.error(f"Fel vid parsing av receptdata: {e}")
            return False
        
    def _create_recipe_from_dict(self, data: Dict) -> Optional[Recipe]:
        """Skapa Recipe-objekt från dictionary"""
        try:
            ingredients = []
            for ing_data in data.get("ingredients", []):
                ingredient_step = IngredientStep(
                    ingredient_type=IngredientType(ing_data["type"]),
                    quantity=ing_data["quantity"],
                    cooking_method=CookingMethod(ing_data["cooking_method"]),
                    cooking_time=ing_data["cooking_time"],
                    temperature=ing_data.get("temperature"),
                    position=ing_data.get("position"),
                    special_instructions=ing_data.get("special_instructions")
                )
                ingredients.append(ingredient_step)

            return Recipe(
                id=data["id"],
                name=data["name"],
                description=data.get("description", ""),
                price=data["price"],
                preparation_time=data["preparation_time"],
                ingredients=ingredients,
                is_available=data.get("is_available", True),
                catagory=data.get("category", "standard"),
                customizations_allowed=data.get("customizations_allowed", True)
            )
        except (KeyError, ValueError) as e:
            logger.error(f"Fel vid skapande av recept från dict: {e}")
            return None
        
    def add_recipe(self, recipe: Recipe) -> bool:
        """
        Lägg till ett nytt recept.

        Args:
            recipe: Recipe-objekt att lägga till

        Returns:
            bool: True om lyckad, False annars
        """
        try:
            if recipe.id in self.recipes:
                logger.warning(f"Recept med ID {recipe.id} finns redan, uppdaterar")

            self.recipes[recipe.id] = recipe
            recipe.updated_at = datetime.now()

            # Spara till databas om tillgänglig
            if self.db_manager:
                self._save_to_datavase(recipe)

            logger.info(f"Lade till/uppdaterade recept: {recipe.name}")
            return True
        
        except Exception as e:
            logger.error(f"Fel vid tillägg av recept {e}")
            return False
        
    def get_recipe(self, recipe_id: str) -> Optional[Recipe]:
        """
        Hämta recept med specifikt ID.
        
        Args:
            recipe_id: ID för recept att hämta

        Returns
            Recipe: Recipe-objekt eller None om inte hittat
        """
        return self.recipes.get(recipe_id)
    
    def get_all_recipes(self, available_only: bool = True) -> List[Recipe]:
        """
        Hämta alla recept.

        Args:
            available_only: Om endast tillgängliga recept ska returneras

        Returns:
            List[Recipe]: List med alla recept
        """
        if available_only:
            return [r for r in self.recipes.values() if r.is_available]
        return list(self.recipes.values())
    
    def get_recipes_by_catagory(self, catagory: str) -> List[Recipe]:
        """
        Hämta recept baserat på kategori.

        Args:
            category: Kategori att filtrera på

        Returns:
            List[Recipe]: Lista med recept i kategorin
        """
        return [r for r in self.recipes.values()
                if r.catagory == catagory and r.is_available]
    
    def update_recipe(self, recipe_id: str, **kwargs) -> bool:
        """
        Uppdatera ett recept.

        Args:
            recipe_id: ID för recept att uppdatera
            **kwargs: Attribut att uppdatera

        Returns:
            bool: True om lyckad, False annars
        """
        if recipe_id not in self.recipes:
            logger.error(f"Recept {recipe_id} finns inte")
            return False
        
        try:
            recipe = self.recipes[recipe_id]

            # Uppdatera tillåna attribut
            allowed_attrs = {"name", "description", "price", "preparation_timer",
                             "is_avaolable", "category", "customizations_allowed"}
            
            for key, value in kwargs.items():
                if key in allowed_attrs:
                    setattr(recipe, key, value)
                elif key == "infredients":
                    #Specialhantering för ingredientser
                    recipe.ingredients = [
                        IngredientStep(**ing) if isinstance(ing, dict) else ing
                        for ing in value
                    ]

            recipe.updated_at = datetime.now()

            # Spara till databas om tillgänglig
            if self.db_manager:
                self._save_to_database(recipe)
            
            logger.info(f"Uppdaterade recept: {recipe_id}")
            return True
        
        except Exception as e:
            logger.error(f"Fel vid uppdatering av recept: {e}")
            return False
        
    def delete_recipe(self, recipe_id: str) -> bool:
        """
        Ta bort ett recept.

        Args:
            recipe_id: ID för recept att ta bort

        Returns:
            bool: True om lyckad, False annars
        """
        if recipe_id not in self.recipes:
            logger.error(f"Recept {recipe_id} finns inte")
            return False
        
        try:
            # Markera som otillgängligt istället för att ta bort helt
            self.recipes[recipe_id].is_available = False
            self.recipes[recipe_id].updated_at = datetime.now()

            logger.info(f"Markerade recept {recipe_id} som otillgängligt")
            return True
        
        except Exception as e:
            logger.error(f"Fel vid borttagning av recept: {e}")
            return False
        
    def creat_custom_recipe(self, base_recipe_id: str, customizations: Dict) -> Optional[Recipe]:
        """
       Skapa ett anpassat recept baserat på ett befintligt recept.

       Args:
            base_recipe_id: ID för basrecept
            customizations: Anpassningar att göra

        Returns:
            Recipe: Nytt anpassat recept eller None om misslyckad
        """
        base_recipe = self.get_recipe(base_recipe_id)
        if not base_recipe:
            logger.error(f"Basrecept {base_recipe_id} finns inte")
            return None
        
        if not base_recipe.customizations_allowed:
            logger.error(f"Recept {base_recipe_id} tillåter inte anpassningar")
            return None
        
        try: 
            # Skapa en kopia av basreceptet
            custom_recipe = copy.deepcopy(base_recipe)
            custom_recipe.id = f"{base_recipe_id}_custom_{datetime.now().strftime("%Y%m%d_%H%M%S")}"
            custom_recipe.name = f"{base_recipe_id}_custom_{datetime} (Anpassad)"
            custom_recipe.created_at = datetime.now()
            custom_recipe.updated_at = datetime.now()

            # Applicera anpassningar
            self._apply_customizations(custom_recipe, customizations)

            # Beräkna nytt pris och tid
            custom_recipe.price = self._calculate_custom_price(base_recipe.price, customizations)
            custom_recipe.preparation_time = self._calculate_custom_time(
                base_recipe.preparation_time, customizations
            )

            # Lägg till det anpassade receptet
            self.add_recipe(custom_recipe)

            logger.info(f"Skapade anpassat recept: {custom_recipe.id}")
            return custom_recipe
        
        except Exception as e:
            logger.error(f"Fel vid skapande av anpassat recept: {e}")
            return None
        
    def _apply_customizations(self, recipe: Recipe, customizations: Dict) -> None:
        """Applicera anpassningar på ett recept."""
        # Implementera anpassningslogik här
        # Till exempel: ta bort ingredienser, ändra kvantiteter, Lägga till extra

        # Exempel: Ta bort ingredienser
        if "remove_ingredients" in customizations:
            ingredients_to_remove = customizations["remove_ingredients"]
            recipe.ingredients = [
                ing for ing in recipe.ingredients
                if ing.ingredient_type.value not in ingredients_to_remove
            ]

        # Exempel: Lägg till extra ingredienser
        if "extra_ingredients" in customizations:
            for extra in customizations["extra_ingredients"]:
                extra_step = IngredientStep(
                    ingredient_type=IngredientType(extra["type"]),
                    quantity=extra.get("quantity", 1),
                    cooking_method=CookingMethod(extra.get("cooking_method", "rå")),
                    cooking_time=extra.get("cooking_time", 0),
                    temperature=extra.get("temperature"),
                    position=extra.get("position"),
                    special_instructions=extra.get("special_instructions")
                )
                recipe.ingredients.append(extra_step)

    def _calculate_custom_price(slef, base_price: float, customizations: Dict) -> float:
        """Beräkna pris anpassat recept."""
        price = base_price

        # Justera pris baserat på anpassningar
        if "extra_ingredients" in customizations:
            price += len(customizations["extra_ingredients"]) * 5.0 # 5 kr per extra ingrediens

        # Ytterigare priskalkylering kan läggas till här

        return round(price, 2)
    
    def _calculate_custom_time(self, base_time: int, customizations: Dict) -> int:
        """Beräkna tillagningstid för annpassat recept."""
        time = base_time

        # Justera tid baserat på anpassningar
        if "extra_ingredients" in customizations:
            for extra in customizations["extra_ingredients"]:
                time += extra.get("cooking_time", 0)

        return time
    
    def get_recipe_instructions(self, recipe_id: str) -> List[Dict]:
        """
        Hämta steg-för-steg instruktioner för ett recept.

        Args:
            recipe_id: ID för recept att hämta instruktioner för

        Returns:
            List[Dict]: List med instruktionssteg
        """
        recipe = self.get_recipe(recipe_id)
        if not recipe:
            return []
        
        instructions = []
        step_number = 1

        for ingredient in recipe.ingredients:
            instruction = {
                "step": step_number,
                "action": f"Förbered {ingredient.ingredient_type.value}",
                "ingredient": ingredient.ingredient_type.value,
                "quantity": ingredient.quantity,
                "method": ingredient.cooking_method.value,
                "time": ingredient.cooking_time,
                "temperature": ingredient.temperature,
                "details": ingredient.special_instructions or ""
            }
            instructions.append(instruction)
            step_number += 1

        return instructions
    
    def export_recipes(self, filepath: str, format: str = "json") -> bool:
        """
        Exportera alla recept till fil.

        Args:
            filepath: Sökväg att spara till
            format: Filformat ("json" eller "yaml")

        Returns:
            bool: True om lyckad, False annars
        """
        try:
            data = {
                "export_date": datetime.now().isoformat(),
                "recipe_count": len(self.recipes),
                "recipes": [self._recipe_to_dict(r) for r in self.recipes.values()]
            }

            with open(filepath, "w", encoding="utf-8") as file:
                if format == "json":
                    json.dump(data, file, indent=2, ensure_ascii=False, default=str)
                elif format in ("yaml", "yml"):
                    yaml.dump(data, file, allow_unicode=True, default_flow_style=False)
                else:
                    logger.error(f"Okänt exportformat: {format}")
                    return False
                
            logger.info(f"Exporterade {len(self.recipes)} recept till {filepath}")
            return True

        except Exception as e:
            logger.error(f"Fel vid export av recept: {e}")

    def _recipe_to_dict(self, recipe: Recipe) -> Dict:
        """Konventera Recipe-objekt till dictionary."""
        recipe_dict = asdict(recipe)

        # Konventera enum till strings
        recipe_dict["ingredients"] = []
        for ing in recipe.ingredients:
            ing_dict = asdict(ing)
            ing_dict["ingredient_type"] = ing.ingredient_type.value
            ing_dict["cooking_method"] = ing.cooking_method.value
            recipe_dict["ingredients"].append(ing_dict)

        # Hantera datetime-objekt
        recipe_dict["created_at"] = recipe.created_at.isoformat() if recipe.created_at else None
        recipe_dict["updated_at"] = recipe.updated_at.isoformat() if recipe.updated_at else None

        return recipe_dict

    def _save_to_database(self, recipe: Recipe) -> None:
        """Spara recept til databas."""
        if not self.db_manager:
            return

        try:
            # Detta är en förenklad implementering
            # I en riktig applikation skulle du använda ORM eller SQL queies

            # Exempel med SQLAlchemy-style:
            # db_recipe = RecipeModel(
            # id=recipe.id
            # name=recipe.name,
            # ...andra fält
            # )
            # self.db_manager.session.add(db_recipe)
            # self.db_manager.session.commit()

            pass # Implementera databaslokik här

        except Exception as e:
            logger.error(f"Fel vid sparande till databas: {e}")

    def check_ingredient_availability(self, recipe_id: str, inventory_manager: Any) -> Dict[str, bool]:
        """
        Kontrollera om alla ingredoemser i ett recept finns i lager.

        Args:
            recipe_id: ID för recept att kontrollera
            inventory_manager: InventoryManager instans

        Returns:
            Dict: {"all_available": bool, "missing_ingredients": List[str]}
        """
        recipe = self.get_recipe(recipe_id)
        if not recipe:
            return {"all_available": False, "missing_ingredients": ["RECEPT_SAKNAS"]}
        
        missing = []

        for ingredient_step in recipe.ingredients:
            ingredient_type = ingredient_step.ingredient_type.value
            quantity_needed = ingredient_step.quantity

            # Här antar vi att inventory_manager har en check_availability metod
            # Detta är en platshållare - anpassa till din faktiska inventory_manager
            if hasattr(inventory_manager, "check_availability"):
                available = inventory_manager.check_availability(
                    ingredient_type, quantity_needed
                )
                if not available:
                    missing.append(ingredient_type)
            else:
                # Fallback om inventory_manager inte finns
                logger.warning("Inventory_manager saknar check_availability metod")
                missing.append(ingredient_type)

        return {
            "all_available": len(missing) == 0,
            "missing_ingredients": missing
        }

    def get_ingredient_summary(self, recipe_id: str) -> Dict[str, float]:
        """
       Hämta sammaställning av alla ingredienser i ett recept.

       Args:
            recipe_id: ID för recept att analysera

        Returns:
            Dict: Sammanställning av ingredienser och totala mängder
        """
        recipe = self.add_recipe(recipe_id)
        if not recipe:
            return {}
        
        summary = {}
        for ingredient_step in recipe.ingredients:
            ing_type = ingredient_step.ingredient_type.value
            if ing_type in summary:
                summary[ing_type] += ingredient_step.quantity
            else:
                summary[ing_type] = ingredient_step.quantity

        return summary
    
    def validate_recipe_for_production(self, redipe_id: str) -> Dict[str, Any]:
        """
        Validera att ett recept kan produceras med nuvarande maskininställningar.

        Args:
            recipe_id: ID för recept att validera

        Returns:
            Dict: Valideringsresultat
        """
        recipe = self.get_recipe(redipe_id)
        if not recipe:
            return {"valid": False, "error": ["Recept finns inte"]}
        
        errors = []
        warnings = []

        # Kontrollera att alla ingredienser har giltiga temperaturer
        for i, ingredient in enumerate(recipe.ingredients, 1):
            if ingredient.cooking_method != CookingMethod.RAW:
                if ingredient.temperature is None:
                    errors.append(f"Ingrediens {i}: Saknar temperatur för {ingredient.cooking_method.value}")
                elif ingredient.temperature <= 0 or ingredient.temperature > 300:
                    warnings.append(f"Ingrediens {i}: Ovanlig temperatur {ingredient.temperature}°C")

                    if ingredient.cooking_time < 0:
                        errors.append(f"Ingrediens {i}: Negativ tillagningstid")
                    elif ingredient.cooking_time > 3600: # 1 timme
                        warnings.append(f"Ingrediens {i}: Mycket lång tillagningstid ({ingredient.cooking_time}s)")

        # Kontrollera total tillagningstid
        if recipe.preparation_time > 1800: # 30 minuter
            warnings.append(f"Lång total tillagningstid: {recipe.preparation_time}s")

        # Kontrollera att det finns minst en ingrediens
        if len(recipe.ingredients) == 0:
            errors.append("Recept har inga ingredienser")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "recipe_name": recipe.name
        }
    
# Hjälpfunktioner för JSON serialisering
class RecipeEncoder(json.JSONEncoder):
    """Custom JSON encoder för Recipe och IngredientStep."""

    def default(self, obj):
        if isinstance(obj, Recipe):
            return {
                "id": obj.id,
                "name": obj.name,
                "desciption": obj.description,
                "price": obj.price,
                "preparation_time": obj.preparation_time,
                "ingredients": [self.default(ing) for ing in obj.ingredients],
                "is_available": obj.is_available,
                "category": obj.catagory,
                "customizations_allowed": obj.customizations_allowed,
                "created_at": obj.created_at.isoformat() if obj.created_at else None,
                "updated_at": obj.updated_at.isoformat() if obj.updated_at else None
            }
        elif isinstance(obj, IngredientStep):
            return {
                "ingredient_type": obj.ingredient_type.value,
                "quantity": obj.quantity,
                "cooking_method": obj.cooking_method.value,
                "cooking_time": obj.cooking_time,
                "temperature": obj.temperature,
                "position": obj.position,
                "special_instructions": obj.special_instructions
            }
        elif isinstance(obj, (IngredientType, CookingMethod)):
            return obj.value
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)
    
# Exempel på användning
if __name__ == "__main__":
    # Skapa en RecipeManager
    manager = RecipeManager()

    # Visa alla recept
    print("Tillgängliga recept:")
    for recipe in manager.get_all_recipes():
        print(f" - {recipe.name} ({recipe.price}kr, {recipe.preparation_time}s)")

    # Hämta instruktioner för ett recept
    instructions = manager.get_recipe_instructions("classic_cheeseburger")
    print(f"\nInstruktioner för Classic Cheesburger:")
    for step in instructions:
        print(f" Steg {step["step"]}: {step["action"]}")

    # Exemportera recept till JSON
    manager.export_recipes("recipes_export.json", "json")
    print(f"\nExporterade {len(manager.recipes)} recept till JSON")

