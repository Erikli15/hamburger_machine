"""
Databasmodul för hamburgerautomaten.
Hanterar databasansluting, modeller och scheman.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.exe.declerative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# Läs databaskonfiguration från miljövariabler eller konfigurationsfil
DATABASE_URL = os.getenv(
    "DATAVASE_URL",
    "sqlite:///./hamburger_machine.db" # Default: SQLite-databas
)

# Skapa SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# Skapa session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Basklass för alla modeller
Base = declarative_base()

# Importera alla modeller för att de ska registreras
from .models import Order, InventoryItem, SystemLog, MaintenanceLog, TemperatureLog

# Funktion för att skapa alla tabeller
def create_database_tables():
    """Skapa alla databastabeller om de inte redan finns."""
    Base.metadata.create_all(bind=engine)
    print(f"Databastabeller skapad i: {DATABASE_URL}")

# Dependency för att få databassession
def get_db() -> Generator[Session, None, None]:
    """
    Ger en databassession som ger en generator.
    Använd i FastAPI endpoints eller andra ställen som behöver DB-åtkomst.

    Exempel:
        db = next(get_db())
        # eller i FastAPI:
        # def get_order(order_id: int, db: Session = Dependes(get_db))
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initiera databas vid import
try:
    # Kontrollera om vi ska skapa tabeller automatiskt
    # (kan konfiguteras via miljövariabel)
    if os.getenv("CREATE_DB_TABLES", "True").lower() == "true":
        create_database_tables()
except Exception as e:
    print(f"Fel vid skapande av databastabbeller: {e}")
    # Forsätt ändå - tabellerna kanske redan finns

# Exportera viktiga komponenter för enkel åtkomst
__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "create_database_tables",
    "Order",
    "InventoryItem",
    "SystemLog",
    "MaintenanceLog",
    "TemperatureLog"
]
