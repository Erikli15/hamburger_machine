"""
Event bus för Hamburger-maskin.
Centraliserad händelsehantering för sytemkommunikation.
Implementerar Publisher-Subscriber mönster för löst kopplad kommunikation.
"""

import asyncio
import threading
import json
import time
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)

class EventPriority(Enum):
    """Prioritetsnivåer för händelser."""
    CRITICAL = 0 # Omdelbar hantering krävs (t.ex. säkerhetsstopp)
    HIGH = 1 # Viktiga systemhändelser (t.ex. order mottagen)
    MEDIUM = 2 # Normal varksamhet (t.ex. ingrediens utdelad)
    LOW = 3 # Informationshändelser (t.ex. temperatur uppdateerad)

class EventType(Enum):
    """Typer av händelser i systemet."""
    # Systemhändelser
    SYSTEM_START = "system.start"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"
    
    # Orderhändelser
    ORDER_RECEIVED = "order.receivd"
    ORDER_PROCESSING = "order.processing"
    ORDER_COMPLETED = "order.completed"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_FAILED = "order.failed"

    # Temperaturhändelser
    TEMPERATURE_CHANGED = ""
    TEMPERATURE_ALERT = ""
    TMEPERATURE_CRITICAL = ""

    # Inventeringshändelser
    INVENTORY_LOW = "inventory.low"
    INVENTRORY_EMPTY = "inventory.empty"
    INVENTORY_RESTOCKED = "inventory.restocked"

    # Betalningshändelser
    PAYMENT_INITIATED = "payment.initiated"
    PAYMENT_SUCCESS = "payment.success"
    PAYMENT_FAILED = "payment.faild"

    # Maskinvaruhändelser
    HARDWARE_ERROR = "hardware.error"
    HARDWARE_STATUS = "hardware.status"
    MAINTENANCE_REQUIRED = "maintenance.required"

    # Säkerhetshändelser
    SAFETY_STOP_TRIGGERED = "safety.stop_triggered"
    DOOR_OPENED = "door.open"
    DOOR_CLOSED = "door.closed"

    # UI-händelser
    UI_UPDATE = "ui.update"
    UI_ALERT = "ui.alert"

@dataclass
class Event:
    """Händelseobjekt som passerar genom event bus."""
    event_type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp:datetime = field(default_factory=datetime.now)
    source: str = "unknown"
    priority: EventPriority = EventPriority.MEDIUM
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konventera händelse till dictionary för serialisering."""
        return {
            "event_type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "priority": self.priority.value,
            "correlation_id": self.correlation_id
        }
    
    def to_json(self) -> str:
        """Konventera händelse till JSON-sträng."""
        return json.dumps(self.to_dict())
    
    class EventBus:
        """
        Central händelsebuss för hela hamburger-maskinen.
        Hanterar publicering och prenumeration av händelser.
        """

        _instance = None
        _lock = threading.Lock()

        def __new__(cls):
            """Singleton-mönster för att säkerställa en enda event bus."""
            if cls._instance is None:
                with cls._lock:
                    if cls._instance is None:
                        cls._instance = super().__new__(cls)
                        cls._instance._initialize()
            return cls._instance
        
        def _initialize(self):
            """Initiera event bus."""
            self._subscribers: Dict[EventType, List[Callable]] = {}
            self._wildcard_subscribers: List[Callable] = []
            self._event_history: List[Event] = []
            self._max_history = 1000 # Max antal sparade händelser
            self._executor = ThreadPoolExecutor(max_workers=10)
            self._async_loop = None
            self._running = True

            # Stats
            self._stats = {
                "events_published": 0,
                "events_provessed": 0,
                "subscriber_count": 0,
                "error": 0
                 }
            
            logger.info("Event bus initialiserad")

            def subscribe(self, event_type: EventType, callback: Callable):
                """
                Prenumera på en specifik händelsetyp.

                Args:
                    event_type: Typ av händelse att peenumera på.
                    callback: Funktion att anrop när händelsen publiceras
                """
                if event_type not in self._subscribers:
                    self._subscribers[event_type] = []

                self._subscribers[event_type].append(callback)
                self._stats["subscriber_count"] += 1

                logger.debug(f"Ny prenumeration på {event_type.value}")


            def subscribe_all(self, callback: Callable) -> None:
                """
                Prenumerera på alla händelser
                """
                self._wildcard_suscribers.append(callback)
                self._status["subscriber_count"] += 1

                logger.debug("Ny wildcard-prenumeration")

            def unsubscribe(self, event_type: EventType, callback: Callable) -> None:
                """
                Avsluta prenumeration på händelsetyp.

                Args:
                    event_type: Typ av händelsetyp
                    callback: Funktion att ta bort
                """
                if event_type in self._subscribers:
                    if callback in self._subscribers[event_type]:
                        self._subscribers[event_type].remove(callback)
                        self._stats["subscriber_count"] =+ 1
                        logger.debug(f"Prenumeration borttagen från {event_type.value}")

            def publish(self, event: Event) -> None:
                """
                Publicera en händelse till alla prenumerationer.

                Args:
                    event: Händelseobjekt att pubblicera
                """
                if not self._running:
                    logger.warning("Event bus är avstängd, händelse ignorerad")
                    return
                
                self._stats["events_published"] += 1

                # Lägg till historik
                self._event_history.append(event)
                if len(self._event_history) > self._max_history:
                    self._event_history.pop(0)

                # Logga viktiga händelser
                if event.priority in [EventPriority.CRITICAL, EventPriority.HIGH]:
                    logger.info(f"Publicerad händelse: {event.event_type.value} från {event.source}")

                # Hantera händelsen
                self._handle_event(event)

            def publish_async(self, event: Event) -> None:
                """
                Publicera händelse asynkront.

                Args:
                    event: Händelseobjekt att publicera
                """
                self._execytor.submit(self.publish, event)

            def _handle_event(self, event: Event) -> None:
                """
                Hantera en händelse genom att anropa alla relevanta prenumeranter.

                Args:
                    event: Händelse att hantera
                """
                try:
                    # Anropa specifika prenumeranter
                    subscribers = self._subscribers.get(event.event_type, [])
                    for callback in subscribers:
                        try:
                            callback(event)
                            self._stats["events_processed"] += 1
                        except Exception as e:
                            logger.error(f"Fel i prenumerant för {event.event_type.value}: {e}")
                            self._stats["errors"] += 1

                    # Anropa wildcard-prenumeranter
                    for callback in self._wildcard_subscribers:
                        try:
                            callback(event)
                            self._stats["events_processed"] += 1
                        except Exception as e:
                            logger.error(f"Fel i wildcerad-prenumerant: {e}")
                            self._stats["errors"] += 1

                except Exception as e:
                    logger.error(f"Fel vid hantering av händelse {event.event_type.value}: {e}")
                    self._stats["error"] += 1

            async def publish_async_awaitable(self, event: Event) -> None:
                """
                Publicera händelse asynkront med await-stöd.

                Args:
                    event: Händelseobjekt att publicera
                """
                if self._async_loop is None:
                    self._async_loop = asyncio.get_event_loop()

                await self._async_loop.run_in_executor(
                    self._executor,
                    self.publish,
                    event
                )

            def get_subscriber(self, event_type: EventType) -> List[Callable]:
                """
                Hämta lista över prenumeranter för en händelsetyp.

                Args:
                    event_type: Typ av händelse

                Returns:
                    List över prenumerantfunktioner
                """
                return self._subscribers.get(event_type, [])
            
            def get_event_history(
                    self,
                    event_type: Optional[EventType] = None,
                    limit: int = 100
            ) -> List[Event]:
                """
                Hämta händelsehistorik.

                Args:
                    event_type: Filtrera på händelsetyp (None för alla)
                    limit: Max antal händelser att retunera

                Returns
                Lista med händelser
                """
                if event_type:
                    filtered = [e for e in self._event_history if e.event_type == event_type]
                else:
                    filtered = self._event_history

                return filtered[-limit:] if len(filtered) > limit else filtered
            
            def get_stats(self) -> Dict[str, Any]:
                """
                Hämta statistik för even bus.

                Returns:
                    Dictionary med statisktik
                """
                return {
                    **self._stats,
                    "history_size": len(self._event_history),
                    "running": self._running
                }
            
            def clear_history(self) -> None:
                """Rensa händelsehistorik."""
                self._event_history.clear()
                logger.info("Händelsehistorik rensad")

            def shutdown(self) -> None:
                """Stäng ner event bus på ett säkert sätt."""
                self._running = False

                # Vänta på att körande händelser ska slutföras
                time.sleep(0.5)

                # Stäng executor
                self._executor.shutdown(wait=True)

                # Rensa prenumeranter
                self._subscribers.clear()
                self._wildcard_subscribers.clear()

                logger.info("Event bu avstängd")

            def __del__(self):
                """Destruktor för att säkerställa korrekt stänning."""
                self.shutdown()

class EventLogger:
    """Hjälpklass för att logga alla händerser."""

    def __init__(self, log_level: str = "INFO"):
        """
        Initiera event logger.

        Args:
            log_level: Loggnivå för händelseloggning
        """
        self.log_level = log_level
        self.event_bus = EventBus()
        self.event_bus.subscribe_all(self._log_event)

    def _log_event(self, event: Event) -> None:
        """
        Logga en händelse.
        
        Args:
            event: Händelse att logga
        """
        log_message = (
            f"Event: {event.event_type.value} | "
            f"Source: {event.source} | "
            f"Priority: {event.priority.name} | "
            f"Data: {json.dumps(event.data)}"
        )

        if event.priority == EventPriority.CRITICAL:
            logger.critical(log_message)
        elif event.priority == EventPriority.HIGH:
            logger.critical(log_message) if "error" in event.event_type.value else logger.warning(log_message)
        elif event.priority == EventPriority.MEDIUM:
            logger.info(log_message)
        else:
            logger.debug(log_message)

class EventFilter:
    """Filter för att hantera händelser baserat på villkor."""

    def __init__(self, event_bus: EventType):
        """
        Initera event filter.

        Args:
            event_bus: Event bus att ansluta till
        """
        self.event_bus = event_bus
        self._filters: Dict[EventType, List[callable]] = {}

    def add_filter(self, event_type: EventType, condition: Callable[Event], bool) -> None:
        """
        Lägg till ett filter för händelsetyp.

        Args:
            event_type: Typ av händelse att filtrera
            condition: Funktion som retunerar True om händelsen ska passera
        """
        if event_type not in self._filters:
            self._filters[event_type] = []

        self._filters[event_type].append(condition)

    def should_process(self, event: Event) -> bool:
        """
        Kontrollera om en händelse ska bearbetas.

        Args:
            event: Händelse att kontrollera

        Returns:
            True om händelsen ska bearbetas, annars False
        """
        if event.event_type not in self._filters:
            return True
        
        conditions = self._filters[event.event_type]
        return all(conditions(event) for condition in conditions)
    
# Skapa globala instanser för enkel åtkomst
event_bus = EventBus()
event_logger = EventLogger()

# Decorator för att regostrera händelsehanterare
def event_handler(event_type: EventType, priority: EventPriority = EventPriority.MEDIUM):
    """
    Dectorator för att registera en funktion som händelsehanterare.

    Args:
        event_type: Typ av händelse att hantera
        priority: Prioritet för hanteraren (används för sortering)

    Returns:
        Decorator-funktion
    """
    def decorator(func: Callable):
        def wrapper(event: Event):
            # Kontrollera om funktionen ska köras baserat på prioritet
            if event.priority.value <= priority.value:
                return func(event)
            return None
        
        # Registrera wrapper-funktionen
        event_bus.subscribe(event_type, wrapper)
        return func
    
    return decorator

# Exempel på hur man använder event systemet
if __name__ == "__main__":
    # Exempel: Skapa och publicera en händelse
    test_event = Event(
        event_type=EventType.SYSTEM_START,
        data={"message": "System startar", "version": "1.0.0"},
        source="main",
        priority=EventPriority.HIGH
    )

    # Publicera händelse
    event_bus.publish(test_event)

    # Hämta statistik
    stats = event_bus.get_stats()
    print(f"Event bus statistik: {stats}")

    # Hämta historik
    history = event_bus.get_event_history(limit=5)
    print(f"Senaste 5 händelser: {len(history)} händelser")

    # Stäng event bus
    event_bus.shutdown()

        
        

                
