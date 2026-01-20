"""
Inventory Tracker Module
Spåra och hanterar ingrediensinventering för harmburgarmaskin.
"""

import json
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
import sqlite3
from dataclasses import dataclass, asdict
import csv

from utils.logger import get_logger
from utils.config_loader import ConfigLoader


class IngredientType(Enum):
    """Typer av ingredienser."""
    BUNS = "buns"
    PATTY_BEEF = "patty_beef"
    PATTY_VEGAN = "patty_vegan"
    PATTY_CHICKEN = "patty_checken"
    CHEES = "chees"
    LETTUCE = "lettuce"
    TOMATO = "tomato"
    ONION = "onion"
    BACON = "bacon"
    SAUCE_MAYO = "sauce_mayo"
    SAUCE_KETCHUP = "sauce_ketchup"
    SAUCE_MUSTARD = "sauce_mustrad"
    SAUCE_SPECIAL = "sauce_special"
    FRIES = "fries"
    COLD_DRINK = "cold_drink"
    HOT_DRINK = "hot_drink"

class InventoryStatus(Enum):
    """Status för ingresienslager"""
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    CRITICAL_STOCK = "critical_stock"
    OUT_OF_STOCK = "out_of_stock"
    EXPIRED = "expired"

@dataclass
class Ingredient:
    """Dataklass för ingresiensinformation."""
    id: str
    type: IngredientType
    name: str
    quantity: int
    unit: str
    min_threshold: int
    max_capacity: int
    status: InventoryStatus
    location: str # Ex: "dispenser_1", "fridge_2", "freezer_1"
    supplier: str
    batch_number: str
    expiry_date: Optional[datetime]
    last_restock: datetime
    temperature_zone: Optional[float] # För temperatursensitiv ingredienser

    def to_dict(self) -> Dict:
        """Konvnetera till dictionary."""
        data = asdict(self)
        data["type"] = self.type.value
        data["status"] = self.status.value
        if self.expiry_date:
            data["expiry_date"] = self.expiry_date.isoformat()
        data["last_restock"] = self.last_restock.isoformat()
        return data
    
@dataclass
class InventoryTransaction:
    """Dataklass för inventoringstransaktioner."""
    id: str
    ingredient_id: str
    transaction_type: str # "restock", "consumption", "waste", "adjustement"
    quantity_change: str
    previous_quantity: int
    new_quantity: int
    timestamp: datetime
    order_id: Optional[str]
    reason: Optional[str]
    user_id: Optional[str]

    def to_dict(self) -> Dict:
        """Konventera till dictionary."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data
    
class InventoryTracker:
    """
    Huvudklass för inventering.
    Hanterar lagerstatus, automatisk beställning och ingredientsförbrukning.
    """

    def __init__(self, db_path: str = "database/inventory.db"):
        """
        Initiera inventeringsspåren.

        Args:
            db_path: Sökväd till databasen
        """
        self.logger = get_logger(__name__)
        self.config = ConfigLoader().get_invnetory_config()

        self.db_path = db_path
        self._init_database()

        # In-memory cache för snabb återkomst
        self.inventory_cache: Dict[str, Ingredient] = {}
        self.transaction_history: List[InventoryTransaction] = []

        # Lås för trådsäkerhet
        self._lock = threading.RLock()

        # Tråd för automatisk övervakning
        self._monitor_thread = None
        self._monitoring = False

        # Koppling till hardware sensors
        self.sensor_interface = None
        
        self.logger.info("Inventory Tracker initaliserad")

    def _init_database(self) -> None:
        """Initiera databas med tabeller."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Skapa ingredientstabell
            cursor.execute("""
                CRESTE TABLE IF NOT EXISTS ingredients (
                        id TEXT PRIMARY KEY,
                        type TEXT NOT NULL,
                        name TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        unit TEXT NOT NULL,
                        min_threshold INTEGER NOT NULL,
                        min_capacity INTEGER NOT NULL
                        status TEXT NOT NULL,
                        location TEXT NOT NULL,
                        supplier TEXT,
                        batch_number TEXT,
                        expiry_date TEXT,
                        last_restock TEXT NOT NULL,
                        temperature_zone REAL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            # Skapa transktionstabell
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS inventory_transactions (
                           id TEXT PRIMARY KEY,
                           ingredient_id TEXT NOT NULL,
                           transaction_type TEXT NOT NULL,
                           quantity_change INTEGER NOT NULL,
                           previous_quantity INTERGER NOT NULL,
                           new_quantity INTEGER NOT NULL,
                           timestamp TEXT NOT NULL,
                           order_id TEXT,
                            reason TEXT,
                            user_id TEXT,
                            FOREIGN KEY (ingredient_id) REFERENCES ingredients (id)
                        )
                """)
            
            # Skapa beställningshistorik
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS restock_orders (
                            id TEXT PRIMARY KEY,
                           supplier TEXT NOT NULL,
                           ingredient_id TEXT NOT NULL, -- JSON lista med ingredienser
                           total_cost REAL,
                            order_date TEXT NOT NULL,
                            expected_delivery TEXT,
                           atual_delivery TEXT,
                           note TEXT,
                           )
                """)
            
            # Skapa index för snabbare sökningar
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ingredients_status 
                ON ingredients(status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_timestamp
                ON inventory_transactions(timestamp)""")
            
            conn.commit()
            conn.close()

            self.logger.info("Databas initieraserad")
        except sqlite3.Error as e:
            self.logger.error(f"Fel vid databasinitiering: {e}")
            raise

    def start_monitoring(self, interval: int = 60) -> None:
        """
        Starta automatisk övervakning av inventering.

        Args:
            interval: Kontrollintervall i sekunder.
        """
        if self._monitoring:
            self.logger.warning("Övervakning redan igång")
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_inventory, 
            args=(interval,),
            daemon=True,
            name="InventoryMonitor"
            )
        self._monitor_thread.start()
        self.logger.info(f"Inveteringsövervakning startad med {interval}s intervall")

    def stop_monitoring(self) -> None:
        """Stoppa automatisk övervakning."""    
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        self.logger.info("Inventeringsövervakning stoppad")

    def _monitor_loop(self, interval: int) -> None:
        """Huvudloop för automatisk övervakning."""
        while self._monitoring:
            try:
                self.check_inventory_levels()
                self.check_expiry_dates()
                self.check_temperature_zones()
                self.generate_repports()

                time.sleep(interval)


            except Exception as e:
                self.logger.error(f"Fel i övervakningsloop: {e}")
                time.sleep(interval)

    def add_ingredient(self, ingredient: Ingredient) -> bool:
        """
        Lägg till en ny ingrediens i inventeringen.

        Args:
            ingredient: Ingrediensobjekt

        Returns:
            True om lyckad, annars False
        """
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                expiry_str = ingredient.expiry_date.isoformat() if ingredient.expiry_date else None

                cursor.execute("""
                    INSERT INTO ingredients (
                        id, type, name, quantity, unit, min_threshold,
                        max_capacity, status, location, supplier,
                        batch_number, expiry_date, last_restock,
                        temperature_zone
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ingredient.id,
                    ingredient.type.value,
                    ingredient.name,
                    ingredient.quantity,
                    ingredient.unit,
                    ingredient.min_threshold,
                    ingredient.max_capacity,
                    ingredient.status.value,
                    ingredient.location,
                    ingredient.supplier,
                    ingredient.batch_number,
                    expiry_str,
                    ingredient.last_restock.isoformat(),
                    ingredient.temperature_zone
                ))

                conn.commit()
                conn.close()

                # Uppdatera cache
                self.inventory_cache[ingredient.id] = ingredient

                # Lägg transaktion
                transaction = InventoryTransaction(
                    id=f"add_{datetime.now().timestamp()}",
                    ingredient_id=ingredient.id,
                    transaction_type="inital_stock",
                    quantity_change=ingredient.quantity,
                    previous_quantity=0,
                    new_quantity=ingredient.quantity,
                    timestamp=datetime.now(),
                    order_id=None,
                    reason="Initial stock",
                    user_id="system"
                )
                self._log_transaction(transaction)

                self.logger.info(f"Ladda till ingrediens {ingredient.name} ({ingredient.id})")
                return True
            
            except Exception as e:
                self.logger.error(f"Fel vid tillägg av ingrediens: {e}")
                return False
            
    def update_ingredient_quantity(self, 
                                   ingredient_id: str, 
                                   quantity_change: int,
                                   transaction_type: str, 
                                   order_id: Optional[str] = None,
                                   reason: Optional[str] = None,
                                   user_id: str = "system") -> bool:
        """
        Uppdatera ingredienskvantitet (förbrukning, påfyllning).

        Args:
            ingredient_id: ID för ingrediensen
            quantity_change: Förändring i kvantitet (negativ för förbrukning)
            order_id: Order-ID om kopplat till order
            reason: Orsak till förändring
            user_id: Användare som utförde ändringen

        Returns:
            True om lyckad, False annars
        """
        with self._lock:
            try:
                # Hämta nuvarande ingrediens
                ingredient = self.get_ingredient(ingredient_id)
                if not ingredient:
                    self.logge.error(f"Ingrediens {ingredient_id} hittades inte")
                    return False
                
                previous_quantity = ingredient.quantity
                new_quantity = previous_quantity + quantity_change

                # Kontrollera att vi inte får neagtivt lager
                if new_quantity < 0:
                    self.logger.warning(
                        f"Försök att minska {ingredient_id} under 0. "
                        f"Nuvarande: {previous_quantity}, Förändring: {quantity_change}"
                    )
                    new_quantity = 0

                    # Kontrollera maxkapacitet
                    if new_quantity > ingredient.max_capacity:
                        self.logger.warning(
                            f"Försök att överskida maxkapacitet för {ingredient_id}. "
                            f"Max: {ingredient.max_capacity}, Försökt: {new_quantity}"
                        )
                        new_quantity = ingredient.max_capacity

                    # Uppdatera status baserat på en ny kvantitet
                    new_status = self._calculate_status(new_quantity, ingredient.min_threshold)

                    # Uppdatera databasen
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()

                    cursor.execute("""
                        UPDATE ingredients 
                        SET quantity = ?, status = ?, last_updated = ?
                        WHERE id = ?
                    """, (
                        new_quantity,
                        new_status.value,
                        datetime.now().isoformat(),
                        ingredient_id
                    ))

                    conn.commit()
                    conn.close()

                    # Uppdatera cache
                    ingredient.quantity = new_quantity
                    ingredient.status = new_status
                    ingredient.last_restock = datetime.now()
                    self.inventory_cache[ingredient_id] = ingredient

                    # Logga transaktion
                    transaction_type = "restock" if quantity_change > 0 else "consumption"

                    transaction = InventoryTransaction(
                        id=f"txn_{datetime.now().timestamp()}",
                        ingredient_id=ingredient_id,
                        transaction_type=transaction_type,
                        quantity_change=quantity_change,
                        previous_quantity=previous_quantity,
                        new_quantity=new_quantity,
                        timestamp=datetime.now(),
                        order_id=order_id,
                        reason=reason,
                        user_id=user_id
                    )
                    self._log_transaction(transaction)

                    self.logger.info(
                        f"Uppdaterad ingrediens {ingredient_id}: "
                        f"{previous_quantity} -> {new_quantity} ({quantity_change:+d})"
                    )

                    # Utlös event om lågt lager
                    if new_status in (InventoryStatus.LOW_STOCK, InventoryStatus.CRITICAL_STOCK):
                        self._trigger_low_stock_alert(ingredient, new_status)

                    return True
            except Exception as e:
                self.logger.error(f"Fel vid uppdatering av ingredienskvantitet: {e}")
                return False
            
    def consume_ingredients_for_order(self,
                                      order_id: str,
                                      ingredients_required: Dict[str, int],
                                      user_id: str = "system") -> Tuple[bool, Dict[str, str]]:
        """
        Förbruka ingredienser för en order.

        Args:
            order_id: Order-ID
            ingredients_required: Dictionary med ingrediens-ID och kvantitet
            user_id: Användare som utför förbrukningen

        Returns:
            Tuple (success, error_dict)
        """
        with self._lock:
            errors = {}

            # Först kontrollera alla ingredienser finns
            for ingredient_id, quantity in ingredients_required.items():
                ingredient = self.get_ingredient(ingredient_id)
                if not ingredient:
                    errors[ingredient_id] = "Ingrediens hittads inte"
                    continue

                if ingredient.quantity < quantity:
                    errors[ingredient_id] = f"Otillräckligt lager: {ingredient.quantity} < {quantity}"

                # Om det finns fel, retunera dem
                if errors:
                    self.logger.warning(f"Kan inte slutföra order {order_id}: {errors}")
                    return False, errors
                
                # Utför alla förbrukningar
            for ingredient_id, quantity in ingredients_required.items():
                success = self.update_ingredient_quantity(
                    ingredient_id=ingredient_id,
                    quantity_change=-quantity,
                    order_id=order_id,
                    reason=f"Order {order_id}",
                    user_id=user_id
                )

                if not success:
                    errors[ingredient_id] = "Kunde inte uppdatera lager"

            if errors:
                self.logger.warning(f"Fel vid förbrukning för order {order_id}: {errors}")
                return False, errors
            
            self.logger.info(f"Förbrukade ingredienser för order {order_id}")
            return True, {}
        
    def restock_ingredient(self,
                           ingredient_id: str,
                           quantity: int,
                           batch_naumber: Optional[str] = None,
                            expiry_date: Optional[datetime] = None,
                            user_id: str = "admin") -> bool:
                           
        """
        Fyll på lager av en ingrediens.

        Args:
            ingredient_id: ID för ingrediensen
            quantity: Kvantitet att fylla på
            batch_number: Nyt batchnummer (om ny batch)
            expiry_date: Ny utgångsdatum (om ny batch)
            user_id: Användare som utför påfyllning

        Returns:
            True om lyckad, False annars
        """
        with self._lock:
            try:
                ingredient = self.get.ingredient(ingredient_id)
                if not ingredient:
                    self.logger.error(f"Ingrediens {ingredient_id} hittades inte")
                    return False

                # Om ny batch, uppdatera batchinformation
                if batch_naumber:
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()

                    expiry_str= expiry_date.isoformat() if expiry_date else None

                    cursor.execute("""
                        UPDATE ingredients
                        SET batch_number = ?, expiry_date = ?
                        WHERE id = ?
                        """, (
                            batch_naumber, expiry_str, ingredient_id))

                    conn.commit()
                    conn.close()

                    ingredient.batch_number = batch_naumber
                    ingredient.expiry_date = expiry_date
                    self.inventory_cache[ingredient_id] = ingredient

                # Uppdatera kavantitet
                success = self.update_ingredient_quantity(
                    ingredient_id=ingredient_id,
                    quantity_change=quantity,
                    order_id=None,
                    reason="Manual restock",
                    user_id=user_id
                ) 

                if success:
                    self.logger.info(f"Fyllde på {ingredient.name}: +{quantity} {ingredient.unit}")

                return success
            except Exception as e:
                self.logger.error(f"Fel vid påfyllning {e}")
                return False
    
    def get_ingredient(self, ingredient_id: str) -> Optional[Ingredient]:
        """
        Hämta ingrediensinformation.

        Args:
            ingredient_id: ID för ingrediensen

        Returns:
            Ingredient-objekt eller None om inte hittad
        """
        # Första kontrollera cashe
        if ingredient_id in self.inventory_cache:
            return self.inventory_cache[ingredient_id]
        
        # Hämte från databas
        ingredient = self._get_ingredient_from_db(ingredient_id)
        if ingredient:
            self.inventory_cache[ingredient_id] = ingredient

        return ingredient
    
    def _get_ingredient_from_db(self, ingredient_id: str) -> Optional[Ingredient]:
        """Hämta ingrediens från databas."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM ingredients WHERE id = ?", (ingredient_id,))
            row = cursor.fetchone()

            conn.close()

            if not row:
                return None
            
            # Konvertera från databasrad till Ingredient-objekt
            expiry_date = None
            if row["expiry_date"]:
                expiry_date = datetime.fromisoformat(row["expiry_date"])

            ingredient = Ingredient(
                id=row["id"],
                type=IngredientType(row["type"]),
                name=row["name"],
                quantity=row["quantity"],
                unit=row["unit"],
                min_threshold=row["min_threshold"],
                max_capacity=row["max_capacity"],
                status=InventoryStatus(row["status"]),
                location=row["location"],
                supplier=row["supplier"],
                batch_number=row["batch_number"],
                expiry_date=expiry_date,
                last_restock=datetime.fromisoformat(row["last_restock"]),
                temperature_zone=row["temperature_zone"]
            )

            return ingredient
        except Exception as e:
            self.logger.error(f"Fel vid hämtning av ingrediens: {e}")
            return None
        
    def get_all_ingredients(self,
                            filter_status: Optional[InventoryStatus] = None,
                            filter_type: Optional[IngredientType] = None) -> List[Ingredient]:
        """
        Hämta alla ingredienser med optional filtrering.

        Args:
            filter_status: Filtrera på status
            filter_type: Filtrera på typ

        Returns:
            Lista med Ingredient-objekt
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = "SELECT * FROM ingredients WHERE 1=1"
            params = []

            if filter_status:
                query += " AND status = ?"
                params.append(filter_status.value)

            if filter_type:
                query += " AND type = ?"
                params.append(filter_type.value)

            query += " ORDER BY name"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            ingredients = []
            for row in rows:
                expiry_date = None
                if row["expiry_date"]:
                    expiry_date = datetime.fromisoformat(row["expiry_date"])

                ingredient = Ingredient(
                    id=row["id"],
                    type=IngredientType(row["type"]),
                    name=row["name"],
                    quantity=row["quantity"],
                    unit=row["unit"],
                    min_threshold=row["min_threshold"],
                    max_capacity=row["max_capacity"],
                    status=InventoryStatus(row["status"]),
                    location=row["location"],
                    supplier=row["supplier"],
                    batch_number=row["batch_number"],
                    expiry_date=expiry_date,
                    last_restock=datetime.fromisoformat(row["last_restock"]),
                    temperature_zone=row["temperature_zone"]
                )
                ingredients.append(ingredient)

                # Uppdatera cache
                self.inventory_cache[ingredient.id] = ingredient
            return ingredients
        
        except Exception as e:
            self.logger.error(f"Fel vid hämtning av alla ingredienser: {e}")
            return []
        
    def check_inventory_levels(self) -> Dict[str, List[Ingredient]]:
        """
        Kontrollera lagerstatus och flagga låga lagernivåer.

        Returns:
            Dictionary med ingredieser grupperade efter status.
        """
        with self._lock:
            try:
                all_ingredients = self.get_all_ingredients()

                result = {
                    "critical": [],
                    "low": [],
                    "expiring_soon": [],
                    "out_of_stock": []
                }

                for ingredient in all_ingredients:
                    # Uppdatera status baserat på aktuellt kvantitet
                    new_status = self._calculate_status(
                        ingredient.quantity,
                        ingredient.min_threshold
                    )

                    # Om status ändrats, uppdatera
                    if new_status != ingredient.status:
                        ingredient.status = new_status

                    # Uppdatera databas
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE ingredients SET status = ? WHERE id = ?",
                                   (new_status.value, ingredient.id)
                    )
                    conn.commit()
                    conn.close()

                    self.inventory_cache[ingredient.id] = ingredient

                    # Logga statusändring
                    self.logger.warning(
                        f"Statusändring för {ingredient.name}:"
                        f"{ingredient.status.value} -> {new_status.value}"
                    )

                    # Grubbera för rapportering
                    if ingredient.status == InventoryStatus.CRITICAL_STOCK:
                        result["critical"].append(ingredient)
                    elif ingredient.status == InventoryStatus.LOW_STOCK:
                        result["low"].append(ingredient)
                    elif ingredient.status == InventoryStatus.OUT_OF_STOCK:
                        result["out_of_stock"].append(ingredient)

                    # Kontrillera utgångsdatum
                    if ingredient.expiry_date:
                        days_util_expiry = (ingredient.expiry_date - datetime.now()).days

                    if 0 <= days_util_expiry <= self.config.get("expiry_warning_days", 3):
                        result["expiring_soon"].append(ingredient)

                # Utlös varningar om kritiska lager
                if result["critical"]:
                    self._trigger_critical_stock_alert(result["critical"])

                return result
            
            except Exception as e:
                self.logger.error(f"Fel vid kontroll av lagerstatus: {e}")
                return {}
            
    def check_expiry_dates(self) -> List[Ingredient]:
        """
        Kontrollera utgågna ingredienser.

        Returns:
            Lista med utgångna ingredienser.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM ingredients
                WHERE expiry_date IS NOT NULL 
                AND expiry_date < ?
                AND status != "expired"
            """, (datetime.now().isoformat(),))

            rows = cursor.fetchall()
            conn.close()

            expired_ingredients = []

            for row in rows:
                # Uppdatera status till EXPIRED
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE ingredients SET status = ? WHERE id = ?",
                    (InventoryStatus.EXPIRED.value, row["id"])
                )
                conn.commit()
                conn.close()

                # Skapa ingrediensobjekt
                ingredient = self.get_ingredient(row["id"])
                if ingredient:
                    expired_ingredients.append(ingredient)

                # Logga utgången ingrediens
                transaction = InventoryTransaction(
                    id=f"exp_{datetime.now().timestamp()}",
                    ingredient_id=row["id"],
                    transaction_type="waste",
                    quantity_change=row["quantity"],
                    previous_quantity=row["quantity"],
                    new_quantity=0,
                    timestamp=datetime.now(),
                    order_id=None,
                    reason="Expired",
                    user_id="system"
                )
                self._log_transaction(transaction)

                self.logger.warning(
                    f"Ingrediens utgången: {row["name"]} "
                    f"(Batch: {row["batch_number"]}, ID: {row["id"]})"
                )
                return expired_ingredients

        except Exception as e:
            self.logger.error(f"Fel vid kontroll av utgångsdatum: {e}")
            return []
        
    def check_temperature_zones(self) -> Dict[str, List[Dict]]:
        """
        Kontrollera temperatursensorer för kylda/frysta ingredientser.

        Returns:
            Dictionary med temperaturproblem
        """
        if not self.sensor_interface:
            return {}
        
        try:
            temperature_issues = {
                "too_warm": [],
                "too_cold": [],
                "no_signal": []
            }

            ingredients = self.get_all_ingredients()

            for ingredient in ingredients:
                if ingredient.temperature_zone is None:
                    # Hämta aktuell temperatur från sensor
                    current_temp = self.sensor_interface.get_temperature(
                        ingredient.location
                    )

                    if current_temp is None:
                        temperature_issues["no_signal"].append({
                            "ingredient_id": ingredient.id,
                            "location": ingredient.location,
                            "expected_temp": ingredient.temperature_zone
                        })
                        continue

                    # Kontrollera om temperaturen är inom acceptabelt intrevall
                    temp_range = self.config["temperature_zones"].get(
                        ingredient.type.value,
                        {"min": ingredient.temperature_zone -2,
                         "max": ingredient.temperature_zone +2}
                    )

                    if current_temp > temp_range["max"]:
                        temperature_issues["too_warm"].append({
                            "ingredient": ingredient.name,
                            "location": ingredient.location,
                            "current_temp": current_temp,
                            "max_temp": temp_range["max"],
                            "difference": current_temp - temp_range["max"]
                        })

                        self.logger.warning(
                            f"Temperaturarlarm: {ingredient.name} är för varm."
                            f"{current_temp}°C > {temp_range["max"]}°C"
                        )

                    elif current_temp < temp_range["min"]:
                        temperature_issues["too_cold"].append({
                            "ingredient": ingredient.name,
                            "location": ingredient.location,
                            "current_temp": current_temp,
                            "min_temp": temp_range["min"],
                            "difference": temp_range["min"] - current_temp
                        })

                        self.logger.warning(
                            f"Temperaturarlarm: {ingredient.name} är för kall."
                            f"{current_temp}°C < {temp_range["min"]}°C"
                        )

            return temperature_issues
        except Exception as e:
            self.logger.error(f"Fel vid temperaturkontroll: {e}")
            return {}
        
    def generate_repports(self) -> Dict[str, Any]:
        """
        Generera olika inventeringsrapporter.

        Returns:
            Dictionary med rapporter
        """
        try:
            # Hämta data för rapporter
            all_ingredients = self.get_all_ingredients()
            today = datetime.now()
            week_ago = today - timedelta(days=7)

            # Totala värden
            total_value = sum(
                ing.quantity * self.config["ingredient_prices"].get(ing.type.value, 0)

                for ing in all_ingredients
            )

            # Förbrukning senast veckan
            weekly_consumption = self._get_consumption_since(week_ago)

            # Rapportstruktur
            repports = {
                "timestamp": today.isoformat(),
                "summary": {
                    "total_ingredients": len(all_ingredients),
                    "total_value": round(total_value, 2),
                    "out_of_stock": len([i for i in all_ingredients
                                         if i.status == InventoryStatus.OUT_OF_STOCK]),
                    "low_stock": len([i for i in all_ingredients
                                      if i.status == InventoryStatus.LOW_STOCK]),
                    "critical_stock": len([i for i in all_ingredients
                                           if i.status == InventoryStatus.CRITICAL_STOCK])
                },
                "weekly_consumption": weekly_consumption,
                "expiring_soon": self._get_expiring_ingredients(days=7),
                "restock_recommendations": self._get_generations_restock_recommendations(),
                "ingredient_status": [
                    {
                        "id": ing.id,
                        "name": ing.name,
                        "type": ing.type.value,
                        "quantity": ing.quantity,
                        "status": ing.status.value,
                        "location": ing.location
                    }
                    for ing in all_ingredients
                ]
            }

            # Spara rapport till fil
            rapport_filename = f"logs/inventory_report: {today.strftime("%Y%m%d_%H%M")}.json"
            with open(rapport_filename, "w", encoding="utf-8") as f:
                json.dump(repports, f, indent=2, default=str)

            # Generera CSV för export
            self._export_to_csv(all_ingredients)

            self.logger.info(f"Genererade inventeringsrapport: {rapport_filename}")
            return repports
        
        except Exception as e:
            self.logger.error(f"Fel vid generering av rapporter: {e}")
            return {}
        
    def _calculate_status(self, quantity: int, min_threshold: int) -> InventoryStatus:
        """Beräkna lagerstatus baserat på kvantitet och tröskelvärde."""
        if quantity <= 0:
            return InventoryStatus.OUT_OF_STOCK
        elif quantity <= min_threshold * 0.2: # 20% av minsta lagret
            return InventoryStatus.CRITICAL_STOCK
        elif quantity <= min_threshold:
            return InventoryStatus.LOW_STOCK
        else:
            return InventoryStatus.IN_STOCK
        
    def _log_transaction(self, transaction: InventoryTransaction) -> None:
        """Logga en inventeringsransaktion."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
             INSERT INTO inventory_transactions 
            (id, ingredient_id, transaction_type, quantity_change,
            previous_quantity, new_quantity, timestamp, order_id, reason, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transaction.id,
                transaction.ingredient_id,
                transaction.transaction_type,
                transaction.quantity_change,
                transaction.previous_quantity,
                transaction.new_quantity,
                transaction.timestamp.isoformat(),
                transaction.order_id,
                transaction.reason,
                transaction.user_id
            ))

            conn.commit()
            conn.close()

            # Lägg till i minneshistorik (begränsa till 1000 tranaktioner)
            self.transaction_history.append(transaction)
            if len(self.transaction_history) > 1000:
                self.transaction_history.pop(0)

        except Exception as e:
            self.logger.error(f"Fel vid loggning av transaktioner: {e}")

    def _trigger_low_stock_alert(self, ingredient: Ingredient, status: InventoryStatus) -> None:
        """Utlös varning för lågt lager."""
        alert_message = (
            f"{status.value.upper()} VARNING: "
            f"{ingredient.name} har bara {ingredient.quantity} {ingredient.unit} kvar."

            f"Minimum: {ingredient.min_threshold} { ingredient.unit}"
        )

        self.logger.warning(alert_message)

        # Skicka till event bus om det finns
        try:
            from core.event_bus import EventBus
            event_bus = EventBus()
            event_bus.publish("inventory_alert", {
                "ingredient_id": ingredient.id,
                "ingredient_name": ingredient.name,
                "status": status.value,
                "quantity": ingredient.quantity,
                "min_threshold": ingredient.min_threshold,
                "message": alert_message,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            pass # Event bus är inte tillgänglig
    
    def _trigger_critical_stock_alert(self, crtical_ingredients: List[Ingredient]) -> None:
        """Utlös varning för kritiskt lågt lager."""
        if not crtical_ingredients:
            return
        
        alert_message = (
            "KRITISKLÅG LAGER\n"
            "Följande ingredienser måste fyllas på omedelbart:\n"
        )

        for ingredient in crtical_ingredients:
            alert_message += (
                f"- {ingredient.name}: {ingredient.quantity} {ingredient.unit}"
                f"(minimum: {ingredient.min_threshold}\n)"
            )

            self.logger.critical(alert_message)

            # Autimatisk beställning om konfigurerat
            if self.config.get("auto_restock", False):
                self._cretical_restock_order(crtical_ingredients)

    def _cretical_restock_order(self, ingredients: List[Ingredient] ) -> str:
        """
        Skapa automatisk beställning för ingredienser.

        Args:
            ingredients: Lista med ingredienser att beställa

        Returns:
            Order-ID
        """
        try:
            order_id = f"auto_order_{datetime.now().strftime("%Y%m%d%H%M%S")}"

            # Beräkna kvantiteter att beställa
            order_items = []
            total_cost = 0

            for ingredient in ingredients:
                # Beställ upp till 80% av maxkapacitet
                order_quantity = int(ingredient.max_capacity * 0.8) - ingredient.quantity

                if order_quantity > 0:
                    unit_price = self.config["ingredient_prices"].get(
                        ingredient.type.value,
                        0
                    )

                    item = {
                        "ingredient_id": ingredient.id,
                        "name": ingredient.name,
                        "quantity": order_quantity,
                        "unit": ingredient.unit,
                        "unit_price": unit_price,
                        "total_price": order_quantity * unit_price     
                    }

                    order_items.append(item)
                    total_cost += item["total_price"]
            if not order_items:
                self.logger.info("Inga ingredienser att beställa")
                return ""
            
            # Skapa beställning i dtabas
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO restock_orders
                (id, suppler, ingredients, total_cost, status,
                order_date, expected_delivery, notes)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order_id,
                    "Auto Supplier", # Kan göras mer intelligent
                    json.dumps(order_items),
                    total_cost,
                    "padding",
                    datetime.now().isoformat(),
                    (datetime.now() + timedelta(days=2)).isoformat(), # 2 dagars leverans

                    "Automatisk beställning pga lågt lager"
                ))
            
            conn.commit()
            conn.close()

            self.logger.info(
                f"Skapade automatisk beställning {order_id} "
                f"med {len(order_items)} artikelar"
            )

            return order_id
        
        except Exception as e:
            self.logger.error(f"Fel vid skapade av automatisk beställning: {e}")
            return ""

    def _get_consumption_since(self, since_date: datetime) -> Dict[str, int]:
        """Hämta förbrukning sedan ett visst datum."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT ingredient_id, SUM(ABS(quantity_change)) as total_consumed
                FROM inventory_transactions
                WHERE transaction_type = "consumption"
                AND timestamp >= ?
                GROUP BY ingredient_id
            """, (since_date.isoformat(),))

            result = {}
            for row in cursor.fetchall():
                ingredient = self.add_ingredient(row[0])
                if ingredient:
                    result[ingredient.name] = row[1]

            conn.close()
            return result
        except Exception as e:
            self.logger.error(f"Fel vid hämtnig av förbrukning: {e}")
            return {}
        
    def _get_expiring_ingredients(self, days: int = 7) -> List[Dict]:
        """Hämta ingredienser som går ut angivet antal dagar."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            ezpiry_date_limit = (datetime.now() + timedelta(days=days)).isoformat()

            cursor.execute("""
                SELECT * FROM ingredients
                WHERE expiry_date IS NULL
                AND expiry_date <= ?
                AND expiry_date >= ?
                AND status != "expired"
                ORDER BY expiry_date
            """, (ezpiry_date_limit, datetime.now().isoformat()))

            result = []
            for row in cursor.fetchall():
                expiry_date = datetime.fromisoformat(row["expiry_date"])
                days_until = (expiry_date - datetime.now()).days

                result.append({
                    "id": row["id"],
                    "name": row["name"],
                    "quantity": row["quantity"],
                    "batch_number": row["batch_number"],
                    "expiry_date": row["expiry_date"],
                    "days_until_expiry": days_until,
                    "location": row["location"]
                })

                conn.close()
                return result
        except Exception as e:
            self.logger.error(f"Fel vid hämtning av utgånde ingredienser: {e}")
            return []
        
    def _generate_restock_recommendations(self) -> List[Dict]:
        """Generera rekommendationer för påfyllning."""
        recommendations = []

        for ingredient in self.get_all_ingredients():
            if ingredient.status in [InventoryStatus.LOW_STOCK, InventoryStatus.CRITICAL_STOCK]:
                # Beräkna rekommenderad beställningskvalitet
                target_quantity = int(ingredient.max_capacity * 0.8)
                order_quantity = max(0, target_quantity - ingredient.quantity)

                if order_quantity > 0:
                    recommendations.append({
                        "ingredient_id": ingredient.id,
                        "name": ingredient.name,
                        "current_quanity": ingredient.quantity,
                        "min_threshold": ingredient.min_threshold,
                        "recommended_order": order_quantity,
                        "urgency": "high" if ingredient.status == InventoryStatus.CRITICAL_STOCK else "medium",
                        "estimated_cost": order_quantity * self.config["ingredient_prices"].get(ingredient.type.value, 0)
                    })

        return recommendations
    
    def _export_to_cvs(self, ingredients: List[Ingredient]) -> None:
        """Export inventering till CSV-fil."""
        try:
            filename = f"logs/inventory_export_{datetime.now().strftime("%Y%m%d")}.csv"

            with open(filename, "w", newline="", encoding="utf-8") as csvfile:
                fieldnames = [
                    "ID", "Name", "Typ", "Kvantitet", "Enhet",
                    "Minimum", "Max", "Status", "Plats", "Leverantör",
                    "Batch", "Utgångsdatum", "Senast påfyllt", "Temperaturzon"
                ]

                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for ingredient in ingredients:
                    writer.writerow({
                        "ID": ingredient.id,
                        "Name": ingredient.name,
                        "Typ": ingredient.type.value,
                        "Kvantitet": ingredient.quantity,
                        "Enhet": ingredient.unit,
                        "Minimum": ingredient.min_threshold,
                        "Max": ingredient.max_capacity,
                        "Status": ingredient.status.value,
                        "Plats": ingredient.location,
                        "Leverantör": ingredient.supplier,
                        "Batch": ingredient.batch_number,
                        "Utgångsdatum":ingredient.expiry_date.isoformat() if ingredient.expiry_date else "",
                        "Senast påfyllt": ingredient.last_restock.isoformat(),
                        "Temperaturzone": ingredient.temperature_zone or ""
                    })

                self.logger.info(f"Exporterade inventering till {filename}")

        except Exception as e:
            self.logger.error(f"Fel vid CSV-export: {e}")

    def get_inventory_status_summary(self) -> Dict[str, Any]:
        """
        Få en sammanfattning av aktuell lagerstatus.

        Returns:
            Dictiomary med sammanfattning
        """
        all_ingredients = self.get_all_ingredients()

        summary = {
            "total_items": len(all_ingredients),
            "status_counts": {
                "in_stock": 0,
                "low_stock": 0,
                "critikal_stock": 0,
                "out_of_stock": 0,
                "expired": 0,
            },
            "total_value": 0,
            "by_category": {},
            "urgent_actions_needed": []
        }

        for ingredient in all_ingredients:
            # Räkna status
            summary["status_counts"][ingredient.status.value] += 1

            # Beräkna värde
            price = self.config["ingredient_price"].get(ingredient.type.value, 0)
            summary["total_value"] += ingredient.quantity * price

            # Grubbera efter kategori
            category = ingredient.type.value
            if category not in summary["by_category"]:
                summary["by_category"][category] = {
                    "count": 0,
                    "total_quantity": 0,
                    "value": 0
                }

            summary["by_category"][category]["count"] += 1
            summary["by_category"][category]["total_quantity"] += ingredient.quantity
            summary["by_category"][category]["value"] += ingredient.quantity * price

            # Identifera akuta åtgärder
            if ingredient.status == InventoryStatus.CRITICAL_STOCK:
                summary["urgent_actions_needed"].append({
                    "ingredient": ingredient.name,
                    "id": ingredient.id,
                    "expiry_date": ingredient.expiry_date.isoformat() if ingredient.expiry_date else None,
                    "action": "REMOVE_EXPIRED"
                })

            summary["total_value"] = round(summary["total_value"], 2)

            return summary
        
        def cleanup_expired_ingredients(self) -> Tuple[int, float]:
            """
            Rensa bort utgågna ingredienser och beräkna förlust.

            Returns:
                Tuple (antal ingredienser rensade, total förlust i SEK)
            """
            expired_ingredients = self.check_expiry_dates()

            total_loss = 0
            count = 0

            for ingredient in expired_ingredients:
                # Beräkna förlust
                price = self.config["ingredient_prices"].get(ingredient.type.value, 0)
                loss = ingredient.quantity * price
                total_loss += loss

                # Nollställ kvantitet
                self.update_ingredient_quantity(
                    ingredient_id=ingredient.id,
                    quantity_change=-ingredient.quantity,
                    reason="Expired - removed",
                    user_id="system"
                )

                count += 1

                self.logger.info(
                    f"Rensade utgångens: {ingredient.name} "
                    f"(Batch: {ingredient.batch_number}), Förlust: {loss:.2f} SEK"
                )
            return count, total_loss
        
        def connect_sensor_interface(self, sensor_interface: Any) -> None:
            """
            Anslut till temperatursensorinterface.

            Args:
                sensor_interface: Objekt med get_temperature() metod
            """
            self.sensor_interface = sensor_interface
            self.logger.info("Anslöt till temperatursensorinterface")

        def close(self) -> None:
            """Stäng ner inventeringsspåraren på ett säkert sätt."""
            self.stop_monitoring()

            # Spara cache till databas om nödvändigt
            self._save_cache_to_db()

            self.logger.info("Inventory Tracker stängd")

        def _save_cache_to_db(slef) -> None:
            """Spara cache till databas"""
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                for ingredient_id, ingredient in self.inventory_cache.items():
                    cursor.execute("""
                        UPDATE ingredients
                        SET quantity = ?, status = ?, last_restock = ?
                        WHERE id = ?
                    """, (
                        ingredient.quantity,
                        ingredient.status.value,
                        ingredient.last_restock.isoformat(),
                        ingredient_id
                    ))

                conn.commit()
                conn.close()

            except Exception as e:
                self.logger.error(f"Fel vid sparande av cache: {e}")

# Exempel på konfiguration för config.yaml
"""
inventory:
    auto_restock: true
    monitoring_interval: 60
    ingredient_prices:
        buns: 2.50
        patty_beef: 8.00
        patty_vegan: 7.50
        patty_chicken: 6.50
        cheese: 1.20
        lettuce: 0.50
        tomato: 0.80
        onion: 0.40
        pickles: 0.30
        bacon: 3.00
        souce_mayo: 0.20
        souce_ketchup: 0.15
        souce_mustrad: 0.15
        souce_special: 0.35
        fries: 1.50
        nuggets: 5.00
    temperature_zones:
        patty_beef:
            min: -18
            max: -15
        chees:
            min: 2
            max: 8
        lettuce:
            min: 1
            max: 4
        tomato:
            min: 8
            max: 12
"""

if __name__ == "__main__":
    # Exempel på användning
    tracker = InventoryTracker()

    # Lägg till exempelingingredienser
    now = datetime.now()

    ingredients_to_add = [
        Ingredient(
            id="bun_001",
            type=IngredientType.BUNS,
            name="Hamburgerbröd",
            quantity=100,
            unit="st",
            min_threshold=20,
            max_capacity=200,
            status=InventoryStatus.IN_STOCK,
            location="shelf_1",
            batch_number="BUN20240115",
            expiry_date=now + timedelta(days=30),
            last_restock=now,
            temperature_zone=None
        ),
        Ingredient(
            id="beef_001",
            type=IngredientType.PATTY_BEEF,
            name="Nötfärsbiff",
            quantity=50,
            unit="st",
            min_threshold=30,
            max_capacity=150,
            status=InventoryStatus.LOW_STOCK,
            location="freezer_1",
            supplier="Köttgården AB",
            batch_number="BEEF20240110",
            expiry_date=now + timedelta(days=90),
            last_restock=now - timedelta(days=7),
            temperature_zone=-18
        )
    ]

    for ingredient in ingredients_to_add:
        tracker.add_ingredient(ingredient)

    # Starta övervakning
    tracker.start_monitoring(interval=30)

    try:
        # Håll programmet igång
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tracker.stop_monitoring()
        tracker.close()