"""
Kassasystem integration API för hamburgermaskinen.
Hanterar kommunikation med externa kassasystem för ordermottagning och statusuppdateringar.
"""

import json
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import time

from utils.logger import setup_logger
from utils.config_loader import ConfigLoader
from core.event_bus import EventBus, EventType

class OrderSource(Enum):
    """Källor för beställningar"""
    KIOSK = "kiosk"
    MOBILE_APP = "mobile_app"
    WEB = "web"
    ADMIN = "admin"

class OrderStatus(Enum):
    """Status för beställnigar"""
    PENDING = "pending"
    COMFIRMED = "comfirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

@dataclass
class OrderItem:
    """Enskilt varor i en beställning"""
    product_id: str
    product_name: str
    quantity: int
    price: float
    customizations:  Dict[str, Any] = None

    def __post_init__(self):
        if self.customizations is None:
            self.customizations = {}

@dataclass
class Order:
    """Beställningsobjekt"""
    order_id: str
    source: OrderSource
    timestamp: datetime
    items: List[OrderItem]
    customer_id: Optional[str] = None
    total_amount: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    estimated_completion: Optional[datetime] = None

    def calculate_total(self):
        """Beräkna totalbelopp"""
        self.total_amount = sum(item.price * item.quantity for item in self.items)
        return self.total_amount
    
    def to_dict(self):
        """Konventera till dictonary"""
        data = asdict(self)
        data["source"] = self.source.value
        data["status"] = self.status.value
        data["timestamp"] = self.timestamp.isoformat()
        if self.estimated_completion:
            data["estimated_completion"] = self.estimated_completion.isoformat()
        return data
    
class KioskAPI:
    """
    API för ingration med kassasystem.
    Stödaer både push- och pull-baserad kommunikation.
    """

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initiera KioskAPI

        Args:
            config_path: Sökväg till konfigurationsfil
        """
        self.logger = setup_logger("kiosk_api")
        self.config = ConfigLoader.load(config_path).get("kiosk_api", {})
        self.event_bus = EventBus.get_imstance()

        # API-konfiguration
        self.base_url = self.config.get("base_url", "http://localhost:8000")
        self.api_key = self.config("api_key", "")
        self.timeout = self.config.get("timeout_secondes", 10)
        self.polling_interval = self.config.get("polling_interval_seconds", 5)

        # State
        self.is_connected = False
        self.last_sync = None
        self.pending_orders: Dict[str, Order] = {}

        #  Webhook endpoints
        self.wbbhook_url = f"{self.base_url}/webhook/order"
        self.status_update_url = f"{self.base_url}/api/order/status"

        # Starta bakgrundstrådar
        self.stop_polling = threading.Event()
        self.polling_thread = None
        
        # Registrera event handlers
        self._register_event_handlers()

        self.logger.info("KioskAPI initialiserad")

    def _register_event_handlers(self):
        """Registrera event handlers"""
        self.event_bus.subscribe(EventType.ORDER_COMPLETED, self._on_order_completed)
        self.event_bus.subscribe(EventType.ORDER_FAILED, self._on_order_failed)
        self.event_bus.subscribe(EventType.SYSTEM_STATUS_CHANGED, self._on_system_status_changed)

    def connect(self) -> bool:
        """
        Anslut till kassasystemet

        Returns:
            True om anslutningen lyckades, anars False
        """
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{self.base_url}/api/health",
                headers=headers,
                timeout=self.timeout
            )

            if response.status_code == 200:
                self.is_connected = True
                self.last_sync = datetime.now()
                self.logger.info(f"Ansluten till kassasystem: {self.base_url}")

                # Starta polling för nya beställningar
                self.start_polling()

                # Skicka systemstatus
                self.send_system_status("online")

                return True
            else:
                self.logger.error(f"Kassasystem svarade med status: {response.status_code}")
                return False
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Kunde inte ansluta till kassasystem: {e}")
            return False
        
    def disconnect(self):
        """Koppla från kassasystemet"""
        self.stop_polling
        self.send_system_status("offline")
        self.is_connected = False
        self.logger.info("Frånkopplad från kassasysteme")


    def start_polling(self):
        """Starta bakgrundspolling för ny beställningar"""
        if self.polling_thread is None or not self.polling_thread.is_alive():
            self._stop_polling_clear()
            self.polling_thread = threading.Thread(
                target=self._poll_orders,
                daemon=True,
                name="KioskAPIPolling"
                )
            self.polling_thread.start()
            self.logger.info("Polling för beställningar startad")

    def stop_polling(self):
        """Stoppa bakgrundspolling"""
        self.stop_polling.set()
        if self.polling_thread:
            self.polling_thread.join(timeout=2.0)
        self.logger.info("Polling för beställningar stoppad")

    def _poll_orders(self):
        """Bakgrundstråd för att polla efter nya beställningar"""
        while not self._stop_polling.is_set():
            try:
                if self.is_connected:
                    self._fetch_new_orders()
                
                time.sleep(self.polling_interval)

            except Exception as e:
                self.logger.error(f"Fel i polling-tråd: {e}")
                time.sleep(self.polling_interval * 2) # Vänta längre vid fel

    def _fetch_new_orders(self):
        """Hämta ny beställningar från kassasystemet"""
        try:
            headers = self._headers()
            response = requests.get(
                f"{self.base_url}/api/orders/pending",
                headers=headers,
                timeout=self.timeout
            )

            if response.status_code == 200:
                orders_data = response.json()
                self._process_incoming_orders(orders_data)
                self.last_sync = datetime.now()

        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Kunde inte hämta beställningar: {e}")

    def receive_order_webhook(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ta emot beställning via webhok

        Args:
            order_data: Beställningsdata i JSON-format

        Returns:
            Bekräftelsesvar
        """
        try:
            self.logger.info(f"Mottog webhook-beställning: {order_data.get('order_id')}")

            # Validera beställningsdata
            if not self._validate_order_data(order_data):
                return {
                    "success": False,
                    "error": "Ogiltig beställningsdata",
                    "order_id": order_data.get("order_id", "unknown")
                }

            # Skapa Order-objekt
            order = self._parse_order(order_data)

            # Publicera event för ny beställning
            self.event_bus.publish(EventType.NEW_ORDER, {
                "order": order.to_dict(),
                "source": order.source.value
            })

            # Skicka bekräfteöse till kassasystem
            confirmation = {
                "success": True,
                "order_id": order.order_id,
                "status": "accepted",
                "estimated_wait_time": self._calculate_estimated_wait_time(),
                "timestamp": datetime.now().isoformat()
            }
            
            self.logger.info(f"Beställning {order.order_id} accepterad")
            return confirmation
        
        except Exception as e:
            self.logger.error(f"Fel vid mottagning av webhook {e}")
            return {
                "success": False,
                "error": str(e),
                "order_id": order_data.get("order_id", "unknown")
            }

    def send_order_status_update(self, order_id: str, status: OrderStatus, additional_info: Dict[str, Any] = None) -> bool:
        """
        Sicka statusuppdatering för beställning till kassasystem

        Args:
           order_id: Beställnings-ID
           status: Ny status
           additional_info: Ytterligare information (felmeddelanden, etc.)

        Returms:
           True om lyckad uppdatering
        """
        if not self.is_connected:
            self.logger.warning("Ej ansluten till kassasystem, kan inte skicka status")
            return False
        
        try:
            payload = {
                "order_id": order_id,
                "status": status.value,
                "timestamp": datetime.now().isoformat(),
                "machine_id": self.config.get("machine_id", "hamburger_machine_001") 
            }

            if additional_info:
                payload.update(additional_info)

            headers = self._get_headers()
            response = requests.post(
                self.status_update_url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )

            if response.status_code == 200:
                self.logger.info(f"Status uppdaterad för beställning {order_id}: {status.value}")
                return True
            else:
                self.logger.error(f"Misslyckades att uppdatera status: {response.status_code}")
                return False
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Fel vid statusuppdatering: {e}")
            return False
        
    def send_system_status(self, status: str, details: Dict[str, Any] = None) -> bool:
        """
        Skicka systemstatus till kassasytem

        Args:
            stastus: Systemstatus (online, offline, maintenance, error)
            details: Ytterligare statusinformation

        Returns
            True om det lyckad uppdatering
        """
        try:
            playload = {
                "machine_id": self.config.get("machine_id", "hamburger_machine_001"),
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "component": "hamburger_machine"
            }

            if details:
                playload["details"] = details

            headers = self._get_headers()
            response = requests.post(
                f"{self.base_url}/api/system/status",
                json=playload,
                headers=headers,
                timeout=self.timeout
            )

            if response.status_code == 200:
                self.logger.info(f"Systemstatus uppdaterad: {status}")
                return True
            else:
                self.logger.warning(f"Kunde inte skicka systemstatus: {response.status_code}")
                return False
        
        except requests.exceptions.RequestException:
            # Det är OK om detta misslyckas ibland
            return False
        
    def get_menu_items(self) -> List[Dict[str, Any]]:
        """
        Hämta meny från kassasystem

        Returns:
            Lista med menyobjekt
        """
        try: 
            headers = self._get_headers()
            response = requests.get(
                f"{self.base_url}/api/menu",
                headers=headers,
                timeout=self.timeout
            )

            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"Kunda inte hämta meny: {response.status_code}")
                return []
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Fel vid menyhämtning: {e}")
            return []
        
    def _process_incoming_orders(self, orders_data: List[Dict[str, Any]]):
        """Bearbeta inkommande beställningar"""
        for order_data in orders_data:
            try:

                order_id = order_data.get("id")

                # Kontrollera om vi redan  har denna beställning
                if order_id in self.pending_orders:
                    continue
                
                # Validera och skapa order
                if self._validate_order_data(order_data):
                    order = self._parse_order(order_data)
                    self.pending_orders[order.order_id] = order
                    # Publicera event
                    self.event_bus.publish(EventType.NEW_ORDER, {
                        "order": order.to_dict(),
                        "source": order.source.value
                        })
                    
                    self.logger.info(f"Beställning mottagen via polling: {order.order_id}")

            except Exception as e:
                self.logger.error(f"Fel vid bearbetning av beställning: {e}")

    def _parse_order(self, order_data: Dict[str, Any]) ->Order:
        """Parsa orderdata till Order-objekt"""
        # Extrahera grundläggande information
        order_id = order_data.get("id", order_data.get("order_id", str(datetime.now().timestamp())))
        source_str = order_data.get("source", "kiosk")

        try:
            source = OrderSource(source_str)
        except ValueError:
            source = OrderSource.KIOSK

        # Parse timestamp
        timestamp_str = order_data.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else: 
            timestamp = datetime.now()

        # Pardse items
        items = []
        for item_data in order_data.get("items", []):
            item = OrderItem(
                product_id=item_data.get("product_id", ""),
                product_name=item_data.get("product_name", "Unknown"),
                quantity=item_data.get("price", 0.0),
                customizations=item_data.get("customizations", {})
            )
            items.append(item)

        # Skapa Order_objekt
        order = Order(
            order_id=order_id,
            source=source,
            timestamp=timestamp,
            items=items,
            customer_id=order_data.get("customer_id"),
            status=OrderStatus.PENDING
        )

        # Beräkna total
        order.calculate_total()
        
        return order
    
    def _validate_order_data(self, order_data: Dict[str, Any]) -> bool:
        """Validera beställningsdata"""
        required_fields = ["items"]

        # Kontrollera required fields
        for field in required_fields:
            if field not in order_data:
                self.logger.error(f"Saknat fält i beställning: {field}")
            return False
        
        # Kontrollera items
        items = order_data.get("items", [])
        if not items or len(items) == 0:
            self.logger.error("Beställning har inga items")
            return False
        
        # Kontrollera varje item
        for item in items:
            if not item.get("product_id"):
                self.logger.error("Item saknar product_id")
                return False
            if not isinstance(item.get("quantity", 0), int) or item["quantity"] <= 0:
                self.logger.error("Ogiltig quantity")
                return False
            
        return True
    
    def _calculate_estimated_wait_time(self) -> int:
        """Beräkna uppskattade väntetid i sekunder"""
        # Enkel implementatio - kan göras mer avancerad
        base_time = 180 # 3 minuter bas
        queue_multiplier = len(self.pending_orders) * 30 # 30 sek extra per väntadeorder
        return base_time + queue_multiplier
    
    def _get_headers(self) -> Dict[str, str]:
        """Hämta headers för API-anrop"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "HamburgerMachine/1.0"
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers
    
    def _on_order_completed(self, event_data: Dict[str, Any]):
        """Event handler för slutförd beställning"""
        order_id = event_data.get("order_id")
        if order_id:
            self.send_order_status_update(order_id, OrderStatus.COMPLETED, event_data)

            # Ta bort från pending orders
            if order_id in self.pending_orders:
                del self.pending_orders[order_id]

    def _on_order_failed(self, event_data: Dict[str, Any]):
        """Event handler för misslyckad beställning"""
        order_id = event_data.get("order_id")
        if order_id:
            error_msg = event_data.get("error", "Unknown error")
            self.send_order_status_update(
                order_id,
                OrderStatus.FAILED,
                {"error": error_msg}
            )

    def _on_system_status_changed(self, event_data: Dict[str, Any]):
        """Event handler för systemstatusändring"""
        status = event_data.get("status")
        if status:
            self.send_system_status(status, event_data)

    def get_connection_status(self) -> Dict[str, Any]:
        """Hämta snslutningsstatus"""
        return {
            "is_connected": self.is_connected,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "base_url": self.base_url,
            "pending_orders_count": len(self.pending_orders),
            "polling_active": self.polling_thread.is_alive() if self.polling_thread else False
        }
    
    def cleanup(self):
        """Städa upp resurser"""
        self.stop_polling()
        self.disconnect()
        self.logger.info("KioskAPI rensat upp")

# Exempel på användning och testkod
if __name__ == "__main__":
    # Testa API:et
    api = KioskAPI()

    # Testa anslutning
    if api.connect():
        print("Ansluten till kassasystem")
        
        # Hämta meny
        menu = api.get_menu_items()
        print(f"Hämtade {len(menu)} menyobjekt")
        
        # Simulera en webhook-beställning
        test_order = {
            "order_id": "tesrt123",
            "source": "kiosk",
            "timestamp": datetime.now().isoformat(),
            "customer_id": "cust_456",
            "items": [
                {
                    "product_id": "burger_classic",
                    "product_name": "Classic Burger",
                    "quantity": 2,
                    "price": 85.0,
                    "customizations": {
                        "cheese": "extra",
                        "sauce": "ketchup"
                        }
                    }
                ]
            }
        
        response = api.receive_order_webhook(test_order)
        print(f"Webbhook svar: {response}")
        
        # vänta lite för polling
        time.sleep(3)
        
        # Hämta status
        status = api.get_connection_status()
        print(f"Status: {status}")
        
        # Säng ner
        api.cleanup()
        
    else:
        print("Kunde inte ansluta till kassasystem")


    
