"""
Allmänna hjälpfunktioner för hamburger-maskinsystemet.
Central plats för återanvändbara funktioner och verktyg.
"""

import json
import datetime
import time
import random
import string
import hashlib
import re
from typing import Any, Dict, List, Optional, Union, Tuple
from decimal import Decimal
from pathlib import Path
import csv
import math

def generate_order_id(prefix: str = "ORD") -> str:
    """
    Generera ett unik order-ID

    Args:
        prefix: Perfix för order-ID

    Returns:
        Unikt order-ID i formatet PREFIX_TIMESTAMP_RANDOM
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    random_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}_{timestamp}_{random_str}"

def format_temperature(celsius: float) -> str:
    """
    Formaterar temperatur för vidning.

    Args:
        celsius: Temperature i Celsius

    Returns: 
        Formaterad temoeratursträng
    """
    return f"{celsius:.1f}°C"

def celsius_to_fahrenheit(celsius: float) -> float:
    """
    Konventera Celsius till Fahrenheit.

    Args:
        celsius: Temperature i Celsius

    Returns:
        Temperatur i Fahrenheit
    """
    return (celsius * 9/5) + 32

def calculate_cooking_time(weight_grams: float, thickness_cm: float, desired_doneness: str) -> int:
    """
    Beräkna tillagningstid baserat på parameter.

    Args:
        weight_grams: Vikt i gram
        thickness_cm: Tjocklek i cm
        desired_donneness: Önskad stekgrad ("rare", "medium", "well")

    Returns:
        Tillagningstid i sekiunder
    """
    base_times = {
        "rare": 120,
        "medium": 180,
        "well": 240
    }

    base_times.get(desired_doneness, 180)

    # Justera för vikt och tjocklek
    weight_factor = weight_grams / 150 # 150g som bas
    thickness_factor = thickness_cm / 1.5 # 1.5cm som bas

    cooking_time = base_times * weight_factor * thickness_factor

    return int(cooking_time)

def validate_email(email: str) -> bool:
    """
    Validerar e-postadress.

    Args:
        email: E-postadress är giltig
    """
    pattern = r"^[a-zA-z0-9._%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))

def sanitize_string(input_string: str) -> str:
    """
    Saniterar en sträng genom att ta bort potentiellt farliga tecken.

    Args:
        input_string: Sträng att sanitera

    Returns:
        Saniterad sträng
    """
    # Ta bort HTML-taggar
    sanitized = re.sub(r"<[^>]*>", "", input_string)
    # Ta bort kontrolltrcken
    sanitized = "".join(char for char in sanitized if ord(char) >= 32)
    return sanitized.strip()

def calculate_invnetory_alert_threshold(current_level: int, max_capacity: int) -> Dict[str, bool]:
    """
    Beräkna om inventeringsnivåer behöver varningar.

    Args:
        current_level: Nurvarande nivå
        max_capacity: Max kapacitet

    Returns:
        Dictionary med varningsflaggor
    """
    percentage = (current_level / max_capacity) * 100

    return {
        "critical": percentage <= 10,
        "warning": percentage <= 25,
        "low": percentage <= 40,
        "ok": percentage > 40
    }

def format_time_delta(seconds: int) -> str:
    """
    Formaterar tidsdifferens till läsbart format.

    Args:
        seconds: Antal sekunder

    Returns:
        Formaterad tidssträng
    """
    if seconds < 60:
        return f"{seconds} sekunder"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minut {"er" if minutes != 1 else ""}"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours} timm{"ar" if hours != 1 else ""} {minutes} min"
    else:
        days = seconds // 86400
        return f"{days} dag{"ar" if days != 1 else ""}"
    
def generate_checksum(data: Union[str, bytes]) -> str:
    """
    Genererar checksum för dataverifiering.

    Args:
        data: Data att generera checksum för

    Returns:
        SHA-256 checksum
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    return hashlib.sha256(data).hexdigest()

def round_to_nearest(value: float, nearest: float) -> float:
    """
    Avrundar till närmaste angivna värde.

    Args:
        value: Värde att använda
        nearest: Anvrunda till närmaste detta värde

    Returns:
        Avrundat värde
    """
    return round(value / nearest) * nearest

def parse_currency(amount: Union[str, float, Decimal]) -> Decimal:
    """
    Parserar value till Decimal för korrekt hantering.

    Args:
        amount: Belopp att parsera

    Returns:
        Decimal-objekt
    """
    if isinstance(amount, Decimal):
        return amount
    elif isinstance(amount, float):
        return Decimal(str(amount))
    elif isinstance(amount, str):
        # Ta bort alla icke-numeriska tecken förutom punkt och ninus
        cleaned = re.sub(r"[^\d.-]", "", amount)
        return Decimal(cleaned)
    else:
        return Decimal(str(amount))
    
def format_currency(amount: Decimal) -> str:
    """
    Formaterar valuta för visning.

    Args:
        amount: Belopp att formuntera

    Returns:
        Formaterad valutasträng
    """
    return f"{amount:.2f} SEK"

def calculate_percentage(part: float, whole: float) -> float:
    """
    Beräknar procentandel.

    Args:
        part: Del av helheten
        whole: Hela mängden

    Returns:
        Procentandel
    """
    if whole == 0:
        return 0.0
    return (part / whole) * 100

def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Säker division som hanterar division med noll

    Args:
        numerator: Täljare
        denominator: Nämndare
        default: Värde att returnera vid division med noll

    Returns:
        Result av division eller default värde
    """
    if denominator == 0:
        return default
    return numerator / denominator

def retry_opperation(func, max_attempts: int = 3, delay: float = 1.0, exceptions: Tuple = (Exception,)):
    """
    Dekorator för att försöka igen vid fel.

    Args:
        func: Funktion att köra
        max:attemts: Max antal försök
        delay: Fördröjning mellan försök i sekunder
        exceptions: Undantag som ska trigga försöker igen

    Returns:
        Funktionsresultat
    """
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(max_attempts):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    time.sleep(delay)
                else:
                    raise last_exception
            raise last_exception
        
        return wrapper

def load_json_file(file_path: Union[str, Path]) -> Dict:
    """
    Laddar JSON-fil med felhantering.

    Args:
        file_path: Sökväg till JSON-fil

    Returns:
        Inlästa data som dicitonary
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        raise ValueError(f"Kunde inte ladda JSON-fil {file_path}: {e}")
    
def save_json_file(data: Dict, file_path: Union[str, Path]):
    """
    Spara data till JSON-fil.

    Args:
        data: Data att spara
        file_path: sökväg för sparande
    """
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def timestamp() -> str:
    """
    Ger nuvarande tidsstämpel.

    Returns:
        Tidsstämpel i formatet YYYY-MM-DD HH:MM:SS
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def is_buisness_houers(current_time: Optional[datetime.datetime] = None) -> bool:
    """
    Kontrollerar om det är öppetrid (8:00-22:00).

    Args:
        current_time: Tid att kontrollera (default nu)

    Returns:
        True om det är öppettid
    """
    if current_time is None:
        current_time = datetime.datetime.now()

    open_time = datetime.time(8, 0, 0)
    closing_time = datetime.time(22, 0, 0)

    current_time_only = current_time.time()
    
    return open_time <= current_time_only <= closing_time

def calculate_eat(start_time: datetime.datetime, items_in_queue: int, avg_time_per_item: int = 180) -> datetime.datetime:
    """
    Beräknar uppskattad klar-tid för order.

    Args:
        start_time: Starttid
        items_in_queue: Antal föremål i kö
        avg_time_per_item: Genomsnittig tid per föremål i sekunder

    Returns:
        Uppskattade klar-tid
    """
    total_secondes = items_in_queue * avg_time_per_item
    return start_time + datetime.timedelta(total_secondes)

def validate_phone_number(phone: str) -> bool:
    """
    Validera svenskt telefonnummer.

    Args:
        phone: Telefonnummer att validera

    Returns
        True om telefonnummret är giltigt
    """
    # Ta bort mellanslag, bindestreck och plus-tecken
    cleaned = re.sub(r"[\s\-+]", "", phone)

    # Svenska mobilnummer: 07XXXXXXXX
    # Svenska fasta nummer 08XXXXXXXX eller 0XXXXXXXXX
    pattern = r"^(0[0-9]{1,3})?[0-9]{5,12}$"

    return bool(re.match(pattern, cleaned))

def get_file_size_mb(file_path: Union[str, Path]) -> float:
    """
    Hämtar filsorlek i MB.

    Args:
        file_path: Sökväg till fil

    Returns:
        Storlek i MB
    """
    return Path(file_path).stat().st_size / (1024 * 1024)

def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """
    Delar upp lista i mindre chunkar.

    Args:
        lst: Lista att dela upp
        chunk_size: Storlek på varje chunk

    Returns:
        Lista av listor
    """
    return [list[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def generate_random_color() -> str:
    """
    Generera slumpmässig hex-färg.

    returns:
        Hex-färg (t.ex. #FF5733)
    """
    return f"#{random.randint(0, 255):02x}-{random.randint(0, 255):02x}-{random.randint(0, 255):02x}"

def normalize_value(value:float, min_val: float, max_val: float) -> float:
    """
    Normaliserar värde mellan 0 och 1.

    Args:
        value: Värde att normalisera
        min_val: Minsta värde
        max_val: Högsta värde

    Returns:
        Normaliserat värde
    """
    if max_val - min_val == 0:
        return 0.0
    return (value - min_val) / (max_val - min_val)

def calculate_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Beräknar avstånd mellan två punkter.

    Args:
        x1, y1: Koordinater för punkt 1
        x2, y2: Koordinater för punkt 2

    Returns:
        Avstånd
    """
    return math.sqrt((x2 -x1)**2 + (y2 - y1)**2)

def format_bytes(size_bytes: int) -> str:
    """
    Formaterar byte-storlek till läsbart format.

    Args:
        size_bytes: Storlek i bytes

    Returns:
        formaterad storlek
    """
    for unit in  ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

if __name__ == "__main__":
    # Testa några funktioner
    print(f"Order ID: {generate_order_id()}")
    print(f"Formaterad temperatur: {format_temperature(185.5)}")
    print(f"Tillagningstid (150g, 1,5cm, medium): {calculate_cooking_time(150, 1.5, "medium")}s")
    print(f"Validera epost: {validate_email("test@exempel.com")}")
    print(f"Tidsdifferens: {format_time_delta(3665)}")
    print(f"Normalisera värde: {normalize_value(75, 50, 100)}")

