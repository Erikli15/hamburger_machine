"""
API för externa sensorer och övervakningssystem.
Integrerar med yttre miljöövervakning, fjärrövervakning och externa säkerhetssystem.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import aiohttp
from pydantic import BaseModel, Field
import requests
from tenacity import retry, stop_after_attempt, wait_exponental

from utils.logger import setup_logger
from utils.config_loader import ConfigLoader

# Logging setup
logger = setup_logger(__name__)

class SensorType(Enum):
    """Typer av externa sensorer."""
    ENVIRONMENT_TEMPERATURE = "environment_temperature"
    HUMIDITY = "humidity"
    AIR_QUALITY = "air_quality"
    POWER_CONSUMPTION = "power_consumption"
    WATER_QUALITY = "water_quality"
    FIRE_ALARM = "fire_alarm"
    INSTRUSION_DETECTION = "instrusion_detection"
    CO2_LEVEL = "co2_level"
    NOISE_LEVEL = "noise_level"
    REFERIGERANT_LEAK = "referigerant_leak"

class SensorStatus(Enum):
    """Status för externa sensorer."""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    ALARM = "alarm"
    MAINTENANCE = "maintenance"

@dataclass
class SensorReading:
    """Dataklass för sensoravläsningar."""
    sensor_id: str
    sensor_type: SensorType
    value: float
    unit: str
    timestamp: datetime
    location: str
    status: SensorStatus = SensorStatus.ONLINE
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ExternalSensorConfig(BaseModel):
    """Konfiguration för externa sensorer."""
    enbled: bool = Field(default=False, description="Aktivera/inaktiverad")
    api_endpoint: Optional[str] = Field(None, description="API nyckel")
    api_key: Optional[str] = Field(None, description="API nyckel")
    poll_interval: int = Field(default=30, ge=5, description="Avläsningsintervall i sekunder")
    timeout: int = Field(default=10, description="Antal försök vid fel")

    class Config:
        env_prefix = "EXTERNAL_SENSOR_"

class ExteralSensorBase(ABC):
    """Abstrakt basklass externa sensorer."""

    def __init__(self, sensor_id: str, config: ExternalSensorConfig):
        self.sensor_id = sensor_id
        self.config = config
        self.last_reading: Optional[SensorReading] = None
        self.status: SensorStatus = SensorStatus.OFFLINE
        self.error_count: int = 0
        self.max_errors: int = 5

    @abstractmethod
    async def read_sensor(self) -> Optional[SensorReading]:
        """Läs sensorvärde asynkront."""
        pass

    @abstractmethod
    def update_status(self, success: bool):
        """Uppdatera sensorstatus."""
        if success:
            self.error_count = 0
            self.status = SensorStatus.ONLINE
        else:
            self.error_count += 1
            if self.status >= self.max_errors:
                self.status = SensorStatus.OFFLINE
            else:
                self.status = SensorStatus.DEGRADED

class RESTAPISensor(ExteralSensorBase):
    """Sensor som kommunicerar via REST API."""

    def __init__(self, sensor_id: str, config: ExternalSensorConfig, sensor_type: SensorType, location: str):
        super().__init__(sensor_id, config)
        self.sensor_type = sensor_type
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            headers={"Autorization": f"Bearer {self.config.api_key}"}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponental(multiplier=1, min=2, max=10)
    )
    async def read_sensor(self) -> Optional[SensorReading]:
        """Läs sensor via REST API."""
        if not self.config.enabled or not self.config.api_endpoint:
            logger.warning(f"Sensor {self.sensor_id} är inaktiverad eller saknar endpoint")
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.config.api_endpoint,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    timeout=self.config.timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        reading = self._parse_response(data)
                        if reading and self.validate_reading(reading):
                            self.last_reading = reading
                            self.update_status(True)
                            return reading
                        else:
                            logger.error(f"API fel för sensor {self.sensor_id}: {response.status}")
                            self.update_status(False)

        except asyncio.Timeout:
            logger.error(f"Timeout för sensor {self.sensor_id}")
            self.update_status(False)
        except Exception as e:
            logger.error(f"Fel vid läsning av sensor {self.sensor_id}: {e}")
            self.update_status(False)

        return None

    def _parse_response(self, data: Dict) -> Optional[SensorReading]:
        """Parsa API-svar till SensorReading."""
        try:
            # Anpassa denna method baserat på API:ets specifika format
            value = data.get("value", data.get("reading", 0.0))
            unit = data.get("unit", "")
            timeatamp_str = data.get("timestamp")
            timestamp = datetime.fromisoformat(timeatamp_str) if timeatamp_str else datetime.now()

            return SensorReading(
                sensor_id=self.sensor_id,
                sensor_type=self.sensor_type,
                value=float(value),
                unit=unit,
                timestamp=timestamp,
                location=self.location,
                metadata=data
            )
        except Exception as e:
            logger.error(f"Fel vid parsing av API-svar för {self.sensor_id}: {e}")
            return None
        
    def validete_reading(self, reading: SensorReading) -> bool:
        """Validera sensprläsning."""
        # Grundläggande validering
        if reading.value is None:
            return False
        
        # Typ-specifik validering
        if self.sensor_type == SensorType.ENVIRONMENT_TEMPERATURE:
            return -50 <= reading.value <= 100 # Celsius
        elif self.sensor_type == SensorType.HUMIDITY:
            return 0 <= reading.value <= 100 # Procent
        elif self.sensor_type == SensorType.CO2_LEVEL:
            return 0 <= reading.value <= 5000 #PPM
        elif self.sensor_type == SensorType.AIR_QUALITY:
            return 0 <= reading.value <= 500 # AQI
        
        return True
    
class MQTTSensor(ExteralSensorBase):
    """Sensor som anvnder MQTT för kommunikation."""

    def __init__(self, sensor_id: str, config: ExternalSensorConfig, sensor_type: SensorType, location: str, topic: str):
        super().__init__(sensor_id, config)
        self.sensor_type = sensor_type
        self.location = location
        self.topic = topic
        self.callback: Optional[Callable] = None

    async def read_sensor(self) -> Optional[SensorReading]:
        """MQTT-sensorer använder push, inte pull."""
        # Returnera senaste läsning eller vänta på ny
        return self.last_reading
    
    def process_message(self, message: Dict):
        """Processa inkommande MQTT-meddelande."""
        try:
            reading = SensorReading(
                sensor_id=self.sensor_id,
                sensor_type=self.sensor_type,
                value=float(message.get("value", 0)),
                unit=message.get("unit", ""),
                timestamp=datetime.fromisoformat(message.get("timestamp", datetime.now().isoformat())),
                location=self.location,
                metadata=message
            )

            if self.validate_reading(reading):
                self.last_reading = reading
                self.update_status(True)

                # Anropa callbacke om satt
                if self.callback:
                    self.callback(reading)

        except Exception as e:
            logger.error(f"Fel vid processing av MQTT-meddelande för {self.sensor_id}: {e}")
            self.update_status(False)

    def validete_reading(self, reading: SensorReading) -> bool:
        """Validera MQTT-sensoravläsning."""
        # Länkande validering som REST-sensorer
        return reading.value is None
    
class ExternalSensorManager:
    """Hantera alla externa sensorer."""

    def __init__(self):
        self.config = ConfigLoader().load_sensor_config()
        self.sensors: Dict[str, ExteralSensorBase] = {}
        self.reading_callbacks: List[Callable[[SensorReading], None]] = []
        self._running = False
        self._poll_tasks: Dict[str, asyncio.Task] = {}

    def initialize_sensors(self):
        """Initiera alla konfigurerade sensorer."""
        sensor_configs = self.config.get("sensors", {})

        for sensor_id, sensor_configs in sensor_configs.items():
            config = ExternalSensorConfig(**sensor_configs.get("config", {}))

            if not config.enabled:
                logger.info(f"Sensor {sensor_id} är inaktiverad")
                continue

            sensor_type = SensorType(sensor_configs.get("type"))
            location = sensor_configs.get("location", "unknown")
            portcol = sensor_configs.get("portcol", "rest")

            if portcol == "rest":
                sensor = RESTAPISensor(
                    sensor_id=sensor_id,
                    config=config,
                    sensor_type=sensor_type,
                    location=location
                )
            elif portcol == "mqtt":
                topic = sensor_type.get("topic", f"sensors/{sensor_id}")
                sensor = MQTTSensor(
                    sensor_id=sensor_id,
                    config=config,
                    sensor_type=sensor_type,
                    location=location,
                    topic=topic
                )
            else:
                logger.error(f"Okänt protokoll för sensor {sensor_id}: {portcol}")
                continue

            self.sensors[sensor_id] = sensor
            logger.info(f"Initialiserad sensor: {sensor_id} ({sensor_type.value})")

    async def start_monitoring(self):
        """Starta övervakning av alla sensorer."""
        self._running = True

        # Starta pallade sensorer
        for sensor_id, sensor in self.sensors.items():
            if isinstance(sensor, RESTAPISensor):
                task = asyncio.create_task(
                    self._poll_sensor(sensor_id, sensor)
                )
                self._poll_tasks[sensor_id] = task

        logger.info(f"Startade övervakning av {len(self._poll_tasks)} sensorer")

    async def stop_monitoring(self):
        """Stoppa övervakning."""
        self._running = False

        # Avbryt alla polling tasks
        for task in self._poll_tasks.values():
            task.cancel()

        await asyncio.gather(*self._poll_tasks.values(), return_exceptions=True)
        self._poll_tasks.clear()

        logger.info("Stoppade sensorövervakning")

    async def _poll_sensor(self, sensor_id: str, sensor: RESTAPISensor):
        """Poll en sensor med givet intervall."""
        while self._running:
            try:
                reading = await sensor.read_sensor()

                if reading:
                    # Notifiera alla callbacks
                    for callback in self.reading_callbacks:
                        try:
                            callback(reading)
                        except Exception as e:
                            logger.error(f"Callback fel för sensor {sensor_id}: {e}")

                    # Logga viktiga avvikelser
                    self._check_alarma(reading)

                # Vänta till nästa avläsning
                await asyncio.sleep(sensor.config.poll_interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Fel i polling för sensor {sensor_id}: {e}")
                await asyncio.sleep(5) # Kort väntan vid fel

    def _check_alarms(self, reading: SensorReading):
        """Kontrollera om avläsning utlöser larm."""
        alarm_rules = self.config.get("alarm_rules", {}).get(reading.sensor_type.value, {})

        if not alarm_rules:
            return
        
        min_val = alarm_rules.get("min")
        max_val = alarm_rules.get("max")

        alarm_triggered = False
        alarm_message = ""

        if min_val is not None and reading.value < min_val:
            alarm_triggered = True
            alarm_message = f"{reading.sensor_type.value} under minimum: {reading.value} {reading.unit}"
        elif max_val is not None and reading.value > max_val:
            alarm_triggered = True
            alarm_message = f"{reading.sensor_type.value} över maximum: {reading.value} {reading.unit}"

        if alarm_triggered:
            logger.warning(f"ALARM: {alarm_message}")
            self._trigger_alarm(reading, alarm_message)

    def _trigger_alarm(self, reading: SensorReading, message: str):
        """Utlös larm vid kritiska värden."""
        # Skicka tll händelsebuss
        from core.event_bus import EventBus
        event_bus = EventBus.get_instance()

        event_bus.publish(
            event_bus="sensor_alarm",
            data={
                "sensor_id": reading.sensor_id,
                "sensor_type": reading.sensor_type.value,
                "value": reading.value,
                "unit": reading.unit,
                "location": reading.location,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
        )

    def register_callback(self, callback: Callable[[SensorReading], None]):
        """Registrera callback för nya sensoravläsningar."""
        self.reading_callbacks.append(callback)

    def get_sensor_status(self) -> Dict[str, Dict]:
        """Hamta status för alla sensorer."""
        status = {}
        for sensor_id, sensor in self.sensors.items():
            status[sensor_id] = {
                "type": sensor.sensor_type.value if hasattr(sensor, "sensor_type") else "unknown",
                "status": sensor.status.value,
                "last_reading": sensor.last_reading.value if sensor.last_reading else None,
                "location": sensor.location if hasattr(sensor, "location") else "unknown",
                "error_count": sensor.error_count
            }
        return status
    
    def get_sensor_reading(self, sensor_id: str) -> Optional[SensorReading]:
        """Hämta senasete avläsning för specifika sensor."""
        sensor = self.sensors.get(sensor_id)
        return sensor.last_reading if sensor else None
    
# Factory-funktion för att skapa sensorer
def crate_sensor(sensor_type: str, config: [Dict]) -> Optional[ExteralSensorBase]:
    """Factory för att skapa sensorinstanser."""
    sensor_classes = {
        "rest": RESTAPISensor,
        "mqtt": MQTTSensor,
    }

    sensor_class = sensor_classes.get(sensor_type)
    if not sensor_class:
        logger.error(f"Okänd sensortyp: {sensor_type}")
        return None
    
    try:
        return sensor_class(**config)
    except Exception as e:
        logger.error(f"Fel vid skappade av sensor: {e}")
        return None
    
# Snabbastart för test
async def main():
    """Testfunktion för externa sensorer."""
    manager = ExternalSensorManager()
    manager.initialize_sensors()

    # Exempel på callback
    async def print_reading(reading: SensorReading):
        print(f"[{reading.timestamp}] {reading.sensor_id}: {reading.value} {reading.unit}")

        manager.register_callback(print_reading)

        try:
            await manager.start_monitoring()
            await asyncio.sleep(60) # Kör i 60 sekunder
        finally:
            await manager.stop_monitoring()

if __name__ == "__main__":
    asyncio.run(main())

