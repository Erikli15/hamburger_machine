"""
Temperaturenssor Manager för Hamburger Maskinen
Hanterar läsning och övervakning av alla temperatursensorer i systemet
"""

import time
import threading
import random
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class SensorType(Enum):
    """Typer av temperatursensorer i systemet"""
    FRITOS = "fritös"
    GRILL = "grill"
    FREEZER = "freezer"
    AMBIENT = "ambient"
    COOLING = "cooling_system"

class SensorStatus(Enum):
    """Status för em sensor"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAULTY = "faulty"
    CALIBRATTING = "calibrating"

@dataclass
class TemperatureReading:
    """Dataklass för en temperaturavläsning"""
    sensor_id: str
    temperature: float
    timestamp: float
    unit: str = "C"
    accuracy: float = 0.5 # ± grader C

    def to_dict(self) -> Dict:
        """Konventera till dictionary"""
        return {
            "sensor_id": self.sensor_id,
            "temperature": self.temperature,
            "timestamp": self.timestamp,
            "unit": self.unit,
            "accuracy": self.accuracy
        }
    
@dataclass
class SensorConfig:
    """Konfiguration för en sensor"""
    sensor_id: str
    sensor_type: SensorType
    location: str
    min_temp: float
    max_temp: float
    warning_threshold: float = 5.0 # grader från gräns för varning
    polling_interval: float = 1.0 # sekunder
    calibration_offset: float = 0.0

class TemperaturSensor:
    """Abstraktion för en enskild temperatursensor"""

    def __init__(self, comfig: SensorConfig, simulator: bool = True):
        self.config = comfig
        self.simulator = simulator
        self.status = SensorStatus.INACTIVE
        self.last_reading: Optional[TemperatureReading] = None
        self.calibration_history: List[float] = []

        # Simulerade värden (används när simulator=True)
        self._simulated_temp = (comfig.min_temp + comfig.max_temp) / 2
        self._simulated_drift = 0.0

        logger.info(f"Initierad sensor: {comfig.sensor_id} ({comfig.sensor_type.value})")

    def read_temperature(self) -> TemperatureReading:
        """Läs temperatur från sensorn"""
        try:
            if self.simulator:
                temperature = self._read_simulated()
            else:
                temperature = self._read_physical()

            reading = TemperatureReading(
                sensor_id=self.config.sensor_id,
                temperature=temperature,
                timestamp=time.time(),
                accuracy=self.config.calibration_offset
            )        

            self.last_reading = reading
            self.status = SensorStatus.ACTIVE

            # Kontrollera om temperaturen är inom acceptabla gränser
            self._check_thresholds(temperature)

            return reading
        
        except Exception as e:
            logger.error(f"Fel vid läsning av sensor {self.config.sensor_id}: {e}")
            self.status = SensorStatus.FAULTY
            raise

    def _read_simulated(self) -> float:
        """Simulerad temperaturläsning med lite vaiation"""
        # Lägg till lite naturlig variation
        variation = random.uniform(-0.5, 0.5)

        # Simulera drift över tid
        self._simulated_drift += random.uniform(-0.1, 0.1)
        self._simulated_drift = max(min(self._simulated_drift, 2.0), -2.0)

        # Beräkna temperatur
        base_temp = self._simulated_temp
        if self.config.sensor_type == SensorType.FRITOS:
            base_temp = 175.0 # Standard fritöstemp
        elif self.config.sensor_type == SensorType.GRILL:
            base_temp = 200.0 # Standard grilltemp
        elif self.config.sensor_type == SensorType.FREEZER:
            base_temp = -18.0 # Standard frysvärde

        temp = base_temp + variation + self._simulated_drift

        # Säkerställ att vi är inom realistiska gränser
        return max(self.config.min_temp, min(self.config.max_temp, temp))
    
    def _read_physical(self) -> float:
        """Läs från fysisk sensor (placeholder - implementera för riktig hårdvara)"""
        # Här skulle du integrera med riktiga sensorer via GPIO, I2C, SPI, etc.
        # Exempel för DS18B20 (OneWire):
        # with open(f"/sys/bus/w1/devices/{sensor_id}/w1_slave", "r") as f:
        #       data = f.read()
        #       temp = float(data.split("t=")[-1]) / 1000.0

        raise NotImplementedError("Fysisk sensorläsning kräver hårdvaruimplementering")
    

    def _chek_thresholds(self, temperature:float):
        """Kontrollera om temperaturen är utanför acceptabla gränser"""
        if temperature < self.config.min_temp + self.config.warning_threshold:
            logger.warning(f"Sensor {self.config.sensor_id}: Låg temperature: {temperature:.1f}°C" f"(min: {self.config.min_temp}°C)")
        elif temperature > self.config.max_temp - self.config.warning_threshold:
            logger.warning(f"Sensor {self.config.sensor_id}: Hög temperatur: {temperature:.1f}°C" f"max: {self.config.max_temp}°C")

    def calibrate(self, referenc_temp: float) -> float:
        """Kalibrera sensorn mot en referenstemperatur"""
        logger.info(f"Startar kalibrering av {self.config.sensor_id}")
        self.status = SensorStatus.CALIBRATTING

        try:
            # Ta fler mätningar
            readings = []
            for _ in range(10):
                reading = self.read_temperature()
                readings.append(reading.temperature)
                time.sleep(0.1)

            avg_reading = sum(readings) / len(readings)
            offset = referenc_temp - avg_reading

            # Uppdatera kalibreringsoffset
            self.config.calibration_offset = offset
            self.calibration_history.append(offset)

            logger.info(f"Kalibrering klar för {self.config.sensor_id}:" f"offset = {offset:.2f}°C")

            self.status = SensorStatus.ACTIVE
            return offset 

        except Exception as e:
            logger.error(f"Kalibrering misslyckades för {self.config.sensor_id}: {e}")
            self.status = SensorStatus.FAULTY
            raise

    def get_status(self) -> Dict:
        """Hämta sensorstatus"""
        return {
            "sensor_id": self.config.sensor_id,
            "type": self.config.sensor_type.value,
            "status": self.status.value,
            "location": self.config.location,
            "last_reading": self.last_reading.to_dict() if self.last_reading else None,
            "calibration_offset": self.config.calibration_offset,
            "temperature_limits": {
            "min": self.config.min_temp,
            "max": self.config.max_temp
            }
        }   
    
class SensorManager:
    """Hanterar alla temperatursensorer i systemet"""

    def __init__(self, config_file: Optional[str] = None):
        self.sensors: Dict[str, TemperaturSensor] = {}
        self.sensor_configs: Dict[str, SensorConfig] = {}
        self.monitoring_thread: Optional[threading.Thread] = None
        self.is_monitoring = False
        self.callbacks: List[callable[[TemperatureReading], None]] = []
        self.alert_callbacks: List[Callable[[str, str], None]] = []

        # Lägg till standardkonfigurationer
        self._load_default_configs()

        if config_file:
            self._load_config_from_file(config_file)

        logger.info("SensorManager initierad")

    def _load_default_configs(self):
        """Lägg till standardsensorer"""
        default_configs =  [
            SensorConfig(
                sensor_id="fritos_1",
                sensor_type=SensorType.FRITOS,
                location="fritös_framsida",
                min_temp=150.0,
                max_temp=190.0,
                warning_threshold=5.0
            ),
            SensorConfig(
                sensor_id="fritos_1",
                sensor_type=SensorType.FRITOS,
                location="fritös_baksida",
                min_temp=150.0,
                max_temp=190.0,
                warning_threshold=5.0
            ),
            SensorConfig(
                sensor_id="grill_1",
                sensor_type=SensorType.GRILL,
                location="grill_ovan",
                min_temp=180.0,
                max_temp=250.0,
                warning_threshold=10.0
            ),
            SensorConfig(
                sensor_id="grill_2",
                sensor_type=SensorType.GRILL,
                location="grill_undner",
                min_temp=180.0,
                max_temp=250.0,
                warning_threshold=10.0
            ),
            SensorConfig(
                sensor_id="freezer_1",
                sensor_type=SensorType.FREEZER,
                location="frysfack_höger",
                min_temp=-25.0,
                max_temp=-15.0,
                warning_threshold=3.0
            ),
            SensorConfig(
                sensor_id="freezer_2",
                sensor_type=SensorType.FREEZER,
                location="frysfack_vänster",
                min_temp=-25.0,
                max_temp=-15.0,
                warning_threshold=3.0
            ),
            SensorConfig(
                sensor_id="ambient_1",
                location="maskin_innanför",
                min_temp=15.0,
                max_temp=45.0,
                warning_threshold=5.0
            )
        ]

        for config in default_configs:
            self.add_sensor(config)

    def _load_config_from_file(self, config_file: str):
        """Läs sensorer från konfigurationsfil (placeholder)"""
        # Implementera läsning från YAML/JSON fil
        pass

    def add_sensor(self, config: SensorConfig, simulator: bool = True):
        """Lägg till en ny sensor"""
        sensor = TemperaturSensor(config, simulator)
        self.sensors[config.sensor_id] = sensor
        self.sensor_configs[config.sensor_id] = config

        logger.info(f"Sensor tillagd: {config.sensor_id} på {config.location}")

    def remove_sensor(self, sensor_id: str):
        """Ta bort en sensor"""
        if sensor_id in self.sensors:
            del self.sensors[sensor_id]
            del self.sensor_configs[sensor_id]
            logger.info(f"Sensor borttagen: {sensor_id}")

    def read_sensor(self, sensor_id: str) -> Optional[TemperatureReading]:
        """Läs temperatur från specifik sensor"""
        if sensor_id not in self.sensors:
            logger.error(f"Sensor {sensor_id} finns inte")
            return None
        
        try:
            return self.sensors[sensor_id].read_temperature()
        except Exception as e:
            logger.error(f"Kunde inte läsa sensor {sensor_id}: {e}")
            return None
        
    def read_all_sensors(self) -> Dict[str, TemperatureReading]:
        """Läs temperatur från alla sensorer"""
        readings = {}

        for sensor_id, sensor in self.sensors.items():
            try:
                readings[sensor_id] = sensor.read_temperature()
            except Exception as e:
                logger.error(f"Misslyckades att läsa {sensor_id}: {e}")
                readings[sensor_id] = None

        return readings
    
    def start_monitoring(self, interval: float = 2.0):
        """Starta bakgrundsövervakning av alla sensorer"""
        if self.is_monitoring:
            logger.warning("Övervakning är redan igång")
            return
        
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval,),
            daemon=True
        )
        self.monitoring_thread.start()

        logger.info(f"Startade temperatursensorövervakning (intervall: {interval}s)")

    def stop_monitoring(self):
        """Stoppa bakgrundsövervakning"""
        self.is_monitoring = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5.0)

        logger.info("Stoppade temperatursensorövervakning")

    def _monitoring_loop(self, interval: float):
        """Bakgrundstråd för kontinuerlig övervakning"""
        while self.is_monitoring:
            try:
                readings = self.read_all_sensors()

                # Anropa callbacks för varje avläsning
                for sensor_id, reading in readings.items():
                    if reading:
                        for callback in self.callbacks:
                            try:
                                callback(reading)
                            except Exception as e:
                                logger.error(f"Callback fel för {sensor_id}: {e}")

                    # Kontrollera avvikelser
                    self._check_for_alerts(readings)
            except Exception as e:
                logger.error(f"Fel i övervakningsloop: {e}")

            time.sleep(interval)

    def _check_for_alerts(self, readings: Dict[str, Optional[TemperatureReading]]):
        """Kontrollera avikelser och skicka varningar"""
        for sensor_id, reading in readings.items():
            if not reading:
                continue

            sensor = self.sensors.get(sensor_id)
            if not sensor:
                continue

            config = sensor.config
            temp = reading.temperature

            # Kontrollera kritiska gränser
            if temp <= config.min_temp or temp >= config.max_temp:
                alert_msg = (
                    f"KRITISKT: Sensor {sensor_id} har temperatur {temp:.1f}°C"
                    f"utanför gränserna ({config.min_temp}-{config.max_temp}°C)"
                )
                logger.critical(alert_msg)
                self._trigger_alert(sensor_id, alert_msg)

            # Kontrollera varningsgränser
            elif (temp <= config.min_temp + config.warning_threshold or
                  temp >= config.max_temp - config.warning_threshold):
                warning_msg = (
                    f"VARNING: Sensor {sensor_id} nära gränsvärde: {temp:.1f}°C"
                )
                logger.warning(warning_msg)
                self._trigger_alert(sensor_id, warning_msg)

    def _trigger_alert(self, sensor_id: str, message: str):
        """Utlös alert via calbacks"""
        for callback in self.alert_callbacks:
            try:
                callback(sensor_id, message)
            except Exception as e:
                logger.error(f"Alert callback fel: {e}")

    def register_callback(self, callback: Callable[[str, str], None]):
        """Registrera callback för varningar"""
        self.alert_callbacks.append(callback)

    def calibrate_sensor(self, sensor_id: str, referensce_temp: float) -> Optional[float]:
        """Kalibrera en specifik sensor"""
        if sensor_id not in self.sensors:
            logger.error(f"Sensor {sensor_id} finns inte")
            return None

        try:
            offset = self.sensors[sensor_id].calibrate(referensce_temp)
            return offset
        except Exception as e:
            logger.error(f"Kalibrering misslyckades för {sensor_id}: {e}")
            return None

    def get_sensor_status(self, sensor_id: str) -> Optional[Dict]:
        """Hämta status för specifik sensor"""
        if sensor_id not in self.sensors:
            return None
        
        return self.sensors[sensor_id].get_status()
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Hämta status för alla sensorer"""
        status = {}
        for sensor_id in self.sensors:
            status[sensor_id] = self.get_all_status(sensor_id)
        return status
    
    def get_temperature_summary(self) -> Dict:
        """Hämta sammanfattning av alla temperaturer"""
        readings = self.read_all_sensors()

        summary = {
            "timestamp": time.time(),
            "sensors": {},
            "averages": {},
            "alerts": []
        }

        # Gruppera per sensortyp
        type_totals = {}
        type_counts = {}

        for sensor_id, reading in readings.items():
            if reading:
                sensor = self.sensors[sensor_id]
                sensor_type = sensor.config.sensor_type.value

                # Lägg till sensordata
                summary["sensors"][sensor_id] = reading.to_dict()

                # Beräkna genomsnitt per typ
                if sensor_type not in type_totals:
                    type_totals[sensor_type] = 0.0
                    type_counts[sensor_type] = 0

                type_totals[sensor_type] += reading.temperature
                type_counts[sensor_type] += 1

            # Beräkna genomsnitt
            for sensor_type, total in type_totals.items():
                count = type_counts[sensor_type]
                summary["averages"][sensor_type] = total / count

            return summary

# Exempel på användning
if __name__ == "__main__":
    # Konfigurera loggning
    logging.basicConfig(level=logging.INFO)

    # Skapa sensormanager
    manager = SensorManager()

    # Lägg till callback för temperaturuppdateringar
    def handle_temperature_update(reading: TemperatureReading):
        print(f"Uppdatering: {reading.sensor_id} = {reading.temperature:.1f}°C")

    manager.register_callback(handle_temperature_update)

    # Lägg till callback för varningar
    def handle_alert(sensor_id: str, message: str):
        print(f"ALERT [{sensor_id}]: {message}")

    manager.register_alert_callback(handle_alert)

    # Starta övervakning
    manager.start_monitoring(interval=1.0)

    try:
        # Kör i 30 sekunder för demonstration
        print("Startar temperaturövervakning i 30 sekunder...")
        print("Tryck Ctrl+C för att avsluta\n")

        time.sleep(30)

    except KeyboardInterrupt:
        print("\nAvslutar...")
    finally:
        manager.stop_monitoring()

        # Visa sammafattning
        summary = manager.get_temperature_summary()
        print("\nTemperatursammanfattning:")
        print(f"Antal sensorer: {len(summary["sensors"])}")

        for sensor_type, avg_temp in summary["averages"].item():
            print(f"{sensor_type}: {avg_temp:.1f}°C")
     