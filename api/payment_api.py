"""
Betalningsgetway API för hamburgerautomaten.
Integrerar med externa betalningstjänster (Swish, kort, etc.)
"""

import requests
import json
import hmac
import hashlib
from typing import Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import logging
from decimal import Decimal
import asyncio
import aiohttp

from utils.logger import get_logger
from utils.config_loader import load_config
from core.event_bus import EventBus, EventType
from core.safety_monitor import SafetyMonitor


logger = get_logger(__name__)

class PaymentMethod(Enum):
    """Tillgängliga betalningsmetoder."""
    CARD = "card"
    SWISH = "swish"
    MOBILE_PAY = "mobile_pay"
    CASH = "cash" # För framtida kassasystem
    CREDIT = "credit" # För återkommande kunder

class PaymentStatus(Enum):
    """Status för betalningar."""
    PENDING = "pennding"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "faild"
    REFAUNDED = "refaunded"
    CANCELLED = "candelled"

@dataclass
class PaymentRequest:
    """Data för en betalningsförfrågan."""
    order_id: str
    amount: Decimal
    currency: str = "SEK"
    method: PaymentMethod = PaymentMethod.CARD
    customer_reference: Optional[str] = None
    metadata: Optional[Dict] = None

@dataclass
class PaymentResponse:
    """Svar från betalningsgeteway."""
    payment_id: str
    status: PaymentStatus
    transaction_id: Optional[str] = None
    timestamp: datetime = None
    message: Optional[str] = None
    qr_code: Optional[str] = None # För Swish/MobilePay
    redrirect_url: Optional[str] = None # För 3D Secure

class PaymentGateway:
    """Huvudklass för betalningsintegration."""

    def __init__(self):
        """Initiera betalningsgeteway med konfiguration."""
        self.config = load_config().get("payment", {})
        self.event_bus = EventBus.get_instance()
        self.safety_monitor = SafetyMonitor()

        # API endpoints
        self.base_url = self.config.get("base_url", "https://api/paymentprovider.com")
        self.api_key = self.config.get("api_key")
        self.merchant_id = self.config.get("merchant_id")
        self.secret_key = self.config.get("secret_key")

        # Session för HTTP-förfågningar
        self.session = None
        self.async_session = None

        # Transactionshistorik
        self.transactions = {}

        logger.info(f"PaymentGateway initialiserad för återförsäljare: {self.merchant_id}")

    def initialize_session(self):
        """Initiera HTTP-session."""
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Marchant-ID": self.merchant_id
            })

    async def initialize_async_session(self):
        """Initiera asynkron HTTP-session."""
        if self.async_session is None:
            self.async_session = aiohttp.ClientSession(headers={
                "Authotization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Marchant-ID": self.merchant_id
            })

    def _generate_signature(self, data: Dict) -> str:
        """Generera HMAC-signature för säkerhet."""
        message = json.dumps(data, sort_keys=True)
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _validate_response(self, response: requests.Response) -> bool:
        """Validera svar från betalningsgateway."""
        try:
            if response.status_code == 200:
                data = response.json()
                if "signature" in data:
                    # Verifiera signaturen
                    excepted_sig = data["signature"]
                    del data["signature"]
                    actual_sig = self._generate_signature(data)
                    return excepted_sig == actual_sig
                return True
            return False
        except Exception as e:
            logger.error(f"Fel vid validering av svar: {e}")
            return False
        
    def process_payment(self, payment_request: PaymentRequest) -> PaymentResponse:
        """
        Bearbeta en betalning.

        Args:
            payment_request: Betalningsförftågan

        Returns:
            PaymentResponse: Resultat av betalningen
        """
        logger.info(f"Bearbetar betalning för order {payment_request.order_id}")

        # Säkerhetskontroll
        if not self.safety_monitor.check_payment_safety(payment_request.amount):
            logger.error(f"Osäkert belopp: {payment_request.amount}")
            return PaymentResponse(
                payment_id=f"ERR_{payment_request.order_id}",
                status=PaymentStatus.FAILED,
                message="Osäkert belopp"
            )
        
        # Skicka händelse om påbörjad betalning
        self.event_bus.publish(EventType.PAYMENT_STARTED, {
            "order_id": payment_request.order_id,
            "amount": str(payment_request.amount),
            "method": payment_request.method.value
        })

        try:
            self.initialize_session()

            # Förbered betalningsdata
            payment_data = {
                "order_id": payment_request.order_id,
                "amount": str(payment_request.amount),
                "currency": payment_request.currency,
                "payment_method": payment_request.method.value,
                "customer_reference": payment_request.customer_reference,
                "metadata": payment_request.metadata or {},
                "timestamp": datetime.utcnow().isoformat()
            }

            # Lägg till signeatur
            payment_data["signature"] = self._generate_signature(payment_data)

            # Välj rätt endpoint baserat på betalningdmetod
            endpoint = self._get_endpoint_for_method(payment_request.method)

            # Skicka förfrågan
            response = self.session.post(
                f"{self.base_url}{endpoint}",
                json=payment_data,
                timeout=30
            )

            # Validera svar
            if self._validate_response(response):
                result = response.json()

                # Skapa betalningssvar
                payment_response = PaymentResponse(
                    payment_id=result.get("payment_id"),
                    status=PaymentStatus(result.get("status")),
                    transaction_id=result.get("transaction_id"),
                    timestamp=datetime.fromisoformat(result.get("timestamp")),
                    message=result.get("message"),
                    qr_code=result.get("qr_code"),
                    redrirect_url=result.get("redirect_url")
                )

                # Spara transaktion
                self.transactions[payment_request.payment_id] = payment_response

                # Skicka händelse
                self.event_bus.publish(EventType.PAYMENT_COMPLETED, {
                    "order_id": payment_request.payment_id,
                    "payment_id": payment_response.payment_id,
                    "status": payment_response.status.value,
                    "amount": str(payment_request.amount)
                })

                logger.info(f"Betalning {payment_response.payment_id} {payment_response.status.value}")
                return payment_response
            else:
                return Exception("Ogiltigt svar från betalningsgataway")
            
        except requests.exceptions.Timeout:
            logger.error("Timeout vid betalning")
            return PaymentResponse(
                payment_id=f"TIMEOUT_{payment_request.order_id}",
                status=PaymentStatus.FAILED,
                message="Timeout från betalningsgateway"
            )
        except Exception as e:
            logger.error(f"Fel vid betalning: {e}")
            self.event_bus.publish(EventType.PAYMENT_FAILED, {
                "order_id": payment_request.order_id,
                "error": str(e)
            })
            return PaymentResponse(
                payment_id=f"ERR_{payment_request.order_id}",
                status=PaymentStatus.FAILED,
                message=f"Betalningsfel: {str(e)}"
            )
        
    async def process_payment_async(self, payment_request: PaymentRequest) -> PaymentResponse:
        """
        Bearbeta betalning asynkront.

        Args:
            payment_request: Betalningsförfrågan

        Returns:
            PaymentResponse: Resultat av betalningen
        """
        try:
            await self.initialize_async_session()

            payment_data = {
                "order_id": payment_request.order_id,
                "amount": str(payment_request.amount),
                "currency": payment_request.currency,
                "payment_method": payment_request.method.value,
                "timestamp": datetime.utcnow().isoformat()
            }
            payment_data["signature"] = self._generate_signature(payment_data)

            endpoint = self._get_endpoint_for_method(payment_request.method)

            async with self.async_session.post(
                f"{self.base_url}{endpoint}",
                json=payment_data,
                timeout=aiohttp.ClientTimeout(tota=30)
            ) as response:
                result = await response.json()

                return PaymentResponse(
                    payment_id=result.get("payment_id"),
                    status=PaymentStatus(result.get("status")),
                    transaction_id=result.get("transaction_id")
                )
            
        except Exception as e:
            logger.error(f"Asynkront betalningsfel: {e}")
            return PaymentResponse(
                payment_id=f"ASYNC_ERR_{payment_request.order_id}",
                status=PaymentStatus.FAILED,
                message=str(e)
            )
        
    def _get_endpoint_for_method(self, method: PaymentMethod) -> str:
        """Hämta rätt api endpoint baserat på betalningsmetoder."""
        endpoints = {
            PaymentMethod.CARD: "/v1/payments/card",
            PaymentMethod.SWISH: "/v1/payments/swish",
            PaymentMethod.MOBILE_PAY: "/v1/payments/mobilepay",
            PaymentMethod.CASH: "/v1/payments/cash",
            PaymentMethod.CREDIT: "/v1/payments/credit"
        }
        return endpoints.get(method, "/v1/payment/card")
    
    def check_payment_status(self, payment_id: str) -> PaymentStatus:
        """
        Kontrollera status för en betalning.

        Args:
            payment_id: ID för betalningen

        Returns:
            PaymentStatus: Nuvarande status
        """
        try:
            self.initialize_session()

            response = self.session.get(
                f"{self.base_url}/v1/payments/{payment_id}/status",
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                return PaymentStatus(result.get("status", PaymentStatus.FAILED.value))
            
            return PaymentStatus.FAILED
        
        except Exception as e:
            logger.error(f"Fel vid statuskontroll: {e}")
            return PaymentStatus.FAILED
        
    def refunde_payment(self, payment_id: str, amount: Optional[Decimal] = None) -> bool:
        """
        Återbetalning en betalning.

        Args:
            payment_id: ID för ursprunglig betalning
            amount: Belopp att återbetala (hela beloppet om None)

        Returns:
            bool: True om återbetalning lyckades
        """
        try:
            self.initialize_session()

            refund_data = {
                "payment_id": payment_id,
                "amount": str(amount) if amount else None,
                "timestamp": datetime.utcnow().isoformat()
            }
            refund_data["signature"] = self._generate_signature(refound_data)

            respnse = self.session.post(
                f"{self.base_url}/v1/refunds",
                json=refund_data,
                timeout=30
            )

            if respnse.status_code == 200:
                logger.info(f"Återbetalning lyckad för {payment_id}")

                self.event_bus.publish(EventType.PAYMENT_REFUNDED, {
                    "payment_id": payment_id,
                    "amount": str(amount)
                })

                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Fel vid återbetalning: {e}")
            return False
        
    def create_qr_code(self, amount: Decimal, message: str = "") -> Optional[str]:
        """
        Skapa QR-kod för Swish-betalning.

        Args:
            amount: Belopp
            message: Meddelande att visa

        Returns:
            str: QR-kod data eller None om misslyckad
        """
        try:
            self.initialize_session()

            qr_data = {
                "amount": str(amount),
                "message": message,
                "merchant_id": self.merchant_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            qr_data["signature"] = self._generate_signature(qr_data)

            response = self.session.post(
                f"{self.base_url}/v1/swish/qr",
                json=qr_data,
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("qr_code")
            
            return None
        
        except Exception as e:
            logger.error(f"Fel vid QR-kod generering: {e}")
            return None
        
    def validate_webhook(self, payload: Dict, signature:str) -> bool:
        """
        Validera webhook från betalningsgateway.

        Args:
            payload: Webhook data
            signature: Mottagen signature

        Returns:
            bool: True om webhook är autenstisk
        """
        try:
            # Ta bort signatur för beräkning
            if "signature" in payload:
                del payload["signature"]

        except Exception as e:
            logger.error(f"Fel vis webhook-validering: {e}")
            return False
        
    def webhook_handler(self, payload: Dict):
        """
        Hantera inkommande webhook från betalningsgateway.

        Args:
            payload: Webhook data
        """
        try:
            # Validera webhook
            signature = payload.get("signature", "")
            if not self.validate_webhook(payload, signature):
                logger.warning("Ogiltig webhook-signatur")
                return
            
            event_type = payload.get("event_type")
            payment_id = payload.get("payment_id")
            status = payload.get("status")

            if event_type == "payment.completed":
                self.event_bus.publish(EventType.PAYMENT_WEBHOOK_RECEIVED, {
                    "payment_id": payment_id,
                    "status": status,
                    "data": payload
                })
                logger.info(f"Webhook: Betalning {payment_id} är {status}")

            elif event_type == "payment.failed":
                logger.error(f"Webhook: Betalning {payment_id} misslyckades")
                self.event_bus.publish(EventType.PAYMENT_FAILED, {
                    "payment_id": payment_id,
                    "reason": payload.get("failure_reason")
                })

            elif event_type == "refund.completed":
                logger.info(f"Webbhok: Återbetalning för {payment_id} slutförd")

        except Exception as e:
            logger.error(f"Fel vid webhook-hantering: {e}")

    def get_daily_report(self, data: datetime = None) -> Dict:
        """
        Hämta daglig rapport om betalningar.

        Args:
            data: Datum (idag om None)

        Returns:
            Dict: Daglig repport
        """
        try:
            self.initialize_session()

            target_data = date or datetime.now()
            date_str = target_data.strftime("%Y-%m-%d")

            response = self.session.get(
                f"{self.base_url}/v1/reports/daily/{date_str}",
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            
            return {}
        
        except Exception as e:
            logger.error(f"Fel vid rapport-hämtning: {e}")
            return {}
        
    def get_transaction_history(self, limit: int = 100) -> list:
        """Hämta transaktionshistorik."""
        return list(self.transactions.values())[-limit:]
    
    def cleanup(self):
        """Städa upp resurser."""
        if self.session:
            self.session.close()

        if self.async_session:
            asyncio.run(self.async_session.close())

        logger.info("PaymentGateway resurser resande")

# Singleton-instans
_payment_gateway_instance = None

def get_payment_gateway() -> PaymentGateway:
    """
    Hämta singleton-instans av PaymentGateway.

    Returns:
        PaymentGateway: Betalningsgateway-instans
    """
    global _payment_gateway_instance
    if _payment_gateway_instance is None:
        _payment_gateway_instance = PaymentGateway()
    return _payment_gateway_instance


# Exempel på användning
if __name__ == "__main__":
    # Testa betalningsgateway
    gateway = get_payment_gateway()

    # Skapa testbetalning
    test_request = PaymentRequest(
        order_id="TEST_ORDER_001",
        amount=Decimal("89.50"),
        method=PaymentMethod.SWISH,
        customer_reference="test@exemple.com"
    )

    # Bearbeta betalning
    respnse = gateway.process_payment(test_request)

    print(f"Betalnings-ID: {respnse.payment_id}")
    print(f"Status: {respnse.status.value}")
    print(f"QR-kod: {"Ja" if respnse.qr_code else "Nej"}")

    gateway.cleanup()