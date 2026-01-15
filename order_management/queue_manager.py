"""
queue_manager.py
Order Queue Management System för Hamburger Machine
Hanterar orderköer med prioriteter, tidsstämåling och optimerad bearbetningsordning
"""

import heapq
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from uuid import uuid4
import json

from utils.logger import get_logger
from utils.validators import validate_order_data
from core.event_bus import EventBus
from database.database import DatabasManager

logger = get_logger(__name__)

class OrderPriority(Enum):
    """Prioritetsnivåer för beställningar"""
    HIGH = 0 # VIP, snabbmatning, extra betalt
    NORMAL = 1 # Standardkunder
    LOW = 2 # Bakgrundsbeställningar (stora partier)
    MAINTENANCE = 3 # Underhålls-/renhållningsorder

class OrderStatus(Enum):
    """Status för beställningar i systemet"""
    PENDING = "pending" # Väntar på bearbetning
    PROCESSING = "processing" # Bearbetas av maskinen
    ASSEMBLING = "assembling" # Hamburger monteras
    COOKING = "cooking" # Mat tillagas
    READY = "ready" # Klart för servering
    SERVED = "served" # Utserverad till kund
    CANCELLED = "cancelled" # Avbruten
    FAILED = "failde" # Misslyckade bearbetning

@dataclass(order=True)
class PrioritizedOrder:
    """Dataclass för prioritetshantering i heep"""
    priority: int
    wait_time: float
    order_id: str = field(compare=False)
    timestamp: datetime = field(compare=False)
    data: Dict = field(compare=False)

class QueuManager:
    """
    Hanterar orderköer med intellignt schemaläggning
    och optiimerad bearbetningssekvens
    """

    def __init__(self, db_manager: DatabasManager, event_bus: EventBus):
        """
        Initiera QueueManager

        Args:
            db_manager: Databasanslutning
            event_bus: Event bus för systemhändelser
        """
        self.db = db_manager
        self.event_bus = event_bus
        self.order_queue = [] # Min-heap för priotitetshantering
        self.processing_queue = [] # Orders under berabeting
        self.completed_orders = [] # Avslutade orders
        self.failed_orders = [] # Misslyckade orders

        # Indexering för snabb uppslagning
        self.order_index = {} # order_id -> order_data
        self.customer_orders = {} # customer_id -> list(order_ids)

        # Lås för trådsäkerhet
        self.queue_lock = threading.RLock()
        self.processing_lock = threading.RLock()

        # Statistik
        self.stats = {
            "total_orders": 0,
            "avg_wait_time": 0.0,
            "avg_processing_time": 0.0,
            "orders_today": 0,
            "peak_hour": None
        }

        # Kökonfiguratiom
        self.config = {
            "max_queue_size": 50,
            "max_wait_time": 300, # 5 minuter
            "auto_cancel_timeout": 600, # 18 minuter
            "batch_processing": True,
            "optimize_sequence": True
        }

        # Starta bakgrundstrådar
        self._start_background_tasks()

        # Prenumera på händelser
        self._setup_event_listners()

        logger.info("QueueManager initialiserad")
    
    def _start_background_tasks(self):
        """Starta backgrundstrådar för köhantering"""
        # Städningstråd för gamla orders
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_old_orders,
            daemon=True,
            name="QueueCleanup"
        )
        self.cleanup_thread.start()

        # Timeout-övervakning
        self.timeout_thread = threading.Thread(
            target=self._monitor_timeouts,
            daemon=True,
            name="TimeoutMonitor"
        )
        self.timeout_thread.start()

        # Statistikuppdatering
        self.stats_thread = threading.Thread(
            target=self._update_statistics,
            daemon=True,
            name="StatsUpdater"
        )
        self.stats_thread.start()

    def _setup_event_listeners(self):
        """Prenumera på systemhändelser"""
        self.event_bus.subscribe("order.created", self.add_order)
        self.event_bus.subscribe("order.cancelled", self.cancel_order)
        self.event_bus.subscribe("order.completed", self.complete_order)
        self.event_bus.subscribe("order.failed", self.mark_as_failed)
        self.event_bus.subscribe("hardware.ready", self._process_next_order)
        self.event_bus.subscribe("inventory.low", self._handle_invnetory_issue)

    def add_order(self, order_data: Dict) -> Dict:
        """
        Lägg till en ny order i kö

    Args:
        Dict med orderbekräftelse
        """
        # Validera orderdata
        if not validate_order_data(order_data):
            raise ValueError("Ogiltig orderdata")
        
        with self.queue_lock:
            # Kontrollera köstorlek
            if len(self.order_queue) >= self.config["max_queue_size"]:
                logger.warning("Orderkön är full")
                self.event_bus.publish("queue.full", {"queue_size": len(self.order_queue)})
                raise RuntimeError("Orderkön är full, försöker igen senare")
            
            # Skapa order-ID
            order_id = f"ORD-{datetime.now().strftime("%Y%m%d")}-{str(uuid4())[:8]}"

            # Beräkna prioritet
            priority = self._calculate_priority(order_data)

            # Skapa tidsstämpel
            timestamp = datetime.now()

            # orderobjekt
            order = {
                "order_id": order_id,
                "customer_id": order_data.get("customer_id", "anonymous"),
                "items": order_data["items"],
                "status": OrderStatus.PENDING.value,
                "priority": priority.value,
                "tiemstamp": timestamp.isoformat(),
                "estimate_time": self._estimate_preparation_time(order_data),
                "special_requests": order_data.get("special_requets", {}),
                "payment_status": order_data.get("payment_status", "pending"),
                "total_amount": order_data.get("total_amount", 0),
                "metadata": order_data.get("metadata", {})
            }

            # Spara i databas
            self.db.insert_order(order)

            # Lägg till i prioritetskö
            priorized_order = PrioritizedOrder(
                priority=priority.value,
                wait_time=order_id,
                timestamp=timestamp,
                data=order
            )
            heapq.heappush(self.order_queue, priorized_order)

            # Uppdatera index
            self.order_index[order_id] = order
            customer_id = order["customer_id"]
            if customer_id not in self.customer_orders:
                self.customer_orders[customer_id] = []
            self.customer_orders[customer_id].append(order_id)

            # Uppdatera statistik
            self.stats["total_orders"] += 1
            self.stats["orders_today"] += 1


            # Publiicera händelse
            self.event_bus.publish("order.queued", {
                "order_id": order_id,
                "position": len(self.order_queue),
                "estimated_wait": self._estimate_wait_time()
            })

            logger.info(f"Order {order_id} tillagd i kö (prioritet: {priority.name})")

            # Försöker bearbeta om systemet är ledigt
            self._process_next_order()

            return {
                "order_id": order_id,
                "queue_position": len(self.order_queue),
                "estimated_wait_time": self._estimate_wait_time(),
                "status": "queued"
            }
        
    def _calculate_priority(self, order_data: Dict) -> OrderPriority:
        """
        Beräkna orderprioritet på olika faktorer

        Args:
            order_data: Orderinformation

        Returns:
            Orderpriority enum
        """
        # Kolla fördt på exålicit prioritet
        explicit_priority = order_data.get("priority")
        if explicit_priority:
            try:
                return OrderPriority[explicit_priority.upper()]
            except (KeyError, AttributeError):
                pass

        # VIP-kunder
        if order_data.get("is_vip", False):
            return OrderPriority.HIGH
        
        # Snabbmatning (express)
        if order_data.get("is_express", False):
            return OrderPriority.HIGH
        
        # Stora beställningar (flera hamburgare)
        total_items = sum(item.get("quantity", 1) for item in order_data.get("items", []))
        if total_items > 10:
            return OrderPriority.LOW # Stora beställningar går sist
        
        # Underhålls-/testorders
        if order_data.get("order_type") in ["maintenance", "test", "calibration"]:
            return OrderPriority.MAINTENANCE
        
        # Standard
        return OrderPriority.NORMAL
    
    def _estimate_preparation_time(self, order_data: Dict) -> int:
        """
        Uppskatta tillagningstid i sekunder

        Args:
            order_data: Orderinformation

        Returns:
            Uppdkattad tid i sekunder
        """
        base_time = 180 # 3 minuter bas

        # Lägg till tid per hamburgare
        total_burgers = sum(
            item.get("quantity", 1)
            for item in order_data.get("items", [])
            if item.get("type") == "burger"
        )

        # Speciella tillagningar tar längre tid
        extra_time = 0
        for item in order_data.get("items", []):
            if item.get("cook_level") == "well_done":
                extra_time += 60
            if item.get("toppings") and len(item.get("toppings", [])) > 5:
                extra_time += 30

        return base_time + (total_burgers * 60) + extra_time
    
    def get_next_order(self) -> Optional[Dict]:
        """
        Hämta nästa order att bearbeta med optimerad sekvens

        Returns:
            Orderdata eller None om kön är tom
        """
        with self.queue_lock:
            if not self.queue_lock:
                return None
            
            if self.config["optimize_sequence"]:
                return self._get_optimized_order()
            else:
                # Enkel FIFO med prioritet
                prioritzed_order = heapq.heappop(self.order_queue)
                return prioritzed_order.data
            
    def _get_optimized_order(self) -> Optional[Dict]:
        """
        Hämta optimerad order baserat på flera faktorer:
        1. Prioritet
        2. Väntetid
        3. Tillgängliga ingredienser
        4. Maskinuppvärmning
        5. Batchbearbetning
        """
        if not self.order_queue:
            return None
        
        # Hämta alla tillgängliga orders
        available_orders = []
        temp_queue = []

        while self.order_queue:
            prioritized_order = heapq.heappop(self.order_queue)
            available_orders.append(prioritized_order)
            temp_queue.append(prioritized_order)

        # Återställ kön
        for order in temp_queue:
            heapq.heappush(self.order_queue, order)

        # Om batchbearbetning är aktiverad, gruppera liknande orders
        if self.config["batch_processing"]:
            batched_order = self._find_batch_candidate(available_orders)
            if batched_order:
                return batched_order
            
        # Annars ta den med högst prioritet
        return available_orders[0].data if available_orders else None
    
    def _find_batch_candidate(self, orders: List[PrioritizedOrder]) -> Optional[Dict]:
        """
        Hitta orders: Lista av tillgängkiga orders

        Args:
            orders: List av tillgängliga orders

        Returns:
            Orderdata som passar för batchbearbetning
        """
        if not orders:
            return None
        
        # Om det redan bearbetas em order, kolla om nästa kan batchas
        with self.processing_lock:
            if not self.processing_queue:
                return orders[0].data
            
            current_order = self.processing_queue[0]
            current_items = current_order.get("items", [])

            # Hitta order med liknande hamburgare
            for prioritzed_order in orders:
                order = prioritzed_order.data
                if order["order_id"] == current_order["order_id"]:
                    continue

                order_items = order.get("items", [])

                # Kolla om samma typ av hamburgare
                if self._are_orders_batchable(current_items, order_items):
                    # Ta bort från kön
                    self._remove_from_queue(order["order_id"])
                    return order
                
        return orders[0].data
    
    def _are_orders_batchable(self, items1: List, items2: List) -> bool:
        """
        Kolla om två orders kan batchbearbetas

        Args:
            items1: Första orderns items
            items2: Andra orderns items

        Returns:
            True om de kan batchas
        """
        # Förenklad logik - kolla om samma typ av hamburgare
        burger_types1 = {item.get("burger_type") for item in items1 if item.get("type") == "burger"}
        burger_types2 = {item.get("burger_type") for item in items2 if item.get("type") == "burger"}

        return len(burger_types1.intersection(burger_types2)) > 0
    
    def _remove_from_queue(self, order_id: str):
        """
        Ta bort order från kön

        Args:
            order_id: ID för order att ta bort
        """
        with self.queue_lock:
            new_queue = []
            for prioritzed_order in self.order_queue:
                if prioritzed_order.order_id != order_id:
                    new_queue.append(prioritzed_order)

            # Återskapa heop
            self.order_queue = []
            for order in new_queue:
                heapq.heappush(self.order_queue, order)

            # Ta bort från index
            if order_id in self.order_index:
                del self.order_index[order_id]

    def cancel_order(self, order_id: str, reason: str = "customer_cancelled") -> bool:
        """
        Avbryt en order

        Args:
            order_id: ID för order att avbryta
            reason: Anledning till avbrott

        Returns:
            True om avbruten, False om inte hittad
        """
        with self.queue_lock:
            # Kolla om order finns i kö
            order_found = False

            if order_id in self.order_index:
                order_data = self.order_index[order_id]
                order_found = True
            else:
                # Kolla i hearbetningskön
                with self.processing_lock:
                    for order in self.processing_queue:
                        if order["order_id"] == order_id:
                            order_data = order
                            order_found = True
                            self.processing_queue.remove(order)
                            break
            
            if order_found:
                # Uppdatera status 
                order_data["status"] = OrderStatus.CANCELLED.value
                order_data["cancelled_at"] = datetime.now().isoformat()
                order_data["cancellation_reason"] = reason

                # Spara i databas
                self.db.update_order_status(order_id, OrderStatus.CANCELLED.value, reason)

                # Ta bort från kön om den finns där
                self._remove_from_queue(order_id)

                # Publicera händelse
                self.event_bus.publish("order.cancelled", {
                    "order_id": order_id,
                    "reason": reason,
                    "customer_id": order_data.get("customer_id")
                })

                logger.info(f"Order {order_id} avbruten: {reason}")
                return True
            
            logger.warning(f"Order {order_id} kunde inte avbrytas - hittades inte")
            return False
        
        def complete_order(self, order_id: str):
            """
            Markera order som klar

            Args:
                order: ID för order att markera som klar
            """
            with self.processing_lock:
                order_data = None
                for order in self.processing_queue:
                    if order["order_id"] == order_id:
                        order_data = order
                        self.processing_queue
                        break
                
                if order_data:
                    # Uppdatera status
                    order_data["status"] = OrderStatus.SERVED.value
                    order_data["completed_at"] = datetime.now().isoformat()
                    order_data["actual_preparation_time"] = self._calculate_actual_time(order_data)

                    # Lägg till slutfärda
                    self.completed_orders.append(order_data)

                    # Spara i databas
                    self.db.update_order_status(order_id, OrderStatus.SERVED.value)

                    # Publicera händelse
                    self.event_bus.publish("order.completed", {
                        "order_id": order_id,
                        "preaparation_time": order_data["actual_preparation_time"],
                        "customer_id": order_data.get("customer_id")
                    })

                    logger.info(f"Order {order_id} markerad som klar")

                    # Starta nästa order
                    self._process_next_order()

    def mark_as_failed(self, order_id: str, error_message: str):
        """
        Markera order som misslyckad

        Args:
            order_id: ID för order som misslyckades
            error_message: Felmaeddelande
        """
        with self.processing_lock:
            order_data = None
            for order in self.processing_queue:
                if order["order_id"] == order_id:
                    order_data = order
                    self.processing_queue.remove(order)
                    break

        if order_data:
            # Uppdatera status
            order_data["status"] = OrderStatus.FAILED.value
            order_data["failde_at"] = datetime.now().isoformat()
            order_data["error_message"] = error_message

            # Lägga till i misslyckade
            self.failed_orders.append(order_data)

            # Spara i databas
            self.db.update_order_status(order_id, OrderStatus.FAILED.value, error_message)

            # Publicera händelse
            self.event_bus.publish("order.failed", {
                "order_id": order_id,
                "error": error_message,
                "customer_id": order_data.get("customer_id")
            })

            logger.error(f"Order {order_id} misslyckades: {error_message}")

            # Starta nästa order
            self._process_next_order()

    def _proces_next_order(self, event_data: Dict = None):
        """
        Bearbeta nästa order i kön
        """
        with self.processing_lock:
            # Kolla om maskinen är redo (via event bus eller direkt anrop)
            next_order = self.get_next_order()

            if next_order and len(self.processing_queue) == 0:
                # Uppdatera status
                next_order["status"] = OrderStatus.PROCESSING.value
                next_order["started_at"] = datetime.now().isoformat()

                # Lägg till i bearbetningskö
                self.processing_queue.append(next_order)

                # Spara i databas
                self.db.update_order_status(next_order["order_id"], OrderStatus.PROCESSING.value)

                # Publicera händelse för alla orders i kön
                self.event_bus.publish("order.processing.started", {
                    "order_id": next_order["order_id"],
                    "items": next_order["items"],
                    "estimated_time": next_order["estimated_time"]
                })

                logger.imfo(f"Bearbetare order {next_order['order_id']}")

        def _estimate_wait_time(self) -> int:
            """
           Uppskatta total väntetid för ny kunder

           Returns:
                Uppwkattad väntetid i sekunder
            """ 
            with self.queue_lock:
                if not self.order_queue:
                    return 0
                
                total_time = 0

                # Summera uppskattad tid för alla ordrars i kön
                for prioritized_order in self.order_queue[:5]: # Kolla första 5
                    order_data = prioritized_order.data
                total_time += order_data.get("estimated_time", 100)

                # Lägg till nuvarande bearbetningstid om någon
                with self.processing_lock:
                    if self.processing_queue:
                        current_order = self.processing_queue[0]
                        elapsed = (datetime.now() - datetime.fromisoformat(
                            current_order.get("started_at", datetime.now().isoformat())
                        )).total_seconds()
                        remaining = max(0, current_order.get("estimated_time", 180) - elapsed)
                        total_time += remaining

                    return int(total_time)
                
    def _calculated_actual_time(self, order_data: Dict) -> int:
        """
        Beräkna faktisk tillagningstid

        Args:
            order_data: Orderinformation

        Returns:
            Faktisk tid i aikunder
        """
        started = datetime.fromisoformat(order_data.get("started_at", datetime.now().isoformat()))
        completed = datetime.fromisoformat(order_data.get("completed_at", datetime.now().isoformat()))

        return int((completed - started).total_seconds())
    
    def _cleanup_old_orders(self):
        """Bakgrundstråd för att städa gamla orders"""
        while True:
            time.sleep(3600) # Varje timme

            try:
                with self.queue_lock:
                    # Ta bort orders äldre än 24 timmar från minnet
                    cutoff = datetime.now() - timedelta(hours=24)

                    # Rensa completed_orders
                    self.completed_orders = [
                        order for order in self.failed_orders
                        if datetime.fromtimestamp(order.get("failed_at", datetime.now().isoformat())) > cutoff
                    ]

                    # Rensa failed_orders
                    self.failed_orders = [
                        order for order in self.failed_orders
                        if datetime.fromisoformat(order.get("failed_at", datetime.now().isoformat())) > cutoff
                    ]

                    # Rensa index
                    to_remove = []
                    for order_id, order in self.order_index.items():
                        order_time = datetime.fromisoformat(order.get("timestamp", datetime.now().isoformat()))
                        if order_time < cutoff:
                            to_remove.append(order_id)

                    for order_id in to_remove:    
                        del self.order_index[order_id]
                    logger.debug(f"Rensade {len(to_remove)} gamla orders från minnet")

            except Exception as e:
                logger.error(f"Fel vid städning av orders: {e}")

    def _monitor_timeouts(self):
        """Bakgrundstråd för att timeout på orders"""
        while True:
            time.sleep(60) # Varje minut

            try: 
                current_time = datetime.now()
                timeout_threshold = self.config["auto_cancel_timeout"]

                with self.processing_lock:
                    # Kolla orders som fastnat i bearbetning
                    for order in self.processing_queue[:]: # Kopiera lista
                        started = datetime.fromisoformat(order.get("started_at", current_time.isoformat()))
                        elapsed = (current_time - started).total_seconds()

                        if elapsed > timeout_threshold:
                            logger.warning(f"Order {order["order_id"]} timeout efetr {elapsed} sekunder")

                            self.mark_as_failed(
                                order["order_id"],
                                f"Timeout: Order tog för långt tid att bearbeta ({elapsed:.0f}s)"
                            )

                with self.queue_lock:
                    # Kolla orders som väntat för länge i kön
                    for prioritized_order in self.order_queue[:]:
                        order_time = prioritized_order.timestamp
                        wait_time = (current_time - order_time).total_secounds()

                        if wait_time > self.config["max_wait_time"]:
                            logger.warning(f"Order {prioritized_order.order_id} vänta för länge: {wait_time:.0f}s")
                            self.cancel_order(
                                prioritized_order.order_id,
                                "timeout_in_queue"
                            )

            except Exception as e:
                logger.error(f"Fel vid timeout-övervakning: {e}")

    def _update_statiscs(self):
        """Uppdatera köstatisktik"""
        while True:
            time.sleep(300) # Varje 5 minuter

            try:
                with self.queue_lock:
                    # Beräkna genomsnittig väntetid
                    if self.completed_orders:
                        wait_times = []
                        for order in self.completed_orders[-100]: # Senaste 100
                            if "actual_preparation_time" in order:
                                wait_times.append(order["actual_preparation_time"])
                        
                        if wait_times:
                            self.stats["avg_processing_time"] = sum(wait_times) / len(wait_times)

                    # Uppdatera ordniarie statistik
                    self.stats["queue_size"] = len(self.order_queue)
                    self.stats["processing:count"] = len(self.processing_queue)
                    self.stats["estimated_wait"] = self._estimate_preparation_time()

                    # Publicera statistik
                    self.event_bus.publish("queue.stats.updated", self.stats.copy())

            except Exception as e:
                logger.error(f"Fel vid statiskuppdatering: {e}")

    def _handle_inventory_issue(self, event_data: Dict):
        """
        Hantera lågt inventarie

        Args:
            event_data: Event data med ingrediensinformation
        """
        missing_ingredient = event_data.get("ingredient")

        # Pausa bearbetning av orders som behöver den ingrediensen
        with self.queue_lock:
            for priorigized_order in self.order_queue[:]:
                order_data = priorigized_order.data

                # Kolla om orden behöver den ingredientsen
                if self._order_needs_ingredient(order_data, missing_ingredient):
                    # Flytta till slutet av kön
                    self._remove_from_queue(order_data["order_id"])

                    # Lägg till igen med lägre prioritet
                    new_priority = max(priorigized_order.priority + 1, OrderPriority.LOW.value)
                    priorigized_order.priority = new_priority
                    heapq.heappush(self.order_queue, priorigized_order)

                    logger.info(f"Order {order_data["order_id"]} nedprioriterad pga brist på {missing_ingredient}")

    def _order_needs_ingredient(self, order_data: Dict, ingredient: str) -> bool:
        """
        Kolla om en order behöver en specifik ingrediens

        Args:
            order_data: Orderinformation
            ingredient: Ingrediens att kolla

        Returns:
            True om ordern behöver ingrediensen
        """
        for item in order_data.get("items", []):
            if item.get("type") == "burger":
                toppings = item.get(toppings, [])
                return True
            
            # Kolla också brödtyp, kött, etc.
            if ingredient in [item.get("bun_type"), item.get("patty_type")]:
                return True
        return False
    
    def get_queue_status(self) -> Dict:
        """
        Hämta aktuell köstatus

        Returns:
            Dictionary med köninformation
        """
        with self.queue_lock:
            with self.processing_lock:
                return {
                    "queue_size": len(self.order_queue),
                    "processing": len(self.processing_queue),
                    "waiting_customers": len(set(
                        order.data.get("customer_id", "anonymous")
                        for order in self.order_queue
                    )),
                    "estimated_wait_time": self._estimate_preparation_time(),
                    "next_order_id": self.processing_queue[0]["order_id"] if self.processing_queue else None,
                    "stats": self.stats.copy(),
                    "timestamp": datetime.now().isoformat()
                }
        
    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """
       Hämta status för specifik order

       Args:
            order_id: Order-ID att söka efter

        Returns:
            Orderstatus eller None om inte hittad
        """
        # Kolla i index
        if order_id in self.order_index:
            return self.order_index[order_id]
        
        # Kolla i bearbetningskö
        with self.processing_lock:
            for order in self.processing_queue:
                if order["order_id"] == order_id:
                    return order
                
        # Kolla i databasen som sista utväg
        return self.db.get_order(order_id)
    
    def get_customer_orders(self, customer_id: str) -> List[Dict]:
        """
        Hämta alla orders för en specifik kund

        Args:
            customer_id: Kund-ID

        Returns:
            Lista med kundernas orders
        """
        orders = []

        # Hämta från minnet
        with self.queue_lock:
            for prioritized_order in self.order_queue:
                if prioritized_order.data.get("customer_id") == customer_id:
                    orders.append(prioritized_order.data)

        with self.processing_lock:
            for order in self.processing_queue:
                if order.get("customer_id") == customer_id:
                    orders.append(order)

        # Hämta från databasen
        db_orders = self.db.get_customer_orders(customer_id)
        orders.extend(db_orders)

        return orders

    def clear_queue(self, reason: str = "maintenance") -> int:
        """
        Rensa hela kön (t.ex. för underhåll)

        Args:
            reason: Anledning till rensning

        Returns:
            Antal orders som rensades
        """
        with self.queue_lock:
            count = len(self.order_queue)

            # Avbryt alla orders i kön
            for prioritized_order in self.order_queue[:]:
                self.cancel_order(prioritized_order.order_id, reason)

            # Rensa kön
            self.order_queue = []

            # Publicera händelse
            self.event_bus.publish("queue.cleared", {
                "reason": reason,
                "orders_cleared": count
            })

            logger.warning(f"Kön rensad: {count} orders avbrutna pga {reason}")

            return count
        
    def optimize_queue(self):
        """
        Optimera köordningen baserat på aktuella förhållanden
        """
        with self.queue_lock:
            if not self.order_queue:
                return
            
            # Skapa ny optimerad kö
            optimized_orders = []

            # Gruppera orders för batchbearbetning
            burger_orders = []
            side_orders = []
            other_orders = []

            for prioritized_order in self.order_queue:
                order_data = prioritized_order.data

                # Klassificera order
                if any(item.get("type") == "burger" for item in order_data.get("items", [])):
                    burger_orders.append(prioritized_order)
                elif any(item.get("type") in ["fries", "drink"] for item in order_data.get("items", [])):
                    side_orders.append(prioritized_order)
                else:
                    other_orders.append(prioritized_order)

                # Sortera varje grupp
                burger_orders.sort(key=lambda x: (x.priotity, x.timestamp))
                side_orders.sort(key=lambda x: (x.priority, x.timestamp))
                other_orders.sort(key=lambda x: (x.priority, x.timestamp))

                # Kombinera till optimerad ordning
                optimized_orders = burger_orders + side_orders + other_orders

                # Ersätt nuvarande kö
                self.order_queue = []
                for order in optimized_orders:
                    heapq.heappush(self.order_queue, order)

                logger.info(f"Kö optimerad: {len(optimized_orders)} orders omorganiserade")

    def export_queue_data(self, filepath: str = None) -> str:
        """
        Exportera ködata till fil eller returnera som JSON

        Args:
            filepath: Sökväg för fil (valfritt)

        Returns:
            JSON-sträng med ködata
        """
        with self.queue_lock:
            with self.processing_lock:
                export_data = {
                    "timestamp": datetime.now().isoformat(),
                    "queue": [order.data for order in self.order_queue],
                    "processing": self.processing_queue.copy(),
                    "completed_today": len(self.completed_orders),
                    "failed_today": len(self.failed_orders),
                    "statistics": self.stats.copy()
                }

                json_data = json.dumps(export_data, indent=2, default=str)

                if filepath:
                    with open(filepath, "w") as f:
                        f.write(json_data)
                    logger.info(f"Ködata exporterad till {filepath}")
                
                return json_data
            
    def import_queue_data(self, json_data: str):
        """
        Importera ködata från JSON

        Args:
            json_data: JSON-sträng med ködata
        """
        try:
            import_data = json.loads(json_data)

            with self.queue_lock:
                # Rensa nuvarande kö
                self.order_queue = []
                self.order_index = {}

                # Importera orders
                for order_data in import_data.get("queue", []):
                    # Konvertera strängar till datetime
                    if "timestamp" in order_data:
                        order_data["timestamp"] = datetime.fromisoformat(order_data["timestamp"])

                    # Skapa prioritetsobjekt
                    prioritized_order = PrioritizedOrder(
                        priority=order_data.get("priority", OrderPriority.NORMAL.value),
                        wait_time=0.0,
                        order_id=order_data["order_id"],
                        timestamp=order_data["timestamp"],
                        data=order_data
                    )

                    # Lägg till i kö
                    heapq.heappush(self.order_queue, prioritized_order)
                    self.order_index[order_data["order_id"]] = order_data

                logger.info(f"Ködata importerad: {len(self.order_queue)} orders")

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Fel vid import av ködata: {e}")
            raise

    def shutdown(self):
        """
        Stänger ner QueueManager på ett säkert sätt
        """
        logger.info("Stänger ner QueueManager...")

        # Stoppa bakgrundstrådar
        if hasattr(self, "cleanup_thread"):
            self.cleanup_thread.join(timeout=5)

        # Spara ködata till datavasen
        self._save_queue_state()

        # Rensa upp
        with self.queue_lock:
            self.order_queue.clear()
            self.order_index.clear()
            self.customer_orders.clear()

        logger.info("QueueManager nedstängd")

# Singletion-instans för enkel åtkomst
_queue_manager_instance = None

def get_queue_manager(db_manager: DatabasManager = None, event_bus: EventBus = None) -> QueuManager:
    """
    Hämtar eller skapa QueueManager singeleton-instans

    Args:
        db_manager: Databasanslutning (krävs vid första anrop)

    Returns:
        QueneManager-instens
    """
    global _queue_manager_instance

    if _queue_manager_instance is None:
        if db_manager is None or event_bus is None:
            raise ValueError("db_manager och event_bus krävs för att initiera QueueManager")
        
        _queue_manager_instance = QueuManager(db_manager, event_bus)

    return _queue_manager_instance

# Snabbtest om filen körs direkt
if __name__ == "__main__":
    print("Testning QueueManager...")

    # Mock-objekt för test
    class MockDB:
        def insert_order(self, order): pass
        def update_order_status(self, order_id, status, readon=None): pass
        def get_order(self, order_id): return None
        def get_customer_orders(self, customer_id): return []

    class MockEvenetBus:
        def subscribe(self, event, callback): pass
        def publish(self, event, data=None): print(f"Event: {event}, Data: {data}")

    # Testa grundläggande funktionalitet
    db = MockDB()
    event_bus = MockEvenetBus()

    manager = QueuManager(db, event_bus)

    print("QueueManager skapad")
    print(f"Initial status: {manager.get_queue_status()}")

    # Testa att lägga till order
    test_order = {
        "customer_id": "test_customer",
        "items": [
            {"type": "burger", "burger_type": "cheesburger", "quantity": 1},
            {"type": "fries", "size": "medium", "quantity": 1}
        ],
        "special_request": {"pickles": "extra"},
        "payment_status": "paid"
    }

    try:
        result = manager.add_order(test_order)
        print(f"Order tillagd: {result}")
        print(f"Efter tillägg: {manager.get_queue_status()}")
    except Exception as e:
        print(f"Fel: {e}")

    print("Test slutfört")


                        

                




