"""
Databasmodul för hamburgerautomaten.
Hanterar databasanslutningar, sessioner och grundläggande CRUD-operationer.
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional, Generator, Any, Dict, List
from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import QueuePool

# For SQLite specifika inställningar
from sqlalchemy.exc import SQLAlchemyError, IntergerityError, OperationalError

# Lokala importer
from utils.config_loader import ConfigLoader
from utils.logger import setup_logger
from .models import Base # Vi antar att models.py definerar Base och alla modeller

# Logging setup
logger = setup_logger(__name__)

class DatabasManager:
    """
    Hantera databasanslutningar sessioner för hamburgerautomaten.
    Stöder både SQLite (för lokal utveckling/test) och PostgreSQL (för produktion).
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initiera databasanslutningen.

        Args:
           config_path: Sökväg till konfigurationsfill (använder standard om None)
        """

        self.config = ConfigLoader(config_path).get_database_config()
        self.engine = None
        self.session_factory = None
        self.SessionLocal = None
        self._setup_connection()

    def _setup_connection(self) -> None:
        """Konfigurera databasanslutningen baserat på konfiguration."""
        try:
            db_type = self.config.get("type", "sqlite").lower()

            if db_type == "sqlite":
                self._setup_sqlite()
            elif db_type in ["postgresql", "postgres"]:
                self._setup_posgersql()
            elif db_type == "mysql":
                self._setup_mysql()
            else:
                raise ValueError(f"Ej stödd databastyp: {db_type}")
            
            # Aktivera SQLite foreign key support
            if db_type == "sqlite":
                self._enable_sqlite_foreign_keys()
            
            # Skapa alla tabeller om de inte finns
            self.create_tables()
            
            logger.info(f"Databasanslutning etablerad: {db_type}")

        except Exception as e:
            logger.error(f"Fel vid uppsättning av databas: {e}")
            raise

    def _setup_sqlite(self) -> None:
        """Konfigurera SQLite-anslutning."""
        db_path = self.config.get("databas", "hamburger_machine.db")

        # Säkerställ att katalogen finns
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # SQLite URI - aktivera WAL mode för bättre concurrent access
        db_url = f"sqlite:///{db_path}"

        # SQLite-specifika inställningar
        connect_args = {
            "check_same_thread": False,
            "timeout": self.config.get("timeout", 30.0)
        }

        # Skapa engine med optimerade inställningar för SQLite
        self.engine = create_engine(
            db_url,
            connect_args=connect_args,
            poolclass=QueuePool,
            pool_size=self.config.get("pool_size", 5),
            max_overflow=self.config.get("max_overflow", 10),
            pool_timeout=self.config.get("pool_timeout", 30.0),
            pool_recycle=self.config.get("pool_recycle", 3600),
            echo=self.config.get("echo_sql", False)
        )

        self._create_session_factory()

    def _setup_postgresql(self) -> None:
        """Konfigurera PostgreSQL-anslutning."""
        db_host = self.config.get("host", "localhost")
        db_port = self.config.get("port", 5432)
        db_name = self.config.get("database", "hamburger_machine")
        db_user = self.config.get("user", "postgres")
        db_password = self.config.get("password", "")

        db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

        self.engine = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=self.config.get("pool_size", 10),
            max_overflow=self.config.get("pool_overflow", 20),
            pool_timeout=self.config.get("pool_timeout", 30.0),
            pool_recycle=self.config.get("pool_recycle", 1800),
            echo=self.config.get("echo_sql", False)
        )

        self._create_session_factory()

    def _setup_mysql(self) -> None:
        """Konfigurera MySQL-anslutning."""
        db_host = self.config.get("host", "localhost")
        db_port = self.config.get("port", 3306)
        db_name = self.config.get("databas", "hamburger_machine")
        db_user = self.config.get("user", "root")
        db_password = self.config.get("password", "")

        db_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

        self.engine = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=self.config.get("pool_size", 10),
            max_overflow=self.config.get("max_overflow", 20),
            pool_timeout=self.config.get("pool_timeout", 30,0),
            pool_recycle=self.config.get("pool_recycle", 1800),
            echo=self.config.get("echo_sql", False),
            # MySQL-specifika inställningar
            pool_pre_ping=True, # Verifiera anslutningar innan använding
            isolation_level="REPEATABLE_READ"
        )

        self._create_session_factory()

    def _create_session_factory(self) -> None:
        """Skapa session factory med scopade sessioner för trådsäkerhet."""
        self.session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            expire_on_commit=False
        )
        self.SessionLocal = scoped_session(self.session_factory)

    def _enable_sqlite_foreign_keys(self) -> None:
        """Aktivera foreign key constaint i SQLite."""
        @event.listens_for(Engine, "connect")
        def set_sqlite_pragma(dbpi_connection, connection_record):
            cursor = dbpi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA jurnal_mode=WAL")
            cursor.excecute("PRAGMA synchronous=NORMAL")
            cursor.execute("PARAGMA cache_size=10000")
            cursor.close()

    def create_tables(self) -> None:
        """Skapa alla tabeller om de inte finns."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Databastabeller skapade/varifierade")
        except Exception as e:
            logger.error(f"Fel vid skapande av tabeller: {e}")
            raise

    def drop_tables(self) -> None:
        """Rdera alla tabeller (endast för test/dav)."""
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.warning("Alla databastabeller raderade")
        except Exception as e:
            logger.error(f"Fel vid radering av tabeller: {e}")
            raise

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager för att få en databassession.
        Hanterar automatiskt rollback vid fel och stängning av session.

        Yields:
             Session: SQLAlchemy session

        Exemple:
             with db.get_session() as session:
                  order = Order(customer_id=1, total=99.99)
                  session_add(order)
                  session.commit()
        """
        session: Session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rolleback()
            logger.error(f"Databassession fel: {e}")
            raise
        finally:
            session.close()
            self.SessionLocal.remove()

    def execute_raw_sql(self, sql: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Exekvera raw SQL-fråga.

        Args:
           sql: SQL-fråga
           params: Parametrar för frågan

        Returns:
           Lista med resultat som dictionaries
        """
        try:
            with self.engine.connect() as connection:
                result = connection.execute(sql, params or {})
                return [dict(row) for row in result]
        except Exception as e:
            logger.error(f"Fel vid exekvering av SQL: {sql} - {e}")
            raise

    def health_check(self) -> Dict[str, Any]:
        """
        Utför en hälsokontroll av databasen.

        Returns:
             Dictionary med hälsostatus
        """
        try:
            with self.get_session() as session:
                # Försök att extevera en enkel fråga
                if self.config.get("type") == "sqlite":
                    session.execute("SELECT 1")
                else:
                    session.execute("SELECT 1 as health_check")

                # Kontrollera antalet aktiva anslutningar
                active_connections = self.engine.pool.checkedout()

                return {
                    "status": "healthy",
                    "database_type": self.config.get("type"),
                    "active_connections": active_connections,
                    "pool_size": self.engine.pool_size(),
                    "checked_at": datetime.now().isoformat()
                }
        
        except Exception as e:
            logger.error(f"Databas hälsokontroll misslyckades: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "checked_at": datetime.now().isoformat()
            }

    def backup_database(self, backup_path: Optional[str] = None) -> str:
        """
        Skapa en säkerhetskopia av databasen.

        Args:
           backup_path: Sökväg för backup-fil

        Returns:
           Sökväg till backup-fil
        """
        if self.config.get("type") != "sqlite":
            raise NotImplementedError("Backup stöds endast för SQLite tillfället")

        db_path = self.config.get("database", "hamburger_machine.db")

        if not backup_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{db_path}.backup_{timestamp}"

        try:
            import shutil
            shutil.copy2(db_path, backup_path)
            logger.info(f"Databas säkerhetskopierad till: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Fel vid säkerhetskopiering av databas: {e}")
            raise

    def optimize_database(self) -> None:
        """Optimera databasen (VACUUM för SQLite, ANALYZE för PostgreSQL)."""
        try:
            with self.get_session() as session:
                if self.config.get("type") == "sqlite":
                    session.execute("VACUUM")
                elif self.config.get("type") in ["postgresql", "postgres"]:
                    session.execute("ANALYZE")
                elif self.config.get("type") == "mysql":
                    session.execute("ANALYZE TABLE")

            logger.info("Databas optimerad")
        except Exception as e:
            logger.warning(f"Kunde inte optimera databas: {e}")

    def close_connections(self) -> None:
        """Stäng alla databasansutningar."""
        try:
            if self.engine:
                self.engine.dispose()
                logger.info("Databasanslutningar stängda")
        except Exception as e:
            logger.error(f"Fel vid stängning av avslutningar {e}")

    def __enter__(self):
        """Stöd för cintext manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tab):
        """Stäng ansutningar när context anslutas."""
        self.close_connections()

# Global databasinstans för enkel åtkonst
_db_instance: Optional[DatabasManager] = None


def get_database() -> DatabasManager:
    """
    Hämta eller global databasinstans (Singletion mönster).

    Returns:
        DatabasManager instans
    """
    global _db_instance

    if _db_instance is None:
        _db_instance = DatabasManager()

    return _db_instance

def init_database(config_path: Optional[str] = None) -> DatabasManager:
    """
    Initiera databasen explicit.

    Args:
       config_path: Sökväg till konfigurationsfil

    Returns:
       DatabasManager instans
    """
    global _db_instance

    _db_instance = DatabasManager(config_path)
    return _db_instance


# Exempel på användning
if __name__ == "__main__":
    # Testa databasanslutningen
    db = get_database()

    # Utför hälsokontroll
    health = db.health_check()
    print(f"Databas hälsa: {health}")

    # Skapa backup
    try:
        backup_path = db.backup_database()
        print(f"Backup skapad: {backup_path}")
    except Exception as e:
        print(f"Kunde inte skapa backup: {e}")

    # Optimera databas
    db.optimize_database()

    # Stäng anslutningar
    db.close_connections()



    
