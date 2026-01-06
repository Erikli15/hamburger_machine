"""
Fritös Controller - Styrning och övervakning av hamburgerfritösen
Hanterar temperaturreglering, säkerhetsfunktioner och fritösprocesser
"""

import time
import threading
import logging
from typing import Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

# Relativa imports för systemintegration
from ...utils.logger import get_logger
from ...utils.validators import validate_temperature_range
from ...core.event_bus import EventBus, EventType
from ...core.safety_monitor import SafetyStatus
from .sensor_manager import TemperaturSensor, SensorType

class FryingStatus(Enum):
    """Status för fritösprocessen"""
    IDLE = "inaktiv"
    PREHEATING = "förvarmning"
    READY = "redo"
    FRYING = "friterar"
    COOLDOWN = "nedkylning"
    ERROR = "fel"
    MAINTENANCE = "underhåll"

class OilQuality(Enum):
    """Oljekvalitetsstatus"""
    EXCELLENT = "utmärkt"
    GOOD = "bra"
    FAIR = "måttlig"
    POOR = "dålig"
    CRITICAL = "kritisk"

@dataclass
class FryingBatch:
    """Representerar en batch hamburger i fritösen"""
    batch_id: str
    start_time: datetime
    quantity: int
    target_temp: float
    cooking_time: int # i sekunder
    burger_type: str
    current_temp: float = 0.0
    time_elapsed: int = 0
    completed: bool = False

class FryerController:
    """
    Huvudkontroller för hamburgerfritösen
    Hanterar temperaturreglering, timers och säkerhetsfunktioner
    """

    def __init__(self, config: Dict, event_bus: EventBus):
        """
        Initierar fritöskontrollern

        Args:
            config: Konfigurationsdictionary
            event_bus: EventBus för systemhändelser
        """
        self.logger = get_logger(__name__)
        self.event_bus = event_bus

        # Konfiguration
        self.config = config.get("fryer", {})
        self.fryer_id = self.config.get("id", "fryer_01")
        self.max_capacity = self.config.get("max_capacity", 8)

        # Temperaturinställningar
        self.target_temperature = self.config.get("target_temperature", 175.0) # °C
        self.temp_tolerance = self.config.get("temp_tolerance", 2.0) # ±°C
        self.min_safe_temp = self.config.get("min_safe_temp", 160.0) # °C
        self.max_safe_temp = self.config.get("max_safe_temp", 190.0) # °C
        self.preheat_temp = self.config.get("preheat_temp", 170) # °C

        # Oljehantering
        self.oil_quality = OilQuality.EXCELLENT
        self.oil_life_hours = 0
        self.max_oil_life = self.config.get("max_oil_life", 72) # timmar
        self.last_oil_change = datetime.now()

        # Status och state
        self.status = FryingStatus.IDLE
        self.current_temperature = 20.0 # Starttemoeratur (rumstemp)
        self.is_heating = False
        self.is_cooling = False
        self.safety_status = SafetyStatus.NORMAL

        # Aktiva batches
        self.active_batch: Optional[FryingBatch] = None
        self.batch_history = []

        # Sensorer
        self.temp_sensor = TemperaturSensor(
            sensor_id=f"{self.fryer_id}_temp",
            sensor_type=SensorType.DS18B20,
            bus_number=self.config.get("bus_number", 1)
        )

        # Trådhantering
        self._control_thread = None
        self._monitor_thread = None
        self._running = False
        self._lock = threading.RLock()

        # PIO-regulator parametrar (förenklad)
        self.kp = self.config.get("kp", 2.5) # Proportional gain
        self.ki = self.config.get("ki", 0.1) # Integral gain
        self.kd = self.config.get("kd", 0.5) # Derivative gain
        self._integral = 0.0
        self._prev_error = 0.0

        self.logger.info(f"Fritöskontroller initierad: {self.fryer_id}")
        self.event_bus.publish(EventType.FRYER_INITIALIZED, {
            "fryer_id": self.fryer_id,
            "status": self.status.value
        })

    def start(self) -> bool:
        """
        Startar fritöskontrollern och dess övervakningstrådar

        Returns:
            bool: True om start lyckades
        """
        with self._lock:
            if self._running:
                self.logger.warning("Fritöskontroller redan igånd")
                return False
            
            self._running = True

        # Starta kontrolltråd
        self._control_thread = threading.Thread(
            target=self._control_loop,
            name=f"{self.fryer_id}_control",
            daemon=True
        )
        self._control_thread.start()

        # Starta övervakningstråd
        self._control_thread = threading.Thread(
            target=self._monitor_loop,
            name=f"{self.fryer_id}_monitor",
            daemon=True
        )
        self._monitor_thread.start()

        self.logger.info(f"Fritöskontroller startad: {self.fryer_id}")
        self.event_bus.publish(EventType.FRYER_STARTED, {
            "fryer_id": self.fryer_id
        })

        return True
    
    def stop(self) -> bool:
        """
        Stoppar fritöskontollern säkert

        Returns:
            bool: True om stopp lyckades
        """
        with self._lock:
            if not self._running:
                return False
            
            self._running = False
            self._stop_heating()

            # Vänta på att trådarna ska avslutas
            if self._control_thread:
                self._control_thread.join(timeout=5.0)
            if self._monitor_thread:
                self._monitor_thread.join(timeout=5.0)

            self.status = FryingStatus.IDLE
            self.logger.info(f"Fritöskontroller stoppad: {self.fryer_id}")
            self.event_bus.publish(EventType.FRYER_STOPPED, {
                "fryer_id": self.fryer_id
            })

            return True
        
    def preheat(self) -> bool:
        """
        Startar förvärmning av fritösen

        Returns:
            bool: True om förvärmning påbörjades
        """
        with self._lock:
            if self.status != FryingStatus.IDLE:
                self.logger.warning(f"Kan inte starta förvärmning, status: {self.status}")
                return False
            
            if not self._check_oil_quality():
                self.logger.error("Dålig oljekvalitet - förvärmning avbruten")
                self._trigger_maintenance_alert()
                return False
            
            self.status = FryingStatus.PREHEATING
            self.target_temperature = self.preheat_temp
            self.logger.info(f"Förvärmning påbörjade, mål: {self.target_temperature}°C")

            self.event_bus.publish(EventType.FRYER_PREHEATING, {
                "fryer_id": self.fryer_id,
                "target_temp": self.target_temperature
            })

            return True
        
    def start_frying(self, batch_id: str, quantity: int, burger_type:str, cooking_time: int) -> Optional[FryingBatch]:
        """
        Startar en fritösbatch

        Args:
            batch_id: Unikt batch_ID
            quantity: Antal hamburger
            burger_type: Typ av hamburger
            cooking_time: Fritöstid i sekunder

        Returns:
            FryingBatch om startades, annars None
        """
        with self._lock:
            # Validera indata
            if quantity <= 0 or quantity > self.max_capacity:
                self.logger.error(f"Ogiltig kvantitet: {quantity}")
                return None
            
            if cooking_time <= 0:
                self.logger.error(f"Ogiltig fritöstid: {cooking_time}")
                return None
            
        # Kontrollera status
        if self.status not in [FryingStatus.READY, FryingStatus.IDLE]:
            self.logger.warning(f"Kan inte starta batch, status: {self.status}")
            return None

        # Kontrollera temperatur
        if not self._is_temperature_ready():
            self.logger.warning("Temperatur inte redo - startar förvärmning")
            self.preheat()
            return None

        # Skapa ny batch
        self.active_batch = FryingBatch(
            batch_id=batch_id,
            start_time=datetime.now(),
            quantity=quantity,
            target_temp=self.target_temperature,
            cooking_time=cooking_time,
            burger_type=burger_type,
            current_temp=self.current_temperature
        ) 

        self.status = FryingStatus.FRYING
        self.logger.info(f"Fritösbatch startade: {batch_id}, {quantity}st {burger_type}")

        self.event_bus.publish(EventType.FRYER_BATCH_STARTED, {
            "fryer_id": self.fryer_id,
            "batch_id": batch_id,
            "quanity": quantity,
            "burger_type": burger_type,
            "cooking_time": cooking_time
        })

        return self.active_batch
    
    def get_status(self) -> Dict:
        """
        Hämtar aktuell status för fritösen

        Returns:
            Dictionary med statusinformation
        """
        with self._lock:
            batch_info = {
                "batch_id": self.active_batch.batch_id,
                "quanity": self.active_batch.quantity,
                "burger_type": self.active_batch.burger_type,
                "time_elapsed": self.active_batch.time_elapsed,
                "cooking_time": self.active_batch.cooking_time,
                "progress_percentage": min(100, (self.active_batch.time_elapsed / self.active_batch.cooking_time) * 100)
            }

            return {
                "fryer_id": self.fryer_id,
                "status": self.safety_status.value,
                "current_temperature": round(self.current_temperature, 1),
                "target_teperature": round(self.target_temperature, 1),
                "is_heating": self.is_heating,
                "is_cooling": self.is_cooling,
                "safety_status": self.safety_status.value,
                "oil_quality": self.oil_quality.value,
                "oil_life_hours": round(self.oil_life_hours, 1),
                "active_batch": batch_info,
                "max_capacity": self.max_capacity
            }
        
    def set_target_temperature(self, temperature: float) -> bool:
        """
        Sätter mål temperaturen för fritösen

        Args:
            temperature: Ny mål temperatur i °C

        Returns:
            bool: True om temperaturen accepterades
        """
        try:
            validate_temperature_range(
                temperature,
                min_val=self.min_safe_temp,
                max_val=self.max_safe_temp
            )

            with self._lock:
                self.target_temperature = temperature
                self.logger.info(f"Mål temperaturen satt till {temperature}°C")

                self.event_bus.publish(EventType.FRYER_TEMP_CHANGED, {
                    "fryer_id": self.fryer_id,
                    "target_temp": temperature,
                    "old_temp": self.target_temperature
                })

                return True
            
        except ValueError as e:
            self.logger.error(f"Ogiltig temperatur: {temperature}°C - {e}")
            return False
        
    def emergency_stop(self) -> bool:
        """
        Nödstopp av fritösen - omedelbart stopp

        Returns:
            bool: True om nödstopp aktiverades
        """
        with self._lock:
            self._stop_heating()
            self.status = FryingStatus.ERROR
            self.safety_status = SafetyStatus.EMERGENCY_STOP

            # Avbryt aktiv batch
            if self.active_batch:
                self.active_batch.completed = True
                self.batch_history.append(self.active_batch)
                self.active_batch = None

            self.logger.critical(f"NÖDSTOPP AKTIVERAD för fritös: {self.fryer_id}")

            self.event_bus.publish(EventType.FRYER_EMERGENCY_STOP, {
                "fryer_id": self.fryer_id,
                "reason": "manual_emergency_stop"
            })

            return True
        
    def _control_loop(self):
        """Huvudkontrolloop för temperaturreglering"""
        control_interval = self.config.get("control_interval", 1.0) # sekunder

        while self._running:
            try:
                # Läs temperatur
                self._read_temperature()

                # Utanför kontrollberäkningar
                self._update_control()

                # Uppdatera batch-status
                if self.status == FryingStatus.FRYING and self.active_batch:
                    self._update_batch()

                # Uppdatera oljekvalitet
                self._update_oil_quality()

                # Publicera statusuppdatering
                self.event_bus.publish(EventType.FRYER_STATUS_UPDATE, self.get_status())

            except Exception as e:
                self.logger.error(f"Fel i kontrolloop: {e}")
                self._handle_error(e)

            time.sleep(control_interval)

    def _monitor_loop(self):
        """Säkerhetsövervakningsloop"""
        monitor_interval = self.config.get("monitor_interval", 0.5)

        while self._running:
            try:
                # Temperatursäkerhetskontroller
                if not self._check_temperature_safety():
                    self._handle_temperature_alert()

                # Oljekvalitetskontroll
                if not self._handle_oil_quality():
                    self.handle_oil_quality_alert()

                # Överhettningsskydd
                if self.current_temperature > self.max_safe_temp + 10:
                    self._trigger_overheat_protection()

            except Exception as e:
                self.logger.error(f"Fel i övervakningsloop {e}")

            time.sleep(monitor_interval)

    def _read_temperature(self):
        """Läs temperatur från sensor"""
        try:
            raw_temp = self.temp_sensor.read_temperature()

            # Filtrera och validera temperatur
            if raw_temp is not None:
                # Enkel filterering (kan ersättas med mer avanderad)
                self.current_temperature = 0.7 * self.current_temperature + 0.3 * raw_temp

                # Uppdatera batchtemperatur
                if self.active_batch:
                    self.active_batch.current_temp = self.current_temperature

        except Exception as e:
            self.logger.error(f"Fel vid temperaturavläsning: {e}")
            self._handle_sensore_error()

    def _update_control(self):
        """PID-baserad teperaturreglering"""
        if self.status == FryingStatus.IDLE:
            self._stop_heating()
            return
        
        # Beräkna fel
        error = self.target_temperature - self.current_temperature

        # PID-beräkningar
        self._integral += error
        derivative = error -self._prev_error

        # Beräkna styrsignal
        control_signal = (
            self.kp * error +
            self.ki * self._integral +
            self.kd * derivative
        )

        # Begränsa intergralwindup
        self._integral = max(min(self._integral, 100), -100)

        # Applicera styrsignal
        if control_signal > 1.0 and not self.is_heating:
            self._start_heating()
        elif control_signal < -1.0 and self.is_heating:
            self._stop_heating()

        # Uppdatera status baserat på temperatur
        if abs(error) <= self.temp_tolerance:
            if self.status == FryingStatus.PREHEATING:
                self.status = FryingStatus.READY
                self.logger.info(f"Fritös redo vid {self.current_temperature}°C")

                self.event_bus.publish(EventType.FRYER_READY, {
                    "fryer_id": self.fryer_id,
                    "temperature": self.current_temperature
                })
        self._prev_error = error

    def _update_batch(self):
        """Uppdaterar aktiv batch"""
        if not self.active_batch:
            return
        
        # Uppdatera förfluten tid
        ellipsed = (datetime.now() - self.active_batch.start_time).total_seconds()
        self.active_batch.time_elapsed = int(ellipsed)

        # Kontrollera om batch är klar
        if ellipsed >= self.active_batch.cooking_time:
            self._complete_batch()

    def _complete_batch(self):
        """Avslutar en bach"""
        with self._lock:
            if not self.active_batch:
                return
            
            self.active_batch.completed = True
            self.active_batch.time_elapsed = self.active_batch.cooking_time

            self.logger.info(
                f"Batch {self.active_batch.batch_id} klar:"
                f"{self.active_batch.quantity}st {self.active_batch.burger_type}"
            )

            # Lägg till historik
            self.batch_history.append(self.active_batch)

            # Publicera batch-klar händelse
            self.event_bus.publish(EventType.FRYER_BATCH_COMPLETED, {
                "fryer_id": self.fryer_id,
                "batch_id": self.active_batch.batch_id,
                "quantity": self.active_batch.quantity,
                "burger_type": self.active_batch.burger_type,
                "cooking_time": self.active_batch.cooking_time
            })

            # Återställ för nästa batch
            self.active_batch = None
            self.status = FryingStatus.READY

    def _start_heating(Self):
        """Aktiverar värmarelement (simulerad)"""
        if not Self.is_heating:
            Self.is_heating = True
            Self.logger.debug("Värmarelement aktiverade")

    def _stop_heating(self):
        """Stänger av värmarelement"""
        if self.is_heating:
            self.is_heating = False
            self.logger.debug("Värmarelement avstängda")

    def _check_temperature_safety(self) -> bool:
        """Kontrollerar temperatur inom säkra gränser"""
        if self.current_temperature < self.min_safe_temp - 5:
            self.safety_status = SafetyStatus.LOW_TEMP_WARNING
            return False
        
        if self.current_temperature > self.max_safe_temp:
            self.safety_status = SafetyStatus.HIGH_TEMP_WARNING
            return False
        
        if self.safety_status in [SafetyStatus.LOW_TEMP_WARNING, SafetyStatus.HIGH_TEMP_WARNING]:
            self.safety_status = SafetyStatus.NORMAL

        return True
    
    def _check_oil_quality(self) -> bool:
        """Kontrollerar oljekvalitet"""
        if self.oil_quality in [OilQuality.POOR, OilQuality.CRITICAL]:
            return False
        
        return True
    
    def _update_oil_quality(self):
        """Uppdaterar oljekvalitet baserat på användning"""
        if self.status == FryingStatus.FRYING:
            # Öka oljeliv baserat på fritöstid
            self.oil_life_hours += (1 / 3600) # 1 sekund = 1/3600 timmar

        # Degradera kvalitet baserat på användning
        if self.oil_life_hours > self.max_oil_life * 0.8:
            self.oil_quality = OilQuality.CRITICAL
        elif self.oil_life_hours > self.max_oil_life * 0.6:
            self.oil_quality = OilQuality.POOR
        elif self.oil_life_hours > self.max_oil_life * 0.4:
            self.oil_quality = OilQuality.FAIR
        elif self.oil_life_hours > self.max_oil_life * 0.2:
            self.oil_quality = OilQuality.GOOD

    def _is_temperature_ready(self) -> bool:
        """Kontrollera om temperaturen är redo för fritösning"""
        return(
            self.status == FryingStatus.READY or
            (self.status == FryingStatus.PREHEATING and
             abs(self.current_temperature - self.target_temperature)<= self.temp_tolerance)
        )
    
    def _handle_temperature_alert(self):
        """Hanterar temperaturvarningar"""
        if self.safety_status == SafetyStatus.HIGH_TEMP_WARNING:
            self._stop_heating()
            self.event_bus.publish(EventType.FRYER_TEMP_ALERT, {
                "fryer_id": self.fryer_id,
                "alert": "high_temperature",
                "temperature": self.current_temperature
            })

    def _handle_oil_quality_alert(self):
        """Hanterar olkekvalitetsvarningar"""
        self.event_bus.publish(EventType.FRYER_MAINTENANCE_ALERT, {
            "fryer_id": self.fryer_id,
            "alert": "oil_quality",
            "oil_quality": self.oil_quality.value,
            "oil_life_hours": self.oil_life_hours
        })

    def _trigger_overheat_protection(self):
        """Aktiverar överhettningsskydd"""
        self.emergency_stop()
        self.event_bus.publish(EventType.FRYER_OVERHEAT, {
            "fryer_id": self.fryer_id,
            "temperature": self.current_temperature
        })

    def _trigger_maintenance_alert(self):
        """Trigger underhållsvarning"""
        self.status = FryingStatus.MAINTENANCE
        self.event_bus.publish(EventType.FRYER_MAINTENANCE_REQUIRED, {
            "fryer_id": self.fryer_id,
            "reason": "oil_change_needed"
        })

    def _handle_sensor_error(self):
        """Hanterar sensorfel"""
        self.safety_status = SafetyStatus.SENSOR_ERROR
        self.event_bus.publish(EventType.FRYER_SENSOR_ERROR, {
            "fryer_id": self.fryer_id,
            "sensor_type": "temperature"
        })

    def _handle_error(self, error: Exception):
        """Generell felhantering"""
        self.status = FryingStatus.ERROR
        self.logger.error(f"Fritösfel: {error}")

        self.event_bus.publish(EventType.FRYER_ERROR, {
            "fryer_id": self.fryer_id,
            "error": str(error),
            "status": self.status.value
        })

    def change_oil(self):
        """Registrerar oljebyte"""
        with self._lock:
            self.oil_quality = OilQuality.EXCELLENT
            self.oil_life_hours = 0
            self.last_oil_change = datetime.now()

            self.logger.info(f"Oljebyte registrerat för {self.fryer_id}")

            self.event_bus.publish(EventType.FRYER_OIL_CHANGED, {
                "fryer_id": self.fryer_id,
                "timestamp": datetime.now().isoformat()
            })

    def get_maintenance_info(self) -> Dict:
        """Hämtar underhållsinformation"""
        return {
            "fryer_id": self.fryer_id,
            "oil_quality": self._check_oil_quality.value,
            "oil_life_hours": round(self.oil_life_hours, 1),
            "max_oil_life": self.max_oil_life,
            "last_oil_change": self.last_oil_change.isoformat(),
            "hours_slice_oil_change": round((datetime.now() - self.last_oil_change).total_seconds() / 3600, 1),
            "batch_count": len(self.batch_history),
            "total_burgers_fried": sum(b.quanity for b in self.batch_history),
            "sensor_status": self.temp_sensor.get_status()
        }
    
    def reset(self) -> bool:
        """
        Återställer fritösen till ursprungligt tillstånd

        Returns:
            bool: True om återställning lyckades
        """
        with self._lock:
            self.stop()
            time.sleep(2)

            # Återställ alla variabler
            self.status = FryingStatus.IDLE
            self.current_temperature = 20.0
            self.is_heating = False
            self.is_cooling = False
            self.safety_status = SafetyStatus.NORMAL
            self.active_batch = None
            self._integral = 0.0
            self._prev_error = 0.0

            # Starta om
            return self.start()
        
# Test och exempelanvändning
if __name__ == "__main__":
    # Exempel på hur man använder klassen
    from ...core.event_bus import EventBus

    # Skapa mock-konfiguration
    config = {
        "fryer": {
            "id": "test_fryer_01",
            "target_temperature": 175.0,
            "temp_tolerance": 2.0,
            "min_safe_temp": 160.0,
            "max_safe_temp": 190.0,
            "preheat_temp": 170.0,
            "max_capacity": 8,
            "max_oil_life": 72,
            "control_interval": 1.0,
            "monitor_interval": 0.5,
            "kp": 2.5,
            "ki": 0.1,
            "kd": 0.5
        }
    }

# Skapa event bus
event_bus = EventBus()

# Skapa fritöskontroller
fryer = FryerController(config, event_bus)

# Starta kontrollern
fryer.start()

try:
    # Testa förvärmning
    print("Startar förvärmning...")
    fryer.preheat()

    # Vänta på att fritösen blir redo
    time.sleep(30)

    # Testa fritösening
    print("Startar fritösbatch...")
    batch = fryer.start_frying(
        batch_id="test_batch_001",
        quantity=4,
        burger_type="cheeseburger",
        cooking_time=180 # 3 Minuter
    )

    if batch:
        print(f"Batch started: {batch.batch_id}")

        # Vänta på att batchen ska bli klar
        time.sleep(185)

    # visa status
    status = fryer.get_status()
    print(f"\nFritösstatus:")
    for key, value in status.items():
        print(f" {key}: {value}")

except KeyboardInterrupt:
    print("\nAvslutar test...")
finally:
    # Stäng av säkert
    fryer.stop()