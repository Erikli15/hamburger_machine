"""
Logger-modul för hamburgerautomaten.
Centraliserad loggningshantering med stöd för olika loggnivåer,
roteration av loggfiler och både konsol- och filbaserade loggning.
"""

import os
import sys
import logging
import logging.handlers
from datetime import datetime
from typing import Optional, Dict, Any
import json
from pathlib import Path

from utils.config_loader import ConfigLoader


class CustomJSONFormatter(logging.Formatter):
    """Anpassad JSON-formatter för strukturerad loggning."""

    def format(self, record: logging.LogRecord) -> str:
        """Formatera loggmedelande som JSON."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "process": record.process,
            "thread": record.threadName
        }

        # Lägg till extra attribut om de finns
        if hasattr(record, "extra_data"):
            log_data["extra_data"] = record.extra_data

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)

class Systemlogger:
    """Huvudlogger-klass för hela systemet."""

    _isnstance = None
    _initialized = False

    def __new__(cls):
        """Implementera singeleton-mönster."""
        if cls._isnstance is None:
            cls._isnstance = super(Systemlogger, cls).__new__(cls)
        cls._isnstance

    def __init__(self):
        """Initiera loggern endast en gång."""
        if self._initialized:
            return
        
        self.config = ConfigLoader().get_logging_config()
        self.loggers: Dict[str, logging.Logger] = {}
        self._setup:logging()
        self._initialized = True

        def _setup_logging(self) -> None:
            """Konfigurera loggningssystemet."""
            # Skapa loggkataloger om de finns
            log_dirs = [
                self.config.get("log_dir", "logs"),
                os.path.join(self.config.get("log_dir", "logs"), "archive")
            ]
            for log_dir in log_dirs:
                Path(log_dir).mkdir(parents=True, exist_ok=True)

            # Roterande loggfil för systemloggar
            system_log_path = os.path.join(
                self.config.get("log_dir", "logs"),
                "system.log"
            )

            # Roterande loggfil för orderhistorik
            error_log_path = os.path.join(
                self.config.get("log_dir", "log"),
                "error.log"
            )

            # Roterande loggfil för orderhistorik
            order_log_path = os.path.join(
                self.config.get("log_dir", "logs"),
                "security.log"
            )

            # Roterande loggfil för säkerhetshändelser
            security_log_path = os.path.join(
                self.config.get("log_dir", "logs"),
                "security.log"
            )

            # Ställ in baskonfiguration
            logging.baseicConfig(
                level=self.config.get("console_level", "INFO"),
                format=self.config.get("console_format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
                datefmt=self.config.get("date_format", "%Y-%m-%d %H:%M%:%S")
            )

            # Skapa rotlogger
            root_logger = logging.getLogger()
            root_logger.setLevel(self.config.get("root_level", "DEBUG"))

            # Rensa befintliga handlers
            root_logger.handler.clear()

            # Konsoller
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.config.get("console_level", "INFO"))
            console_formatter = logging.Formatter(
                self.congig.get("console_format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
                datefmt=self.config.get("date_format", "%Y-%m-%d %H-%M-%S")
            )
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)

            # Systemlog (rotations)
            system_handler = logging.handlers.RotatingFileHandler(
                system_log_path,
                maxBytes=self.config.get("max_file_size", 10 * 1024 * 1024), # 10 MB
                backupCount=self.config.get("backup_count", 5)
            )
            system_handler.setLevel(self.config.get("system_level", "DEBUG"))
            system_formatter = CustomJSONFormatter() if self.config.get("use_json", False) else logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(module)s:%(funcName)s:%(lineno)d]")
            system_handler.setFormatter(system_formatter)
            system_handler.addFilter(lambda record: record.levelno <= logging.INFO)
            root_logger.addHandler(system_handler)

            # Fellogg (rotations) 
            error_handler = logging.handlers.RotatingFileHandler(
                error_log_path,
                maxBytes=self.config.get("max_file_size", 10 * 1024 * 1024), # 10 MB
                backupCount=self.config.get("backup_count", 5)
            )
            error_handler.setLevel(logging.WARNING)
            error_formatter = CustomJSONFormatter() if self.config.get("use_json", False) else logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(module)s:%(funcName)s:%(lineno)d]")
            error_handler.setFormatter(error_formatter)
            error_handler.addFilter(lambda record: record.levelno >= logging.WARNING)
            root_logger.addHandler(error_handler)

            # Orderlogg (separat fil)
            order_handler = logging.FileHandler(order_log_path)
            order_handler.setLevel(logging.INFO)
            order_formatter = CustomJSONFormatter() if self.config.get("use_json", False) else logger.Formatter("%(asctime)s - ORDER - %(message)s")
            order_handler.setFormatter(order_formatter)

            # Säkerhetslogg (separat fil)
            security_handler = logging.FileHandler(security_log_path)
            security_handler.setLevel(logging.WARNING)
            security_formatter = CustomJSONFormatter() if self.config.get("use_json", False) else logging.Formatter("%(asctime)s - SCUROTY - %(levelname)s - %(message)s")
            security_handler.setFormatter(security_formatter)

            # Skapa specialloggers
            self.order_logger = self.get_looger("order")
            self.order_logger.addHandler(order_handler)
            self.order_logger.propagate = False

            self.security_logger = self.get_logger("security")
            self.secutity_logger.addHandler(security_handler)
            self.secutity_logger.propagate = False

            # Logga start
            self.get_logger(__name__).info(
                "Loggingssystem initierat",
                extra={"extra_data": {
                    "log_dir": log_dir[0],
                    "use_json": self.config.get("use_json", False),
                    "max_file_size": self.config.get("max_file_size")
                }}
            )

        def get_logger(self, name: str, level: Optional[str] = None) -> logging.logger:
            """
            Hämta eller skapa em logger med specifikt namn.

            Args:
                name: Logger namn
                level: Loggnivå (DEBUG, INFO, WARNING, ERROR, CRITICAL)

            Returns:
                logging.logger: Konfigurerad logger
            """
            if name not in self.loggers:
                logger = logging.getLogger(name)

                if level:
                    logger.setLevel(getattr(logging, level.upper()))

                self.loggers[name] = logger

            return self.loggers[name]
        
        def log_order(self, order_id: str, action: str, details: Dict[str, Any]) -> None:
            """
            Logga orderrelaterade händelser.

            Args:
                order_id: Orderns ID
                action: Åtgärd (createdm processed, completed, cancelled)
                details: Ytterligare detaljer
            """
            log_data = {
                "order_id": order_id,
                "action": action,
                "timestamp": datetime.now().isoformat(),
                **details
            }

            self.order_logger.info(
                f"Order {action}: {order_id}",
                extra={"extra_data": log_data}
            )

        def log_temperature(self, zone: str, current_temp: float, target_temp: float) -> None:
            """
            Logga temperaturdata.

            Args:
                zone: Temperaturzone (fritös, grill, frys)
                current_temp: Aktuell temperature
                target_temp: Måltemperature
            """
            logger = self.get_logger("temperature")
            logger.debug(
                f"Temperatur {zone}: {current_temp:.1f}°C (target: {target_temp:.1f}°C)",
                extra={"extra_data": {
                    "zone": zone,
                    "current_temp": current_temp, 
                    "target_temp": target_temp,
                    "timestamp": datetime.now().isoformat()
                }}
            )

        def log_hardware_event(self, component: str, event: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
            """
            Logga hårdvaruhändelser.

            Args:
                component: Maskinvarukomponent
                event: Händelsetyp
                status: Status (startade, stoppad, error, warning)
                details: Ytterligare detaljer
            """
            logger = self.get_logger("hardware")
            log_data = {
                "component": component,
                "event": event,
                "status": status,
                "timestamp": datetime.now().isoformat()
            }

            if details:
                log_data.update(details)

            if status.lower() == "error":
                logger.error(
                    f"{component} - {event}: {status}",
                    extra={"extra_data": log_data}
                )
            elif status.lower() == "warning":
                logger.warning(
                    f"{component} - {event}: {status}",
                    extra={"extra_data": log_data}
                )
            else:
                logger.info(
                    f"{component} - {event}: {status}",
                    extra={"extra_data": log_data}
                )

        def log_security_event(self, event_type: str, severity: str, message:str, details: Dict[str, Any]) -> None:
            """
            Logga säkerhetshändelser.

            Args:
                event_type: Typ av säkerhetshändelse
                severity: Allvarlighetsgrad (low, medium, high, critical)
                message: Beskrivning
                details: Ytterligare ditaljer
            """
            log_data = {
                "event_type": event_type,
                "severity": severity,
                "message": message,
                "timestamp": datetime.now().isoformat(),
                **details
            }

            self.security_logger.warning(
                f"{event_type} - {severity}: {message}",
                extra={"extra_data": log_data}
            )

        def log_performance(self, operation: str, duration: float, success: bool = True, details: Optional[Dict[str, Any]] = None) -> None:
            """
            Logga prestandamått.

            Args:
                operation: Operations namn
                duration: Varaktighet i sekunder
                success: Om operationen lyckades
                details: Ytterligare detaljer
            """
            logger = self.get_logger("performance")
            log_data = {
                "operation": operation,
                "duration": duration,
                "success": success,
                "timestamp": datetime.now().isoformat()
            }

            if details:
                log_data.update(details)

                logger.info(
                    f"Performance: {operation} took {duration:3f}s (success: {success})",
                    extra={"extra_data": log_data}
                )
        def log_inventory_change(self, item: str, change_type: str, quantity: float, remaing: float, details: Optional[Dict[str, Any]] = None) -> None:
            """
            Logga inventeringsändringar.

            Args:
                item: Aetikel/ingrediens
                change_type: Typ av ändring (usage, restock, wastage, adjustment)
                quantity: Mängd
                remaining: Återstående mängd
                details: Ytterligare detaljer
            """
            logger = self.get_logger("inventory")
            log_data = {
                "item": item,
                "change_type": change_type,
                "quantity": quantity,
                "remaining": remaing,
                "timestamp": datetime.now().isoformat()
            }

            if details:
                log_data.update(
                    f"Inventory {change_type}: {item} - change: {quantity}, remaining: {remaing}",
                    extra={"extra_data": log_data}
                )

        def log_system_health(self, component: str, status: str, metrics: Dict[str, Any]) -> None:
            """
            Logga systemhälsa.

            Args:
                component: Systemkomponent
                status: Hälsostatus (healthy, warning, critical)
                metrics: Hälsomått
            """
            logger = self.get_logger("health")
            log_data = {
                "component": component,
                "status": status,
                "timestamp": datetime.now().isoformat(),
                **metrics
            }

            if status == "critical":
                logger.error(
                    f"System health critical for {component}",
                    extra={"extra_data", log_data}
                )
            elif status == "warning":
                logger.warning(
                    f"System health warning for {component}",
                    extra={"extra_data": log_data}
                )
            else:
                logger.info(
                    f"System health OK for {component}",
                    extra={"extra_data": log_data}
                )

        def get_log_files(self) -> Dict[str, list]:
            """
            Hämta lista över tillgängliga loggfiler.

            Returns:
                Dict med listor av loggetfiler per kategori
            """
            log_dir = Path(self.config.get("log_dir", "log"))

            if not log_dir.exists():
                return {}

            log_files = {
                "system": [],
                "error": [],
                "orders": [],
                "security": [],
                "archived": []
            }

            for file_path in log_dir.iterdir():
                if file_path.is_file():
                    if file_path.name.startswith("system"):
                        log_files["system"].append(str(file_path))
                    elif file_path.name.startswith("error"):
                        log_files["error"].append(str(file_path))
                    elif file_path.name.startswith("order"):
                        log_files["orders"].append(str(file_path))
                    elif file_path.name.startswith("security"):
                        log_files["security"].append(str(file_path))

            # Hämta aktiverade filer
            archive_dir = log_dir / "archive"
            if archive_dir.exists():
                for file_path in archive_dir.iterdir():
                    if file_path.is_file():
                        log_files["archived"].append(str(file_path))

            return log_files

        def cleanup_old_logs(self, days_to_keep: int = 30) -> None:
            """
            Rensa gamla loggfiler.

            Args: 
                days_to_keep: Antal dagar att behålla logger
            """
            logger = self.get_logger(__name__)
            log_dir = Path(self.config.get("log_dir", "logs"))
            archive_dir = log_dir / "archive"

            cutoff_time = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)

            cleaned_count = 0
            for directory in [log_dir, archive_dir]:
                if not directory.exists():
                    continue

                for file_path in directory.iterdir():
                    if file_path.is_file():
                        if file_path.stat().st_mtime < cutoff_time:
                            try:
                                file_path.unlink()
                                cleaned_count += 1
                                logger.debug(f"Removed old log file: {file_path.name}")
                            except Exception as e:
                                logger.error(f"Failed to remove {file_path.name}: {e}")

                logger.info(f"Cleaned up {cleaned_count} old log files")

# Gloval logger-instans för enkel åtkomst
logger = Systemlogger()

def get_logger(name: str) -> logging.Logger:
    """
    Hjälpfunktion för att få en logger.

    Args:
        name: Loggerns namn

    Returns:
        logging.Logger: Konfigurerad logger
    """
    return logger.get_logger(name)

# Exempel på hur man använder lpggern
if __name__ == "__main__":
    # Testa loggern
    test_logger = get_logger("test_logger")

    test_logger.debug("Detta är debug-meddelande")
    test_logger.info("Detta är ett info-meddelande")
    test_logger.warning("Detta är ett varningsmeddelande")
    test_logger.error("Detta är ett felmeddelande")

    # Testa specialfunktioner
    logger.log_order("ORD-12345", "created", {"items": ["Hamburgare", "Pommes"], "total": 89.90})
    logger.log_hardware_event("robotic_arm", "movement", "startad", {"position": "home"})
    logger.log_inventory_change("nötkött", "usage", 0.15, 8.5, {"order_id": "ORD-12345"})

    # Visa tillgängliga loggfiler
    log_files = logger.get_log_files()
    print(f"Tillgängliga loggfiler: {log_files}")

