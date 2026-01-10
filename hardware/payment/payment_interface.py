"""
Payment Interface Module
Hanterar all betalnungsoperationer för hamburgarmaskinen.
Integrerar med olika betalbibgsmetoder och hanterar transaktioner.
"""

import logging
import time
import threading
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, Callable, List
from decimal import Decimal

# Import hardwaree-specific modules
try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False
    logging.warning("RPi.GPIO not availble. Running in simulation mode.")

try:
    from .card_reader import CardReader, CardReaderError
    HAS_CARD_READER = True
except ImportError:
    HAS_CARD_READER = False
    CardReader = None
    logging.warning("Card reader module not available.")

class PymentMethod(Enum):
    """Tillgängliga betalningsmetoder"""
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    CONTACTLESS = "contacless"
    MOBILE_PAY = "mobile_pay"
    CASH = "cash"
    LOYALTY_POINTS = "loyalty_points"
    GIFT_CARD = "gift_card"

class PaymentStatus(Enum):
    """Status för betalning"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refounded"
    CANCELLED = "cancelled"

@dataclass
class PaymentTransaction:
    """Dataklass för att representera en betalningstransaktion"""
    transaction_id: str
    order_id: str
    amount: Decimal
    currency: str = "SEK"
    method: PymentMethod = PymentMethod.CREDIT_CARD
    status: PaymentStatus = PaymentStatus.PENDING
    timestamp: datetime = None
    customer_id: Optional[str] = None
    card_last_four: Optional[str] = None
    auth_code: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Konventera transektion till dictionary"""
        return {
            "transaction_id": self.transaction_id,
            "order_id": self.order_id,
            "amount": float(self.amount),
            "currency": self.currency,
            "method": self.method.value,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "customer_id": self.customer_id,
            "card_last_four": self.card_last_four,
            "auth_code": self.auth_code,
            "error_message": self.error_message
        }
    
class PaymentInterface:
    """
    Huvudklass för betalningshantering.
    Hanterar olika betalningsmetoder och kommunikation med externa system.
    """

    def __init__(self, config: Dict[str, Any], event_bus=None):
        """
        Initiera betalningsgränssnittet.

        Args:
            config: Konfigurationsdictionary
            event_bus: Event bus för systemhändelser (valfritt)
        """
        self.config = config
        self.event_bus = event_bus
        self.logger = logging.getLogger(__name__)

        # Hardware setup
        self.card_reader = None
        self.cash_acceptor = None
        self._setup_hardware()

        # Payment state
        self.current_transaction: Optional[PaymentTransaction] = None
        self.transaction_history: List[PaymentTransaction] = []
        self.is_processing = False
        self.payment_timeout = config.get("payment_timeout", 120) # secunds

        # Callbacks
        self.on_payment_success: Optional[Callable] = None
        self.on_payment_failed: Optional[Callable] = None
        self.on_status_status_change: Optional[Callable] = None

        # Thread safety
        self._lock = threading.Lock()

        # External APIs
        self.payment_gateway_enabled = config.get("payment_gateway_enbled", False)
        self.test_mode = config.get("payment_test_mode", True)

        self.logger.info("Payment interface initialized")

    def _setup_hardware(self) -> None:
        """Initera alla betalningsenheter"""
        try:
            # Initialize card reader if available
            if HAS_CARD_READER and CardReader:
                reader_config = self.config.get("card_reader", {})
                self.card_reader = CardReader(
                    port=reader_config.get("port", "/dev/ttyUSB0"),
                    baudrate=reader_config.get("baudrate", 9600)
                )
                self.logger.info("Card reader initialized")

            # Setup GPIO for cash acceptor if using Raspberry Pi
            if HAS_GPIO and self.config.get("cash_acceptor_enabled", False):
                self._set_cash_acceptor()

        except Exception as e:
            self.logger.error(f"Failed to setup payment hardware: {e}")

    def _setup_cash_acceptor(self) -> None:
        """Konfigurera kontantacceptorn"""
        try:
            GPIO.setmode(GPIO.BCM)

            # Setup pins (adjust based on your hardware)
            self.cash_pins = {
                "coin_10": 17,
                "coin_5": 18,
                "coin_1": 27,
                "bill_20": 22,
                "bill_50": 23,
                "bill_100": 24
            } 

            for pin_name, pin in self.cash_pins.items():
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                GPIO.add_event_detect(pin, GPIO.FALLING, callback=lambda x, pin=pin_name: self._cash_detected(pin), bouncetime=200)
                self.cash_acceptor_enabled = True
                self.logger.info("Cash acceptor initialized")

        except Exception as e:
            self.logger.error(f"Failed to setup cash acceptor: {e}")
            self.cash_acceptor_enabled = False

    def _cash_datected(self, pin_name: str) -> None:
        """Callback när kontant upptäcks"""
        cash_values = {
            "coin_1": 1, "coin_5": 5, "coin_10": 10,
            "bill_20": 20, "bill_50": 50, "bill_100": 100
        }

        if pin_name in cash_values:
            amount = cash_values[pin_name]
            self.logger.info(f"Cash datected: {amount} SEK")

            if self.current_transaction:
                # Update paid amount
                self._update_cush_payment(amount)

    def _update_cash_payment(self, amount: Decimal) -> None:
        # This would track cash payment and check if full amount is paid
        pass

    def start_payment(
            self,
            order_id: str,
            amount: Decimal,
            payment_method: PymentMethod,
            customer_id: Optional[str] = None
    ) -> PaymentTransaction:
        """
        Starta en ny betalningsprocess.

        Args:
            order_id: Orderns ID
            amount: Belopp att betala
            payment_method: Vald betalningsmetod
            customer_id: Kund-ID (valfritt)

        Returns:
            PaymentTransaction: Transaktionsobjekt
        """
        with self._lock:
            if self.is_processing:
                raise Exception("Payment system is already procesing a transaction")
            
            self.is_processing = True

            # Create transaction
            transaction = PaymentTransaction(
                transaction_id=self._generate_transaction_id(),
                order_id=order_id,
                amount=amount,
                method=payment_method,
                status=PaymentStatus.PROCESSING,
                customer_id=customer_id
            )

            self.current_transaction = transaction
            self.transaction_history.append(transaction)

            self.logger.info(f"Starting payment: {transaction.transaction_id}" f"For order {order_id}, amount: {amount} SEK")

            # Emit event if event bus is available
            if self.event_bus:
                self.event_bus.emit("payment_started", transaction.to_dict())

            # Start payment processing on method
            if payment_method in [PymentMethod.CREDIT_CARD,
                                  PymentMethod.DEBIT_CARD,
                                  PymentMethod.CONTACTLESS]:
                self._process_card_payment(transaction)
            elif payment_method == PymentMethod.MOBILE_PAY:
                self._process_mobile_payment(transaction)
            elif payment_method == PymentMethod.CASH:
                self._process_cash_payment(transaction)
            elif payment_method == PymentMethod.LOYALTY_POINTS:
                self._prcess_loyalty_payment(transaction)
            elif payment_method == PymentMethod.GIFT_CARD:
                self._process_gift_card_payment(transaction)

            return transaction
        
        def _process_card_payment(self, transaction: PaymentTransaction) ->None:
            """Bearbeta kortbitalning"""
            self.logger.info(f"Processing card payment: {transaction.transaction_id}")

            # Starta in a separat thread to avoid blocking
            processing_thread = threading.Thread(
                target=self._card_payment_worker,
                args=(transaction,)
            )
            processing_thread.daemon = True
            processing_thread.start()

        def _card_payment_worker(self, transaction: PaymentTransaction) -> None:
            """Arbetstråd för kortbetaling"""
            try:
                # If in test mode, simulate payment
                if self.test_mode:
                    self.logger.info("Test mode: Simulating card payment")
                    time.sleep(2) # Simulate processing time

                    # Simulate success 90% of the time in test mode
                    import random
                    if random.random() < 0.9:
                        self._complete_payment(transaction, "TESR12345", "1234")
                    else:
                        self._fail_payment(transaction, "Test: Card declined")
                    return
                
                # Real hardware implementation
                if self.card_reader:
                    # Wait for card
                    self.logger.info("Please insert/tap card...")
                    self._update_status("waiting_for_card")
                    
                    # Read card data (this would be encrypted in real implementation)
                    try:
                        card_data = self.card_reader.read_card()

                        # Process payment throug gateway
                        if self.payment_getway_enabled:
                            result = self._call_payment_gateway(
                                transaction,
                                card_data
                            )

                            if result["success"]:
                                self._complete_payment(
                                    transaction,
                                    result["auth_code"],
                                    card_data.get("last_four", "****")
                                )
                            else:
                                self._fail_payment(transaction, result["error"])
                        else:
                            # Simulate gateway i development
                            self.logger.warning("Payment gateway disbled, simulating success")
                            self._complete_payment(transaction, "SIMULATED", "1234")

                    except CardReaderError as e:
                        self._fail_payment(transaction, f"Card reader error: {e}")
                    except Exception as e:
                        self._fail_payment(transaction, f"Payment processing error: {e}")
                else:
                    self._fail_payment(transaction, "Card reader not available")

            except Exception as e:
                self.logger.error(f"Card payment worker error: {e}")
                self._fail_payment(transaction, f"Internal error: {e}")

        def __process_mobile_payment(self, transaction: PaymentTransaction) -> None:
            """Bearbeta nobilbetalning"""
            self.logger.info(f"Processing mobile payment: {transaction.transaction_id}")

            # This would integrate with MobilePay API or simailar
            # For now, simulate
            time.sleep(1)

            if self.test_mode:
                self._complete_payment(transaction, "MOBILE123", None)
            else:
                # Real API integration would go here
                pass

        def _process_cash_payment(self, transaction: PaymentTransaction) -> None:
            """Bearbeta kontantbetalning"""
            self.logger.info(f"Processing cash payment: {transaction.transaction_id}")
            self._update_status("insert_cash")

            # Starta timeout for cash payment
            self._start_payment_timeout(transaction)

        def _process_loyalty_payment(self, transaction: PaymentTransaction) -> None:
            """Bearbeta betalning med poäng"""
            # Integrate with loyalty system
            pass

        def _process_gift_card_payment(self, transaction: PaymentTransaction) -> None:
            # Integrate with gift card system
            pass

        def _call_payment_gateway(self, transaction: PaymentTransaction, card_data: Dict[str, Any]) -> Dict[str, Any]:
            """
            Anropa extern betalningsgateway.
            
            Note: I en riktig implementation skulle detta vara säker kommunikation
            med kryptering och PCI DSS compliance.
            """
            # This is a simulation - implement real gateway API call here
            import requests
            import json

            gateway_url = self.config.get("payment_gateway_url", "")
            api_key = self.config.get("payment_gateway_api_key", "")

            payload = {
                "transaction_id": transaction.transaction_id,
                "amount": float(transaction.amount),
                "currency": transaction.currency,
                "card_data": card_data,
                "merchant_id": self.config.get("merchent_id", "")
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            try:
                if not self.test_mode:
                    response = requests.post(
                        gateway_url,
                        json=payload,
                        headers=headers,
                        timeout=30
                    )

                    if response.status_code == 200:
                        return response.json()
                    else:
                        return {"sucess": False, "error": f"Gateway error: {response.status_code}"}
                else:
                    # Test response
                    return {
                        "success": True,
                        "auth_code": "TEST_AUTH_123",
                        "reansaction_ref": f"REF_{transaction.transaction_id}"
                    }
            
            except Exception as e:
                return {"success": False, "error": f"Gateway connection error: {e}"}
            
        def _complete_payment(self, transaction: PaymentTransaction, auth_code: str, card_last_four: Optional[str]) -> None:
            """Markera betalning som klar"""
            with self._lock:
                transaction.status = PaymentStatus.COMPLETED
                transaction.auth_code = auth_code
                transaction.card_last_four = card_last_four

                self.if_processing = False
                self.current_transaction = None

                self.logger.info(f"Payment completed: {transaction.transaction_id}," f"auth{auth_code}")

                # Emit event
                if self.event_bus:
                    self.event_bus.emit("Payment_completed", transaction.to_dict())

                # Call callback
                if self.on_payment_success:
                    try:
                        self.on_payment_success(transaction)
                    except Exception as e:
                        self.logger.error(f"Error in payment success callback: {e}")

        def _fail_payment(self, transaction: PaymentTransaction, error_message: str) -> None:
            """Markera betalning som misslyckad"""
            with self._lock:
                transaction.status = PaymentStatus.FAILED
                transaction.error_message = error_message

                self.is_processing = False
                self.current_transaction = None

                self.logger.error(f"Payment failed: {transaction.transaction_id}," f"error: {error_message}")

                # Emit event
                if self.event_bus:
                    self.event_bus.emit("payment_failed", transaction.to_dict())

                # Call callback
                if self.on_paymetn_failed:
                    try:
                        self.on_payment_failed(transaction, error_message)
                    except Exception as e:
                        self.logger.error(f"Error in payment failed callback: {e}")

        def cancel_payment(self) -> bool:
            """Avbryt pågånde betalning"""
            with self._lock:
                if self.current_transaction and self.is_processing:
                    self.current_transaction.status = PaymentStatus.CANCELLED
                    self.is_processing = False

                    self.logger.info(f"Payment cancelled: {self.current_transaction.transaction_id}")

                    if self.event_bus:
                        self.event_bus.emit("payment_cancelled", self.current_transaction.to_dict())
                        self.current_transaction = None
                        return True
                    return False
                
        def refund_payment(self, tramsaction_id: str, amount: Optional[Decimal] = None) -> None:
            """
            Återbetala en transaktion.

            Args:
                transaction_id: Transaktions-ID att återbetala
                amount: Belopp att återbetala (None för hela beloppet)

            Returns:
                bool: True om återbetalning lyckades
            """
            # Find transaction
            transaction = next(
                (t for t in self.transaction_history if t.transaction_id == tramsaction_id),
                None
            )

            if not transaction:
                self.logger.error(f"Transaction not found: {tramsaction_id}")
                return False
            
            if transaction.status != PaymentStatus.COMPLETED:
                self.logger.error(f"Connot refound non-completed transaction: {transaction.status}")
                return False
            
            # Process refund
            self.logger.info(f"Processing refund for transaction: {tramsaction_id}")

            # In test mode, simulate refund
            if self.test_mode:
                transaction.status = PaymentStatus.REFUNDED
                self.logger.info(f"Test: Refund simulated for {tramsaction_id}")
                return True
            
            # Real refund implementation would go here
            # This would call the payment gateway's refund API

            return False
        
        def get_transaction_status(self, transaction_id: str) -> Optional[Dict[str, Any]]:
            """Hämta status för en specifik transaktion"""
            transaction = next(
                (t for t in self.transaction_history if t.transaction_id == transaction_id),
                None
            )

            if transaction:
                return transaction.to_dict()
            return None
        
        def get_daily_total(self, date: Optional[datetime] = None) -> Dict[str, Any]:
            """
            Hämta dagens totalsumma per betalningsmetod.

            Args:
                data: Datum att beräkna för (None för idag)

            Returns:
                Dictionary med totalsummor
            """
            if date is None:
                date = datetime.now()

            date_str = date.date().isoformat()

            totals = {
                "date": date_str,
                "total_amount": Decimal("0"),
                "transaction_count": 0,
                "by_method": {method.value: Decimal("0") for method in PymentMethod},
                "completed": 0,
                "failed": 0
            }

            for transaction in self.trnsaction_history:
                if transaction.timestamp.data() == date.date():
                    totals["transaction_count"] += 1

                if transaction.status == PaymentStatus.COMPLETED:
                    totals["total_amount"] += transaction.amount
                    totals["by_method"][transaction.method.value] += transaction.amount
                    totals["completed"] += 1
                elif transaction.status == PaymentStatus.FAILED:
                    totals["failed"] += 1
            
            # Convert Decimal to float for JSON serialization
            totals["total_amount"] = float(totals["total_amount"])
            for method in totals["by_method"]:
                totals["by_method"][method] = float(totals["by_method"][method])
            
            return totals
        
        def _generate_transaction_id(self) -> str:
            """Generera unik transaktions-ID"""
            import uuid
            import hashlib
            import base64

            # Create unique ID with timestamp
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            unique_id = str(uuid.uuid4())[:8]

            # Combine and hash for shorter ID
            compined = f"{timestamp}_{unique_id}".encode()
            hash_id = hashlib.sha256(compined).digest()[:6]

            # Base64 encode for readable ID
            transaction_id = base64.urlsafe_b64decode(hash_id).decode().replace("=", "")

            return f"TRX_{transaction_id}"
        
        def _update_status(self, status: str) -> None:
            """Uppdatera betalningsstatus"""
            self.logger.debug(f"Payment status changed: {status}")

            if self.on_status_change:
                try:
                    self.on_status_change(status)
                except Exception as e:
                    self.logger.error(f"Error in status change callback: {e}")

        def _start_payment_timeout(self, transaction: PaymentTransaction) -> None:
            """Starta timeout"""
            def timeout_handler():
                time.sleep(self.payment_timeout)

                with self._lock:
                    if (self.current_transaction and self.current_transaction_id == transaction.transaction_id and self.current_transaction.status == PaymentStatus.PROCESSING):
                        self._fail_payment(transaction, "Payment timeout")
            
            timeout_thread = threading.Thread(target=timeout_handler)
            timeout_thread.daemon = True
            timeout_thread.start()

        def cleanup(self) -> None:
            """Städa upp resurser"""
            self.logger.info("Cleaning up payment interface")

            with self._lock:
                self.is_processing = False
                self.current_transaction = None

                # Clean up hardware
                if self.card_reader:
                    try:
                        self.card_reader.disconnect()
                    except:
                        pass
                
                if HAS_GPIO:
                    try:
                        GPIO.cleanup()
                    except:
                        pass

# Test and example usage
if __name__ == "__main__":
    # Setup loggning
    logging.basicConfig(level=logging.INFO)

    # Exemple config
    config = {
        "payment_timeout": 120,
        "payment_gateway_enabled": False,
        "payment_test_mode": True,
        "card_reader": {
            "port": "/dev/ttyUSB0",
            "baudrate": 9600
        },
        "cash_acceptor_enabled": False
    }

    # Create payment interface
    payment = PaymentInterface(config)

    # Set callbacks
    def on_success(transacton):
        print(f"Payment successful! Transaction: {transacton.transaction_id}")

    def on_failed(tranaction, error):
        print(f"Payment failed: {error}")

    payment.on_payment_success = on_success
    payment.on_payment_failed = on_failed

    try:
        # Testa payment
        from decimal import Decimal

        transaction = payment.start_payment(
            order_id="ORDER123",
            amount=Decimal("89.50"),
            payment_method=PymentMethod.CREDIT_CARD
        )

        print(f"Started payment; {transaction.transaction_id}")

        # Wait for payment to complete (in real use, this would be async)
        import time
        time.sleep(5)

        # Get status
        status = payment.get_transaction_status(transaction.transaction_id)
        print(f"Final status: {status}")

        # Get daily total
        daily = payment.get_daily_total()
        print(f"Daily total: {daily}")

    finally:
        payment.cleanup()   

