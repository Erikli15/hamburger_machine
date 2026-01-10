#!/usr/bin/env python 3
"""
Kortläsarmoule för hamburgerautomaten.
Hanterar kortbetalningar via chip- och NFC-läsare.
"""

import time
import json
import threading
from enum import Enum
from typing import Optional, Dict, Any, Callable
import logging

# Simulerade import - ersätt med riktiga biblotek för din hårdvara
# import serial
# import RPi.GPIO as GPIO # För Raspbarry Pi

logger = logging.getLogger(__name__)

class CardType(Enum):
    """Typer av kort som stöds."""
    CREDIT = "credit"
    DEBIT = "debit"
    NFC = "nfc"
    CHIP = "chip"
    MAGSTRIPE = "magstrip"
    UNKNOWN = "unknown"

class PaymentStatus(Enum):
    """Status för betalningsförsöka."""
    PENDING = "pending"
    PROCESSING = "processing"
    APPROVED = "approved"
    DECLINED = "declined"
    CANCELLED = "cancrlled"
    ERROR = "error"

class CardReader:
    """
    Klass för att hantera kortläsarens funktionalitet.
    Stödjar både chip, magnetremsa och NFC-betalningar.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initiera kortläsaren.

        Args:
            config: Konfigurationsdictionary med inställningar
        """
        self.config = config
        self.is_initialized = False
        self.is_reading = False
        self.current_card = None
        self.payment_callback = None
        self.status = "disconnected"

        # Hårdvarasupecifika inställningar
        self.port = config.get("post", "/dev/ttyUSB0")
        self.baudrate = config.get("baudrate", 9600)
        self.timeout = config.get("timeout", 10)
        self.simulate = config.get("simulate", False)

        # Betalningsinställningar
        self.max_amount = config.get("max_amount", 1000.0)
        self.require_pin = config.get("require_pin", True)
        self.currency = config.get("currency", "SEK")

        # Trådhanteing
        self.read_thred = None
        self.stop_event = threading.Event()

        logger.info(f"CardReader initaliserad med konfig: {config}")

    def initialize(self) -> bool:
        """
        Initiera och anslut till kortläsarens hårvara.

        Returns:
            bool: True om initiering lyckades
        """
        try:
            if self.simulate:
                logger.info("Simuleringsläge aktiverat för kortläsaren")
                self.status = "simulated"
                self.is_initialized = True
                return True
            
            # För riktig hordvara - kommenterar bort för nu
            # self._setup_hardware()

            logger.info(f"Ansluter till kortläsare på port {self.port}")

            # Simmulerad anslutning - ersätt med riktig kod
            time.sleep(1)

            self.status = "connected"
            self.is_initialized = True
            logger.info("Kortläsare initerad och ansluten")

            return True
        
        except Exception as e:
            logger.error(f"Fel vid initiering av kortläsare {e}")
            self.status = "error"
            return False
        
    def start_reading(self, callback: Optional[Callable] = None) -> bool:
        """
        Starta kortläsningen i bakgrunden.

        Args:
            callback: Funktion att läsningen startades

        Returns:
            bool: True om läsningen startades
        """
        if not self.is_initialized:
            logger.error("Kortläsare inte initierad")
            return False
        
        if self.is_reading:
            logger.warning("Kortläsning redan pågår")
            return False
        
        self.payment_callback = callback
        self.is_reading = True
        self.stop_event.clear()

        # Starta läsningstråd
        self.read_thred = threading.Thread(
            target=self._read_loop,
            daemon=True,
            name="CardReaderThread"
        )
        self.read_thred.start()

        logger.info("Kortläsning startad")
        return True
    
    def stop_reading(self) -> None:
        """Stoppa kortläsningen."""
        self.is_reading = False
        self.stop_event.set()

        if self.read_thred and self.read_thred.is_alive():
            self.read_thred.join(timeout=2.0)

        logger.info("Kortläsning stoppad")

    def process_payment(self, amount: float, order_id: str, card_data:Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa en betalning med kortdata.

        Args:
            amount: Belopp att debitera
            order_id: Order-ID för spårning
            card_data: Data från kortet

        Returns:
            Dict: Betalningsresultat
        """
        try:
            if amount > self.max_amount:
                logger.warning(f"Belopp {amount} överstiger maxgräns {self.max_amount}")
                return self._create_response(
                    success=False,
                    status= PaymentStatus.DECLINED,
                    message="Ogiltiga kortdata"
                )
            
            # Simulera betalningsprocess
            logger.info(f"Processar betalning: {amount} {self.currency} för order {order_id}")

            # I verkligheten: Anslut till betalningsgateway här
            # transaction_id = self._process_with_gateway(amount, card_data, order_id)

            # Simulerat resultat
            transcation_id = f"TXN_{int({time.time()})}_{order_id}"

            logger.info(f"Betalning godkänd: {transcation_id}")

            return self._create_response(
                success=True,
                status=PaymentStatus.APPROVED,
                message="Betalning godkänd",
                transcation_id=transcation_id,
                amount=amount,
                currency=self.currency
            )
        
        except Exception as e:
            logger.error(f"Fel vid betalningsprocess: {e}")
            return self._create_response(
                success=False,
                status=PaymentStatus.ERROR,
                message=f"Betalningsfel: {str(e)}"
            )
        
    def read_card(self) -> Optional[Dict[str, Any]]:
        """
        Läs ett kort (blockerad anrop).

        Returns:
            Dict: Kortdata eller None om ingen kort
        """
        if not self.is_initialized:
            logger.error("Kortläsaren inte initierad")
            return None
        
        try:
            logger.info("Väntar på kort...")

            if self.simulate:
                # Simulerat kort
                time.sleep(2)
                return self._simulate_card_read()
            
            # För riktig hårdwara:
            # card_data = self._read_forma_hardware()
            # return self._parse_card_data(card_data)

            # Tillfällig simulering
            return self._simulate_card_read()
        
        except Exception as e:
            logger.error(f"Fel vid kortläsning: {e}")
            return None
    def cancel_payment(slef) -> bool:
        """Avbryt pågånde betalning."""
        logger.info("Betalning avbruten av användare")
        # I verkligheten: Skicka avbrytkommando till terminalen
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Hämta status för kortläsaren."""
        return {
            "status": self.status,
            "is_initialezed": self.is_initialized,
            "is_reading": self.is_reading,
            "connected": self.status == "connected",
            "simulated": self.simulate,
            "config": {
                "port": self.port,
                "currency": self.currency,
                "max_amount": self.max_amount
            }
        }
    
    def cleanup(self) -> None:
        """Städa upp och stäng ner."""
        self.stop_reading()
        self.is_initialized = False
        self.status = "disconnected"

        if not self.simulate:
            # Stäng hårdvarukopplingar
            # self._cleanup_hardware()
            pass

        logger.info("Kortläsare avslutad")

    # Privata metoder

    def _read_loop(self) -> None:
        """Bakgrundstård för kontinurelig kortläsning."""
        logger.info("Kortläsningsloop startad")

        while not self.stop_event.is_set() and self.is_reading:
            try:
                card_data = self.read_card()

                if card_data and self.payment_callback:
                    self.payment_callback(card_data)

                # Vänta kort för nästa läsning
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Fel i kortläsningsloop: {e}")
                time.sleep(1)

        logger.info("Kortläsningsloop avslutad")

    def _validate_card_data(self, card_data: Dict[str, Any]) -> bool:
        """Validera att kortdata är giltig."""
        required_fields = ["card_number", "expiry_data", "card_type"]

        for field in required_fields:
            if field not in card_data or not card_data[field]:
                logger.warning(f"Saknat fält i kortdata: {field}")
                return False

        # Validerad kortnummer (Luhn-algoritm)
        if not self._validate_card_data_number(card_data.get("card_number", "")):
            return False
        
        return True
    
    def _validate_card_number(self, card_number: str) -> bool:
        """Validera kortnummer med Luhn-algoritm."""
        # Ta bort mellandslag och bindestreck
        card_number = card_number.replace(" ", "").replace("-", "")

        if not card_number.isdigit():
            return False
        
        # Luhn-algoritm
        digits = list(map(int, card_number))
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)

        for d in even_digits:
            checksum += sum(divmod(d * 2, 10))

        return checksum % 10 == 0
    
    def _validate_expiry_date(self, expiry_data: str) -> bool:
        """Validera utgåmgsdatum."""
        try:
            if "/" not in expiry_data:
                return False
            
            month_str, year_str = expiry_data.split("/")
            month = int(month_str)
            year = int(year_str)

            # Lägg till 2000 om år är tvåsiffrigt
            if year < 100:
                year += 2000

            # Kontrollera kortet har gått ut
            if month < 1 or month > 12:
                return False
            
            # Kontrollera om kortet har gått ut
            current_year = time.localtime().tm_year
            current_month = time.localtime().tm_mon

            if year < current_year or (year == current_year and month < current_month):
                return False
            return True
        except (ValueError, AttributeError):
            return False
        
    def _simulate_card_read(self) -> Dict[str, Any]:
        """Simulera ett kort om läs."""
        import random

        card_types = [CardType.CREDIT, CardType.DEBIT, CardType.NFC]
        card_type = random.choice(card_types)

        # Generera ett giltig testkortnummer (Luhn-giltigt)
        test_numbers = [
            "4111 1111 1111 1111", # Visa testnummer
            "5500 0000 0000 0004", # MasterCard testnummer
            "3400 0000 0000 0009", # American Express testnummer
            "6011 0000 0000 0004" # Discover testnummer 
        ]

        card_data = {
            "card_number": random.choice(test_numbers).replace(" ", ""),
            "expiry_date": f"{random.randint(1, 12):02d}/{random.randint(24, 30):02d}",
            "card_type": card_type.value,
            "card_holder": "TEST KUND",
            "read_time": time.time(),
            "simulated": True
        }

        if card_type == CardType.CHIP:
            card_data["chip_present"] = True
            card_data["chip_data"] = "SIMULATED_CHIP_DATA"
        elif card_type == CardType.NFC:
            card_data["nfc_uid"] = f"UID_{random.randint(1000, 9999)}"
            card_data["contactless"] = True

        logger.info(f"Simulerat kort läst: {card_type.value}")
        return card_data
    
    def _create_response(self, success: bool, status: PaymentStatus, message: str, **kwargs) -> Dict[str, Any]:
        """Skapa ett standardiserat betalningssvar."""
        response = {
            "success": success,
            "status": status.value,
            "message": message,
            "timestamp": time.time(),
            "reader_id": self.config.get("reader_id", "default"),
            "currency": self.currency
        }
        response.update(kwargs)
        return response
    
    def _setup_hardware(self) -> None:
        """Konfigurera hårdvarugränssnittet."""
        # Implenetera baserat på din specifika hårdvara
        # Exempel för serial:
        # self.serial_conn = serial(
        # port=self.port,
        # baudrate=self.baudrate,
        # timeout=self.timeout
        #)
        pass

    def _cleanup_hardware(self) -> None:
        """Stängt hårdvarukopplingar."""
        # if hasattr(self, "serial_conn") and self.serial_conn.is_open:
        # self.serial_comn.close()
        pass

# Enkel API för extern användning

class PaymentInterface:
    """Förenklat API för betalingration."""

    def __init__(self, config_path: Optional[str] = None):
        """Initiera betalningsgränssnitt."""
        from ...utils.config_loader import load_config

        if config_path:
            config = load_config(config_path).get("payment", {})
        else:
            config = {
                "simulate": True,
                "currency": "SEK",
                "max_amount": 1000.0
            }

            self.reader = CardReader(config)
            self.initialized = False

    def initialize(self) -> bool:
        """Initiera betalningssystemet."""
        if self.reader.initialize():
            self.initialize = True
            logger.info("PaymentInterface initierad")
            return True
        return False
    
    def process_order_payment(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa betalning för en order.

        Args:
            order_data: Orderinformation inklusive belopp

        Returns:
            Dict: Betalningsresultat
        """
        if not self.initialized:
            return {
                "success": False,
                "message": "Betalningssystem inte initierat"
            }
        
        amount = order_data.get("total_amount", 0)
        order_id = order_data.get("order_id", "unknown")

        # Läs kort
        logger.info(f"Begär betalning: {amount} SEK för order {order_id}")
        print("Var god sätt in eller blippa kort...")

        card_data = self.reader.read_card()

        if not card_data:
            return {
                "success": False,
                "message": "Inget kort upptäckt",
                "status": PaymentStatus.CANCELLED.value
            }
        
        # Processa betalning
        result = self.reader.process_payment(amount, order_id, card_data)

        # Logga resultat (skyddat data)
        safe_card = card_data.copy()
        if "card_number" in safe_card:
            safe_card["card_number"] = safe_card["card_number"][-4:]

        logger.info(f"Betalaningsresultat för orde {order_id}: {result["status"]}")

        return result

    def cleanup(self) -> None:
        """Städa upp."""
        if self.initialized:
            self.reader.cleanup()
            self.initialized = False

# Test och demo
if __name__ == "__main__":
    import sys

    # Konfigurarera loggning
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s -%(name)s - %(levelname)s - %(message)s"
    )

    print("=== Test av kortläsarmodul ===")

    # Skapa testkonfiguration
    config = {
        "simulate": True,
        "port": "/dev/ttyUSB0",
        "baudrate": 9600,
        "currency": "SEK",
        "max_amount": 500.0,
        "reader_id": "test_reader_001"
    } 

    # Testa CardReader
    reader = CardReader(config)

    if reader.initialize():
        print("✓ Kortläsare initierad")

        # Visa status
        status = reader.get_status()
        print(f"Status: {json.dumps(status, indent=2, ensure_ascii=False)}")

        # Testa kortläsning
        print("\nTestar kortlässaren")
        card = reader.read_card()

        if card:
            print(f"✓ Kort läst: {card['card_type']}")

            # Testa betalning
            print("\nTestar betalning...")
            result = reader.process_payment(
                amount=125.50,
                order_id="TEST_001",
                card_data=card
            )

            print(f"Betalningsresulrat: {json.dumps(result, indent=2, ensure_ascii=False)}")

            # Testa kontinierlig läsning med callback
            print("\nTestar kontinuerlig läsning...")

            def payment_callback(card_data):
                print(f"Callback: Kort upptäckt - {card_data["card_type"]}")

                reader.start_reading(payment_callback)

                print("Väntar på kort (5 sekunder)...")
                time.sleep(5)

                reader.stop_reading()
                reader.cleanup()

                print("\n✓ Alla tester slutförda")
                sys.exit(0)
        else:
            print("✗ Kunde inte initiera kortläsare")
            sys.exit(1)