"""
Databasmodeller för Hamburgermaskinen.
Definierar alla databasmodeller och deras relationer.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Enum as SQLEnum, Text, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
import logging

# Konfiguratiom
DATABASE_URL = "sqlite:///hamburger_machine.db" # Ändra för produktion tiik PostgreSQL/MySQL
Base = declarative_base()
logger = logging.getLogger(__name__)

# Enum-definitioner
class OrderStatus(str, Enum):
    """Status för en order."""
    RECEIVED = "received"
    PROCESSING = "processing"
    COOKING = "cooking"
    ASSEMBLING = "assembling"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    FAILED = "failed"

class PaymentMethod(str, Enum):
    """Betalingsmetoder."""
    CARD = "card"
    CASH = "cash"
    MOBILE = "mobile"
    FREE = "free" # För test eller specialfall

class TemperatureUnit(str, Enum):
    """Temperatur-enheter."""
    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"

class IngredientType(str, Enum):
    """Typer av ingredienser."""
    BUN = "bun"
    PATTY = "patty"
    CHEESE = "cheese"
    LETTUCE = "lettuce"
    TOMATO = "tomato"
    ONION = "onion"
    PICKLE = "pickle"
    SAUCE = "souce"
    BACON = "bacon"

class MachineStatus(str, Enum):
    """Status för maskindelar."""
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    ERROR = "error"
    OFF = "off"

# Huvudmodeller
class Order(Base):
    """Order-modell för hamburgerbeställningar."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_number = Column(String(20), unique=True, nullable=False, index=True)
    customer_id = Column(String(50), nullable=True) # Kan vara anonym
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.RECEIVED, nullale=False)
    total_price = Column(Float, nullable=False, default=0.0)
    payment_method = Column(SQLEnum(PaymentMethod), nullable=False)
    payment_status = Column(Boolean, default=False) # True om betald
    special_instructions = Column(Text, nullable=True)

    # Tidsstämplar
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationer
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    event = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Order(id={self.id}, order_nimber={self.order_number}, status={self.status})>"
    
class OrderItem(Base):
    """Enskilda item i en order (t.ex. en hamburger)."""
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    burger_type = Column(String(50), nullable=False) # T.ex. "Cheeseburger", "Double Bacon"
    quantity = Column(Integer, nullable=False, default=1)
    price = Column(Float, nullable=False)

    # Anpassningar
    customizations = Column(JSON, nullable=True) # JSON för extra/mindre ingredienser

    # Relationer
    order = relationship("Order", back_populates="items")
    ingredients = relationship("OrderItemIngredient", back_populated="order_item", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<OrderItem(id={self.id}, burger_type={self.burger_type}, quantity={self.quantity})>"
    
class OrderItemIngredient(Base):
    """Specifika ingredienser för att ett orderitem."""
    __tablename__ = "order_item_ingredients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("oreders.id"), nullable=False)
    event_type = Column(String(50), nullble=False) # T.ex. "payment_receivd", "cooking_started"
    description = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=True) # Ytterligare data i JSON-format
    create_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationer
    order = relationship("Order", back_populates="events")
    
    def __repr__(self):
        return f"<OrderEvent(id={self.id}, order_id={self.order_id}, event_type={self.event_type})>"
    
class OrderEvent(Base):
    """Händelser för en order (för spåring)."""
    __tablename__ = "order_events"

    id = Column(Integer, primary_key=True, autoinctement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    event_type = Column(String(50), nullable=False) # T.ex. "payment_received", "cooking_started"
    description = Column(Text, nullable=True) 
    metadata = Column(JSON, nullable=True) # Ytterligare data i JSON-format

    # Relationer
    order = relationship("Order", back_populates="events")

    def __repr__(self):
        return f"<OrderEvent(id={self.id}, order_id={self.event_type}, event_type={self.event_type})>"
    
class Inventory(Base):
    """Lagerhantering för ingredoenser."""
    __tablename__ = "invnetory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ingredient_type = Column(SQLEnum(IngredientType), nullable=False, unique=True)
    current_quantity = Column(Integer, nullable=False, degault=0)
    max_capacity = Column(Integer, nullable=False, default=100)
    min_threshold = Column(Integer, nullable=False, default=10)
    unit = Column(String(20), nullable=False, default="pieces")

    # Plats i maskinen
    storage_location = Column(String(50), nullable=True) # T.ex. "Dispenser_A1"

    # Status
    is_active = Column(Boolean, default=True)
    last_restocked = Column(DateTime, nullable=True)
    next_restock_estimate = Column(DateTime, nullable=True)

    # Relationer
    history = relationship("InventoryHistory", back_populates="inventory", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Inventory(id={self.id}, type={self.ingredient_type}, quantity={self.current_quantity})>"
    
class InventoryHistory(Base):
    """Historik för inventeringsförändingar."""
    __tablename__ = "invnetory_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invnetory_id = Column(Integer, ForeignKey("inventory.id"), nullable=False)
    change_type = Column(String(50), nullable=False) # T.ex. "restock", "consumption", "waste"
    quantity_change = Column(Integer, nullable=False) # Positiv för tillskott, negativ förbrukning
    new_quantity = Column(Integer, nullable=False)
    reason = Column(Text, nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True) # Om kopplat till en order
    create_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationer
    inventory = relationship("Inventory", back_populates="history")
    order = relationship("Order")

    def __repr__(self):
        return f"<InventoryHistory(id={self.id}, invnetory_id{self.invnetory_id}, change={self.quantity_change})>"
    
class TemperatureReading(Base):
    """Temperaturläsningar från olika delar av maskinen."""
    __tablename__ = "temperature_readings"


    id = Column(Integer, primary_key=True, autoincurement=True)
    sensor_id = Column(String(50), nullable=False, index=True) # T.ex. "grill_1", "fryer_2"
    temperature = Column(Float, nullable=False)
    unit = Column(SQLEnum(TemperatureUnit), default=TemperatureUnit.CELSIUS, nullable=False)
    target_temperature = Column(Float, nullable=True)

    # Metadata
    is_within_range = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<TemperaturReading(id={self.id}, sensor={self.sensor_id}, temp={self.temperature})>"
    
class MachineComponent(Base):
    """Registerade maskinkomonenter och deras status."""
    __tablenamne__ = "machine_components"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component_type = Column(String(50), unique=True, nullable=False) # T.ex "robotic_arm", "conveyor.belt"
    name = Column(String(100), nullable=False)
    component_type = Column(String(50), nullable=False) # T.ex. "acturator", "sensor", "heater"

    # Status
    status = Column(SQLEnum(MachineStatus), default=MachineStatus.OPERATIONAL, nullable=False)
    last_maintenance = Column(DateTime, nullable=True)
    next_maintenance_due = Column(DateTime, nullable=True)

    # Konfiguration
    config = Column(JSON, nullable=True) # Komponent-specifik konfiguration
    is_critical = Column(Boolean, default=True) # Om fel stoppar hela maskinen

    # Relationer
    logs = relationship("ComponentLog", back_populates="component", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<MachineComponent(id={self.id}, component_id={self.component_type}, status={self.status})>"
    
class ComponentLog(Base):
    """Logg för komponenthändelser och fel."""
    __tablename__ = "component_logs"

    id = Column(Integer, primary_key=True, autoincurent=True)
    component_id = Column(Integer, ForeignKey("machine_componsents.id"), mullable=False)
    log_level = Column(String(20), nullable=False) # T.ex. "INFO", "WARNING", "ERROR", "CRITICAL"
    message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationer
    component = relationship("MachineComponent", back_populates="logs")

    def __repr__(self):
        return f"<ComponentLog(id={self.id}, component_id={self.component_id}, level={self.log_level})>"
    
class Recipe(Base):
    """Recept för olika burgertyper."""
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    base_prise = Column(Float, nullable=False)
    is_available = Column(Boolean, default=True)
    preparation_time = Column(Integer, nullable=True) # I sekunder
    calories = Column(Integer, nullable=True)

    # Standardinställningar
    default_ingredients = Column(JSON, nullable=False) # JSON med standardingredienser

    # Relationer
    ingredients = relationship("RecipeIngredient", back_popuöates="recipe", cadcade="all, delete-orphan")

    def __repr__(self):
        return f"<Recipe(id={self.id}, name={self.name}, price={self.base_prise})>"
    
class RecipeIngredient(Base):
    """Ingredienser som ingår i ett recept."""
    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    ingredient_type = Column(SQLEnum(IngredientType), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    is_optional = Column(Boolean, default=False)
    extra_cost = Column(Float, default=0.0) # Extra kostnad om ingrediensen läggs till

    # Relationer
    recipe = relationship("Recipe", back_populates="ingredients")

    def __repr__(self):
        return f"<RecipeIngredient(id={self.id}, recipe_id={self.recipe_id}, type={self.ingredient_type})>"
    
class SystemLog(Base):
    """System-wide logging för audit och debugging."""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    log_level = Column(String(20), nullable=False)
    module = Column(String(100), nullable=True)
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<SystemLog(id={self.id}, level={self.log_level}, module={self.module})"
    
class MaintenanceSchedule(Base):
    """Underhållsschema för maskinen."""
    __tablename__ = "maintenance_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component_id = Column(String(50), nullable=False) # Referens till machine_components.component_id
    maintenance_type = Column(String(50), nullable=False) # T.ex. "cleaning", "calibration", "repair"
    description = Column(Text, nullable=True)
    scheduled_for = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    technician = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    # Status
    is_completed = Column(Boolean, default=False)
    is_critical = Column(Boolean, default=False) # Om det måste göras för att makinen ska fungera

    def __repr__(self):
        return f"<MaintenanceSchedule(id={self.id}, comment={self.component_id}, headuled={self.scheduled_for})>"
    
class DatabaseManager:
    """Hanterar databasanslutning och sessioner."""

    def __init__(self, database_url: str = DATABASE_URL):
        """Initiera databasanslutning."""
        try:
            self.engine = create_engine(
                self.database_url,
                connect_args={"check_same_thread": False} if "sqlite" in self.database_url else {}
            )
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            logger.info(f"Database engine initialized with URL: {self.database_url}")
        except Exception as e:
            logger.error(f"Failed to initoalize database engine: {e}")
            raise

    def create_tables(self):
        """Skapa alla tabeller om de inte finns."""
        try:
            Base.metedata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except SQLAlchemyError as e:
            logger.error(f"Failed to create database tables: {e}")
            raise

    def drop_tables(self):
        """Radera alla tabeller (endast för test/dev)."""
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.warning("Database tables dropped")
        except SQLAlchemyError as e:
            logger.error(f"Failed to drop database tables {e}")
            raise

    def get_session(self) -> Session:
        """Hämta en ny databassession."""
        if not self.SessionLocal:
            self._initialize()
        return self.SessionLocal()
    
    def close(self):
        """Stäng databasanslutningen."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")

# Skapa standardinstanser
db_manager = DatabaseManager()

def init_database():
    """Initiera databasen med grunddata."""
    session = db_manager.get_session()

    try:
        # Skapa tabbeler om de inte finns
        db_manager.create_tables()

        # Lägg till standardrecept om inga finns
        if session.query(Recipe).count() == 0:
            default_recipes = [
                Recipe(
                    name="Classic Burger",
                    description="En klassisk hamburger med nötkött, sallad, tomater och dressing",
                    base_price=59.0,
                    preparation_time=300,
                    calories=550,
                    default_ingredients={
                        "bun": 2,
                        "patty": 1,
                        "lettuce": 1,
                        "tomato": 2,
                        "onion": 2,
                        "sauce": 1 
                    }
                ),
                Recipe(
                    name="Cheeseburger",
                    description="Klassisk hamburger med cheddarost",
                    base_price=69.0,
                    preparation_time=320,
                    calories=650,
                    default_ingredients={
                        "bun": 2,
                        "patty": 1,
                        "cheese": 1,
                        "lettuce": 1,
                        "tomato": 2,
                        "onion": 2,
                        "sauce": 1
                    }
                ),
                Recipe(
                    name="Double Bacon Burger",
                    description="Dubbla köttbullar med bacon och extra ost",
                    base_price=89.0,
                    preparation_time=420,
                    calories=850,
                    default_ingredients={
                        "bun": 2,
                        "patty": 2,
                        "cheese": 2,
                        "bacon": 3,
                        "lettuce": 1,
                        "tomato": 2,
                        "onion": 2, 
                        "sauce": 1
                    }
                )
            ]

            session.add_all(default_recipes)

        # Lägg till standardinventering om inga finns
        if session.query(Inventory).count() == 0:
            default_inventory = [
                Inventory(
                    ingredient_type=IngredientType.BUN,
                    current_quantity=100,
                    max_capacity=200,
                    min_threshold=20,
                    unit="pieces",
                    storage_location="Dispenser_A1"
                ),
                Inventory(
                    ingredient_type=IngredientType.PATTY,
                    current_quantity=80,
                    max_capacity=150,
                    min_threshold=15,
                    unit="pieces",
                    storage_location="Freezer_B1"
                ),
                Inventory(
                    ingredient_type=IngredientType.CHEESE,
                    current_quantity=60,
                    max_capacity=100,
                    min_threshold=10,
                    unit="slices",
                    storage_location="Cooler_C1"
                ),
                Inventory(
                    ingredient_type=IngredientType.LETTUCE,
                    current_quantity=40,
                    max_capacity=80,
                    min_threshold=8,
                    unit="leaves",
                    storage_location="Cooler_C2"
                ),
                Inventory(
                    inventory_type=IngredientType.TOMATO,
                    current_quantity=50,
                    max_capacity=80,
                    min_threshold=8,
                    unit="slice",
                    storage_location="Cooler_C3"
                ),
                Inventory(
                    ingredient_type=IngredientType.SAUCE,
                    current_quantity=90,
                    max_capacity=120,
                    min_threshold=12,
                    unit="portions",
                    storage_location="Dispenser_A2"
                )
            ]

            session.add_all(default_inventory)

            session.commit()
            logger.info("Database initialized with default data")

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Failed to initialized database: {e}")
        raise
    finally:
        session.close()


def get_db() -> Session:
    """
    Despendency för att hämta datavassession.
    Används med FastAPI eller liknande.
    """
    db = db_manager.get_session()
    try:
        yield db
    finally:
        db.close()

# Kör initiering om filen kör direkt
if __name__ == "__main__":
    init_database()
    print("Database models created and initialized successfully!")
    
