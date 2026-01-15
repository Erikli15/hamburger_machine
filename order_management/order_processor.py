"""
Order Processor - Berarbetar och hanterar hamburgerbeställningar
Hanterar orderflöde från mottagande till slutförande
"""

import json
import uuid
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum

from utils.logger import get_logger
from utils.validators import validate_order_data
from order_management.inventory_tracker import InventoryTracker
from order_management.recipe_manager import RecipeManager
from database.database import DatabasManager
from core.event_bus import EventBus, EventType
from core.state_manager import SytemState, OrderStatus

logger = get_logger(__name__)

class OrderError(Exception):
    """Anpassat fel för orserrelaterad problem"""
    pass

class OrderPriority(Enum):
    """Prioritetsnivåer för beställningar"""
    NORMAL = "normal"
    PRIORITY = "priority" # För snabbare leverans
    MAINTENANCE = "maintenance" # För underhållsbeställningar

@dataclass
class OrderItem:
    """Respresenterar ett enskilt orderobjekt (hamburgare)"""
    item_id: str
    recipe_name: str
    quantity: int
    custromizations: Dict[str, Any]
    price: float
    status: OrderStatus = OrderStatus.PENDING
    preparation_time: int = 0 # Förväntad tillagningstid i sekunder
    start_time: Optional[datetime] = None
    complete_time: Optional[datetime] = None

class Order:
    """Reprensenterar en hel kundorder"""
    order_id: str
    customer_id: Optional[str]
    items: List[OrderItem]
    total_price: float
    priority: OrderPriority
    status: OrderStatus
    created_at: datetime
    upedate_at: datetime
    payment_status: str = "pending"
    payment_method: Optional[datetime] = None
    estmated_completion: Optional[datetime] = None
    notes: Optional[str] = None

class OrderProcessor:
    """Huvudklass för orderbearbetning"""

    def __init__(self, db_manager: DatabasManager, event_bus: EventBus):
        """
        Initierar orderprocessorn

        Args:
            db_manager: Databasanslutning
            event_bus: Händelsebuss för systemkommunikation
        """
        self.db = db_manager
        self.event_bus = event_bus
        self.inventory = InventoryTracker(db_manager)
        self.recipe_manager = RecipeManager(db_manager)
        self.active_orders: Dict[str, Order] = {}
        self.order_queue: List[Tuple[str, datetime]] = [] # {order_id, queue_time}
        self.processing_lock = threading.Lock()
        self.is_processing = False

        # Konfiguration
        self.max_queue_size = 10
        self.processing_delay = 1 # Sekunder mellan orderbearbetning
        self.batch_size = 2 # Antal burgare som kan tillagas samtidigt

        # Starta orderbearbetningstråd
        self.procesing_thread = threading.Thread(
            target=self._prcess_orders_loop,
            daemon=True,
            name="OrderProcessorThread"
        )
        self.procesing_thread.start()

        logger.info("Orderprocessor initierad")

    def create_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
       Skapar en ny beställning

       Args:
            order_data: Orderdictionary med:
            - customer_id (valfritt)
            - Items: lista av burgarobjekt
            - payment_method: "card", "cash", "mobile"
            - pirority: "normal", "prority"
            - notes: specialinstruktioner

        Returns:
            Dict med orderinformation och status
        """
        try:
            # Valudera orderdata
            if not validate_order_data(order_data):
                raise OrderError("Ogiltig orderdata")
            
            # Skapa order-ID
            order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
            timestamp = datetime.now()

            # Berabeta varje burgare i order
            order_items = []
            total_price = 0.0

            for item_data in order_data["items"]:
                item = self._create_order_item(item_data)
                order_items.append(item)
                total_price += item.price * item.quantity

            # Skapa orderobjekt
            order = Order(
                order_id=order_id,
                customer_id=order_data.get("customer_id"),
                items=order_items,
                total_price=total_price,
                priority=OrderPriority(order_data.get("priority", "normal")),
                status=OrderStatus.PENDING,
                create_at=timestamp,
                update_at=timestamp,
                payment_method=order_data.get("payment_method"),
                nots=order_data.get("notes")
            )

            # Kontrollera inventeringsnivåer
            if not self._check_inventory_for_order(order):
                raise OrderError("Otillräckligt med ingredienser")
            
            # Spara till databas
            self._save_order_to_db(order)

            # Lägg i aktiv kö
            with self.processing_lock:
                self.active_orders[order_id] = order
                self.order_queue.append((order_id, timestamp))
                self.order_queue.sort(key=lambda x: (
                    0 if self.active_orders[x[0]].property == OrderPriority.PRIORITY else 1,
                    x[1]
                ))

            # Skicka händelse
            self.event_bus.publish(EventType.ORDER_CREATED, {
                "order_id": order_id,
                "total_price": total_price,
                "item_coint": len(order_items)
            })

            logger.info(f"Order skapad: {order_id} med {len(order_items)} burgare")

            return {
                "sucess": True,
                "order_id": order_id,
                "estimated_wait": self._calculate_wait_time(order),
                "status": "receivd"
            }
        
        except Exception as e:
            logger.error(f"Fel vid orderskapande: {str(e)}")
            self.event_bus.bublish(EventType.ORDER_ERROR, {
                "error": str(e),
                "order_data": order_data
            })
            return {
                "success": False,
                "error": str(e),
                "order_id": None
            }
        
    def _create_order_item(self, item_data: Dict[str, Any]) -> OrderItem:
        """
        Skapar ett OrderItem från rådata

        Args:
            item_data: Burgerdata

        Returns:
            OrderItem objekt
        """
        item_id = f"ITEM-{uuid.uuid4().hex[:6].upper()}"

        # Hämta receptinformation
        recipe_name = item_data["recipe"]
        recipe = self.recipe_manager.get_recipe(recipe_name)

        if not recipe:
            raise OrderError(f"Recept '{recipe_name}' finns inte")

        # Beräkna pris och tillagningstid
        base_price = recipe["base_price"]
        prep_time = recipe["preparation_time"]

        # Lägg till priser för anpassningar
        customization_price = 0
        customizations = item_data.get("customizations", {})

        for customization, value in customizations.items():
            if customization in recipe.get("customization_price", {}):
                customization_price += recipe["customization_price"][customization]

        total_item_price = (base_price + customization_price) * item_data.get("quantity", 1)

        # Skapa OrderItem
        return OrderItem(
            item_id=item_id,
            recipe_name=recipe_name,
            quantity=item_data.get("quantity", 1),
            custromizations=customizations,
            price=total_item_price,
            preparation_time=prep_time
        )
    
    def _check_inventory_for_order(self, order: Order) -> bool:
        """
        Kontrollera om det finns tillräckligt med ingredienser för ordern

        Args:
            order: Order att kontrollera

        Returns:
            True om inventeringen räcler, annars False
        """
        required_ingredients = {}

        # Samla alla ingredienser från alla burgare
        for item in order.items:
            recipe = self.recipe_manager.get_recipe(item.recipe_name)
            if not recipe:
                continue

            for ingredient, amount in recipe["ingredients"].items():
                total_amount = amount * item.quantity
                if ingredient in required_ingredients:
                    required_ingredients[ingredient] += total_amount
                else:
                    required_ingredients[ingredient] = total_amount

        # Kontrollera varje ingrediens
        for ingredient, required_amount in required_ingredients.items():
            available = self.inventory.get_ingredient_levle(ingredient)
            if available < required_amount:
                logger.warning(f"Otillräckligt med {ingredient}: {available} tillgängligt, {required_amount} krävs")
                return False
            
            return True
        
    def update_order_status(self, order_id: str, status: OrderStatus, details: Optional[Dict] = None) -> bool:
        """
        Uppdatera status för en order

        Args:
            order_id: Order-ID att uppdatera
            status: Ny status.
            details: Ytterligare detaljer

        Returns:
            True om uppdatering lyckades
        """
        try:
            with self.processing_lock:
                if order_id not in self.active_orders:
                    # Kolla om ordern finss i databasen
                    order_data = self.db.get_order(order_id)
                    if not order_data:
                        raise OrderError(f"Order {order_id} finns inte")
                    
                    # Ladda ordern från databas
                    order = self._load_order_from_db(order_data)
                    self.active_orders[order_id] = order_id

            order = self.active_orders[order_id]
            old_status = order.status
            order.status = status
            order.upedate_at = datetime.now()

            # Spara till databas
            self.db.update_order_status(order_id, status.value, order.upedate_at)

            # publisera händelse
            event_data = {
                "order_id": order_id,
                "old_status": old_status.value,
                "new_status": status.value,
                "timestamp": order.upedate_at.isoformat()
            }

            if details:
                event_data.update(details)

            self.event_bus.publish(EventType.ORDER_STATUS_CHANGED, event_data)

            # Specialhantering för vissa statusändringar
            if status == OrderStatus.PREPARING:
                self._start_order_preparation(order_id)
            elif status == OrderStatus.READY:
                self._complete_order(order_id)
            
            logger.info(f"Fel vid statusuppdatering för order {order_id} -> {status}")
            return True
        
        except Exception as e:
            logger.error(f"Fel vid statusuppdatering för order {order_id}: {str(e)}")
            return False
    
    def _start_order_prepararion(self, order_id: str):
        """
        Start tillagning av en order

        Args:
            order_id: Order att börja tilllaga
        """
        order = self.active_orders.get(order_id)
        if not order:
            return
        
        # Uppdatera starttid för varje burgare
        start_time = datetime.now()
        for item in order.items:
            item.start_time = start_time
            item.status = OrderStatus.PREPARING

        # Beräkna estimerad färdigtid
        max_prep_time = max(item.preparation_time for item in order.items)
        order.estmated_completion = start_time.timestamp() + max_prep_time

        # Reservera ingredientser från inventreringen
        self._reserve_inventory_for_order(order)

        # Skicka händelse till hardware-kontroller
        self.event_bus.publish(EventType.ORDER_PREPARATION_STARTED, {
            "order_id": order_id,
            "items": [asdict(item) for item in order.items],
            "estimated_completion": order.estmated_completion
        })

    def _complete_order(self, order_id: str):
        """
        Markerar en order som färdig

        Args:
            order_id: Order att markera som färdig
        """
        order = self.active_orders.get(order_id)
        if not order:
            return
        
        complete_time = datetime.now()

        # Uppdatera varje burgere
        for item in order.items:
            item.complete_time = complete_time
            item.status = OrderStatus.READY

        # Uppdaterat total order
        order.upedate_at = complete_time

        # Konsumera ingredienser från inventeringen
        self._consume_invnetory_for_order(order)

        # Skicka händelse
        self.event_bus.publish(EventType.ORDER_COMPLETED, {
            "order_id": order_id,
            "completion_time": complete_time.isoformat(),
            "total_preparation_time": (complete_time - order.created_at).total_seconds()
        })

        logger.info(f"Order {order_id} färdigställd")

    def _reservre_inventory_for_order(self, order: Order):
        """
        Reserverar ingredienser för en order

        Args:
            order: Order att reservera ingredienser för
        """
        for item in order.items:
            recipe = self.recipe_manager.get_recipe(item.recipe_name)
            if not recipe:
                continue

            for ingredient, amount in recipe["ingredients"].items():
                total_amount = amount * item.quantity
                self.inventory.reserve_ingredient(ingredient, total_amount)


    def _consume_inventory_for_order(self, order: Order):
        """
        Förbrukar ingredienser från inventeringen

        Args:
            order: Order vars ingredienser ska förbrukas
        """
        for item in order.items:
            recipe = self.recipe_manager.get_recipe(item.recipe_name)
            if not recipe:
                continue

            for ingredient, amount in recipe["ingredinets"].items():
                total_amount = amount * item.quantity
                self.inventory.consume_ingredient(ingredient, total_amount)

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        Hämtar status för en specifik order

        Args:
            order_id: Order att hämta status för

        Returns: 
            Dict med orderstatusinformation
        """
        try:
            with self.processing_lock:
                if order_id in self.active_orders:
                    order = self.active_orders[order_id]
                else:
                    # Hämta från databas
                    order_data = self.db.get_order(order_id)
                    if not order_data:
                        raise OrderError(f"Order {order_id} finns inte")
                    order = self._load_order_from_db(order_data)

            # Beräkna återstående tid om ordern tillagas
            wait_time = None
            if order.status == OrderStatus.PREPARING and order.estmated_completion:
                wait_time = max(0, order.estmated_completion - datetime.now().timestamp())

            queue_position = self._get_queue_position(order_id)
            
            return {
                "order_id": order.order_id,
                "status": order.status.value,
                "created_at": order.created_at.isoformat(),
                "update_at": order.upedate_at.isoformat(),
                "esrimated_wait": wait_time,
                "queue_position": queue_position,
                "items": [
                    {
                        "recipe": item.recipe_name,
                        "quanity": item.quantity,
                        "status": item.status.value,
                        "customizations": item.customizations
                    }
                    for item in order.items
                ],
                "total_price": order.total_price,
                "payment_status": order.payment_status
            }
        
        except Exception as e:
            logger.error(f"Fel vid hämtning av orderstatus {order_id}: {str(e)}")
            return {
                "error": str(e),
                "order_id": order_id,
                "status": "unknown"
            }
        
    def _get_queue_position(self, order_id: str) -> int:
        """
        Hämtar köposition för en order

        Args:
            Köposition (0-indexerad), -1 om inte i kö
        """
        for i, (oid, _) in enumerate(self.order_queue):
            if oid == order_id:
                return i + 1 # 1-indexerad för användarvänlighet
        return -1

    def cancel_order(self, order_id: str, reason: str = "") -> bool:
        """
        Avbryter en order

        Args:
            order_id: Order att avbryta
            reaso: Orsak till avbrott

        Returns:
            True om avbrott lyckades
        """ 
        try:
            with self.processing_lock:
                if order_id not in self.active_orders:
                    raise OrderError(f"Order {order_id} finns inte i aktiv kö")
                
                order = self.active_orders[order_id]

                # Kan bara avbryta om inte redan pågår
                if order.status in [OrderStatus.PREPARING, OrderStatus.READY]:
                    raise OrderError("Kan inte avbryta en order som redan påbörjats")
                
                # Uppdatera status
                order.status = OrderStatus.CANCELLED
                order.upedate_at = datetime.now()

                # Ta bort från kö
                self.order_queue  = [(oid, t) for oid, t in self.order_queue if oid != order_id]

                # Frigör reserverade ingredienser
                self._release_inventory_for_order(order)

                # Spara till databas
                self.db.update_order_status(order_id, OrderStatus.CANCELLED.value, order.upedate_at, reason)

                # Skicka händaelse
                self.event_bus.publish(EventType.ORDER_CANCELLED, {
                    "order_id": order_id,
                    "reason": reason,
                    "cancelled_at": order.upedate_at.isoformat()
                })

                logger.info(f"Order {order_id} avbröts: {reason}")
                return True

        except Exception as e:
            logger.error(f"Fel vid orderavbrott {order_id}: {str(e)}")
            return False
        
    def _release_inventory_for_order(self, order: Order):
        """
        Frigör reserverade ingredienser

        Args:
            order: Order att frigöra ingredienser för
        """
        for item in order.items:
            recipe = self.recipe_manager.get_recipe(item.recipe_name)
            if not recipe:
                continue

            for ingredient, amount in recipe["ingredients"].items():
                total_amount = amount * item.quantity
                self.inventory.release_reservation(ingredient, total_amount)

    def get_queue_status(self) -> Dict[str, Any]:
        """
        Hämtar köstatistik

        Returns:
            Dict med köinformation
        """
        with self.processing_lock:
            total_orders = len(self.active_orders)
            queued_orders = len(self.order_queue)
            processing_orders = sum(
                1 for order in self.active_orders.values()
                if order.status == OrderStatus.PREPARING
            )

            avg_wait_time = self._calculate_avarage_wait_time()

            return {
                "total_orders": total_orders,
                "queued_orders": queued_orders,
                "processing_orders": processing_orders,
                "average_wait_time": avg_wait_time,
                "max_queue_size": self.max_queue_size,
                "queue": [
                    {
                        "order_id": order_id,
                        "priority": self.active_orders[order_id].priority.value,
                        "wait_time": (datetime.now() - queue_time).total_secunds()
                    }
                    for order_id, queue_time in self.order_queue[:5] # Visa bara första 5
                ]
            }

    def _canculate_avarage_wait_time(self) -> float:
        """
        Beräkanr genomsnittligt väntetid

        Returns:
            Genomsnittlig väntetid i sekunder
        """
        if not self.order_queue:
            return 0
        
        total_wait = sum(
            (datetime.now() - queue_time).total_seconds()
            for _, queue_time in self.order_queue
        )

        return total_wait / len(self.order_queue)
                
    def _calculate_wait_time(self, order: Order) -> int:
        """
        Beräkna estimerad väntetid för en order

        Args:
            order: Order att beräkna väntetid för

        Returns:
            Estimerad väntetid i sekunder
        """
        base_wait = len(self.order_queue) * 120 # 2 min per burgare

        if order.priority == OrderPriority.PRIORITY:
            base_wait *= 0.7 # 30% snabbare för prioritet

        return int(base_wait)
    
    def _process_orders_loop(self):
        """
        Huvudloop för orderbeatbetning
        Körs i egen tråd
        """
        while True:
            try:
                if self.is_processing:
                    time.sleep(self.processing_delay)
                    continue

                self.is_processing = True

                # Processa order i kö
                with self.processing_lock:
                    if self.order_queue:
                        order_id, _ = self.order_queue[0]
                        order = self.active_orders.get(order_id)

                        if order and order.status == OrderStatus.PENDING:
                            # Kontrollera om vi kan starta tillagning
                            if self._can_start_preparation():
                                self.update_order_status(order_id, OrderStatus.PRWPARING)

                                # Ta bort från kö
                                self.order_queue.pop(0)

                        self.is_processing = False
                        time.sleep(self.processing_delay)

            except Exception as e:
                logger.error(f"Fel i orderbearbetningsloop: {str(e)}")
                self.is_processing = False
                time.sleep(5)

    def _can_start_preparation(self) -> bool:
        """
        Kontrollerar om systemet kan starta ny tillagning

        Returns:
            True om tillagning kan startas
        """
        # Räkna pågående tillagningar
        ongoing_preparations = sum(
            1 for order in self.active_orders.values()
            if order.status == OrderStatus.PREPARING
        )

        # Kontroööera om vi har kapacitet
        return ongoing_preparations < self.batch_size

    def _save_order_to_db(self, order: Order):
        """
        Spara en order till databasen

        Args:
            order: Order att spara
        """

        order_dict = asdict(order)

        # Konventera datetime till strängar
        order_dict["created_at"] = order.created_at.isoformat()
        order_dict["updated_at"] = order.upedate_at.isoformat()

        if order.estmated_completion:
            order_dict["estimated_completion"] = order.estmated_completion.isoformat()

            # Konventera enmus till strängar
            order_dict["priority"] = order.priority.value
            order_dict["status"] = order.status.value

            # Konventeta OrderItem objekt
            order_dict["items"] = [
                {
                    **asdict(item),
                    "status": item.status.value
                }
                for item in order.items
            ]

            self.db.save_order(order_dict)

    def _load_order_from_db(self, order_data: Dict) -> Order:
        """
        Laddar ett Order-objekt från databasdata

        Args:
            order_data: Databasdata

        Returns:
            Order objekt
        """
        # Konventera strängar till datetime
        order_data["created_at"] = datetime.fromisoformat(order_data["created_at"])
        order_data["updated_at"] = datetime.fromisoformat(order_data["updated_at"])

        if order_data.get("estimated_completion"):
            order_data["estimate_completion"] = datetime.fromisoformat(
                order_data["estimate_completion"]
            )

        # Konventera strängar till enmus
        order_data["priotity"] = OrderPriority(order_data["priotity"])
        order_data["status"] = OrderStatus(order_data["status"])

        # Skapa OrderItem objekt
        items = []
        for item_data in order_data.get("item", []):
            item_data["status"] = OrderStatus(item_data["status"])

            # Konventera start/complete tid om de finns
            if item_data.get("start_time"):
                item_data["start_tiem"] = datetime.fromisoformat(item_data["start_time"])

            items.append(OrderItem(**item_data))

        order_data["items"] = items

        return Order(**order_data)
    
    def get_active_order(self) -> List[Dict[str, Any]]:
        """
        Hämtar alla aktiva ordrar

        Returns:
            Lista med orderinformation
        """
        with self.processing_lock:
            return [
                {
                    "order_id": order.order_id,
                    "status": order.status.value,
                    "created_at": order.created_at.isoformat(),
                    "items_count": len(order.items),
                    "total_price": order.total_price,
                    "priority": order.priority.value,
                    "customer_id": order.customer_id
                }
                for order in self.active_orders.values()
                if order.status not in [OrderStatus.CANCELLED, OrderStatus.READY]
            ]
        
    def cleanup_completed_orders(self, hours_old: int = 24):
        """
        Rensar bort färdigställda och avbrutna ordrar från minnet

        Args:
            hours_old: Anatal timmar gamla ordrar ska rensas
        """
        cutoff_time = datetime.now().timestamp() - (hours_old * 3600)

        with self.processing_lock:
            to_remove = []

            for order_id, order in self.active_orders.items():
                if order.status in [OrderStatus.READY, OrderStatus.CANCELLED]:
                    order_time = order.upedate_at.timestamp()

                    if order_time < cutoff_time:
                        to_remove.append(order_id)

            # Ta bort från aktiv lista
            for order_id in to_remove:
                del self.active_orders[order_id]

            # Rensa kö
            self.order_queue = [
                (oid, t) for oid, t in self.order_queue
                if oid not in to_remove
            ]

            if to_remove:
                logger.info(f"Rensade {len(to_remove)} gamla ordrar från minnet")

    def emergency_stop_orders(self):
        """
        Nödstoppar alla pågående ordrar
        Används vid systemfel säkerhetsproblem
        """
        with self.processing_lock:
            for order_id, order in self.active_orders.items():
                if order.status == OrderStatus.PREPARING:
                    self.update_order_status(order_id, OrderStatus.CANCELLED,
                                             {"reason": "emergency_stop"})
                    
            # Töm kö
            self.order_queue.clear()

            # Frigör alla reserverade ingredienser
            for order in self.active_orders.values():
                if order.status != OrderStatus.READY:
                    self._release_inventory_for_order(order)
                
            logger.warning("Alla ordrar nödstoppade")
            self.event_bus.publish(EventType.EMERGENCY_STOP, {
                "timestamp": datetime.now().isoformat(),
                "affected_orders": list(self.active_orders.keys())
            })

    def export_order_history(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        Exporterar orderhistorik

        Args:
            start_date: Startdatum
            end_date: Slutdatum

        Returns:
            Lista med historiska ordrar
        """
        try:
            order_data = self.db.get_orders_between_dates(start_date, end_date)
            return [
                self._load_order_from_db(order_data)
                for order_data in order_data
            ]
        except Exception as e:
            logger.error(f"Fel vid export av orderhistorik: {str(e)}")
            return []
        
_order_processor_insatnce = None

def get_order_processor(db_manager: DatabasManager = None, event_bus: EventBus = None) -> OrderProcessor:
    """
    Hämtar eller skapar singeleton-instans av OrderProcessor:

    Args:
        db_manager: Databasanslutning (krävs vid förata anrop)
        event_bus: Händelsebuss (krävs vid förata anrop)

    Returns:
        OrderProcessor-instans
    """
    global _order_processor_insatnce

    if _order_processor_insatnce is None:
        if db_manager is None or event_bus is None:
            raise ValueError("db_manager och event_bus krävs för att skapa OrderProcessor")
        
        _order_processor_insatnce = OrderProcessor(db_manager, event_bus)

    return _order_processor_insatnce




