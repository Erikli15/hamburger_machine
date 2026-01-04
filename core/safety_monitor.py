"""
Säkerhetsövervakning för hamburgarmaskinen.
Hantera nödstopp, Temperaturövervakning systemhälsa.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Set
import logging

from ..utils.logger import get_logger
from ..utils.config_lodaer import Configloader
from ..core.event_bus import EventBus, Eventtype

# Konfigurera logger
logger = get_logger(__name__)

class SafetyState(Enum):
    """Status för säkerhetssystemet."""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY_STOP = "emergency_stop"
    MAINTENANCE_MODE = "maintenance"

class SafetyEvent(Enum):
    """Typer av säkerhetshändelser."""
    TEMPERATURE_CRITICAL = "temperatur_critical"
    PRESSURE_HEIGH = "pressure_heigh"
    DOOR_OPEN = "door_open"
    MOTOR_STALLED = "motor_stalled"
    POWER_FAILURE = "power_failure"
    WATER_LEAK = "water_leak"
    FIRE_DETECTED = "fire_detected"
    EMERGENCY_STOP_PRESSED = "emergency_stop_pressed"
    SAFETY_LIMIT_EXCEEDED = "safety_limit_exceeded"

@dataclass
class SafetyThreshold:
    """Gränsvärden för säkerhetsövervakning."""
    min_temp: float = -40.0
    max_temp: float = 250.0
    max_current: float = 15.0 # Ampere
    max_pressure: float = 10.0 # Bar
    max_vibration: float = 5.0 # m/s²
    min_voltage: float = 200.0 # Volt
    max_voltage: float = 250.0 # Volt

@dataclass
class ComponentStatus:
    """Status för en maskinkomponent.""" 
    component_id: str
    enabled: bool = True
    last_check: float = field(default_factory=time.time)
    error_count: int = 0
    last_error: Optional[str] = None
    maintenace_due: bool = False

class SafetyMonitor:
    """
    Huvudklass för säkerhetsövervakning.
    Övervaka alla systemkomponenter och initierar nödåtgärder vid fel.
    """

    def __init__(self, event_bus: EventBus, config_path: str = "config_yaml"):
        """
        Initera säkerhetsövervakare.

        Args:
            event_bus: Händelsebuss för systemkommunikation
            config_path: Sökväg till konfigurationsfi
        """
        self.event_bus = event_bus 
        self.config = Configloader.load_config(config_path).get("safety", {})

        # Systemtillstånd
        self.state = SafetyState.NORMAL
        self.last_state_change = time.time()
        self.emergency_stop_active = False

        # Tröslelvärden
        self.thresholds = SafetyThreshold(
            min_temp=self.config.get("min_temperatur", -40.0),
            max_temp=self.config.get("max_temperatur", 250.0),
            max_current=self.config.get("max:current", 15.0),
            max_pressure=self.config.get("max_pressure", 10.0),
            max_vibration=self.config.get("max_vibration", 5.0),
            min_voltage=self.config.get("min_voltage", 200.0),
            max_voltage=self.config.get("max_voltage", 250.0)
        )

        # Komponentstatus
        self.components: Dict[str, ComponentStatus] = {}
        self.critical_components = {
            "fryer", "grill", "robot_arm", "conveyor", "payment_system"
        }

        # Övervakningsdata
        self.temperature_readings: Dict[str, List[float]] = {}
        self.current_readings: Dict[str, List[float]] = {}
        self.pressure_readings: Dict[str, List[float]] = {}

        # Callbacks för specifika händelser
        self.callbacks: Dict[SafetyEvent, List[Callable]] = {
            event: [] for event in SafetyEvent
        }

        # Övervakningsintervall
        self.monitoring_interval = self.config.get("monitoring_interval", 1.0)
        self.history_size = self.config.get("history_size", 100)

        # Initiera komponenter från konfig
        self._initialize_components()

        # Prestandamått
        self.metrics = {
            "safety_event": 0,
            "emergency_stops": 0,
            "warnings_issued": 0,
            "component_failures": 0
        }

        logger.info("Safety Monitor initialiserad")

    def _initialize_components(self):
        """Initiera alla maskinkomponenter från konfiguration."""
        components = self.config.get("components", {})
        for comp_id, comp_config in components.item():
            self.components[comp_id] = ComponentStatus(
                component_id=comp_id,
                enabled=comp_config.get("enabled", True)
            )

        logger.info(f"Initierade {len(self.components)} komponenter")

    async def start_monitoring(self):
        """
        Starta säkerhetsövervakning.
        Körs som asynkron uppgift.
        """
        logger.info("Startar säkerhetsövervakning...")

        try:
            while True:
                await self._monitoring_cycle()
                await asyncio.sleep(self.monitoring_interval)

        except asyncio.CancelledError:
            logger.info("Säkerhetsövervakning avbruten")
        except Exception as e:
            logger.error(f"Fel i säkerhetsövervakning: {e}")
            await self.trigger_emergency_stop(
                f"Övervakningsfel: {str(e)}"
            )
    
    async def _monitoring_cycle(self):
        """Utanför en övervakningscykel."""
        try:
            # Kontrollera temperaturer
            await self._check_temperatures()

            # Kontrollera elektriska parametrar
            await self._check_electrical_parameters()

            # Kontrollera mekaniska parametrar
            await self._check_mechanical_parameters()

            # Kontrollera komponentstatus
            await self._check_component_health()

            # Kontrollera säkerhetssensorer
            await self._check_safety_sensors()

        except Exception as e:
            logger.error(f"Fel i övervakningscykel: {e}")

    async def _check_temperatures(self):
        """Kontrollera temperaturer på alla värmeelement."""
        try:
            # Hämta temperature från händelsebuss
            temp_data = await self.event_bus.get_latest_event(
                Eventtype.TEMPERATURE_UPDATE
            )

            if not temp_data:
                return
            
            for component, temperature in temp_data.item():
                if temperature > self.thresholds.max_temp:
                    await self._handle_temperature_critical(
                        component, temperature
                    )
                elif temperature < self.thresholds.min_temp:
                    await self._handle_temperature_low(
                        component, temperature
                    )

                # Spara historik
                if component not in self.temperature_readings:
                    self.temperature_readings[component] = []

                self.temperature_readings[component].append(temperature)
                if len(self.temperature_readings[component]) > self.history_size:
                    self.temperature_readings[component].pop(0)

        except Exception as e:
            logger.error(f"Fel vid temperaturkontroll: {e}")

    async def _handle_temperature_critical(self, compoment: str, temp: float):
        """Hantera kritisk temperatur"""
        message = f"Kritisk temperatur på {compoment}: {temp}°C"
        logger.waening(message)

        # Skicka händelse
        await self.event_bus.publish(
            Eventtype.SAFETY_EVENT,
            {
                "event": SafetyEvent.TEMPERATURE_CRITICAL.name,
                "component": compoment,
                "temperature": temp,
                "threshold": self.thresholds.max_temp,
                "timestamp": time.time()
            }
        )

        # Aktivera kylning eller stäng av
        if compoment in ["fryer", "grill"]:
            await self._reduce_heating(compoment)

        # Uppdatera mått
        self.metrics["safety_events"] += 1

        # Kör callbacks
        await self._execute_callbacks(
            SafetyEvent.TEMPERATURE_CRITICAL,
            compoment=compoment,
            temperature=temp
        )

    async def _check_electrical_paramters(self):
        """Kontrollera elektriska parametrar som ström och spänning"""
        try:
            # Hämts el-data från händelsebuss
            electrical_data = await self.event_bus.get_latest_event(
                Eventtype.ELECTRICAL_UPDATE
            )

            if not electrical_data:
                return
            # Kontrollera ström
            current = electrical_data.get("current", 0)
            if current > self.thresholds.max_current:
                await self._handle_high_current(current)

            # Kontrollera spänning
            voltage = electrical_data.get("voltage", 0)
            if voltage < self.thresholds.min_voltage:
                await self._handle_low_voltage(voltage)
            elif voltage > self.thresholds.max_voltage:
                await self._handle_high_voltage(voltage)

        except Exception as e:
            logger.error(f"Fel vid elparameterkontroll: {e}")

    async def _check_component_health(self):
        """Kontrollera hälsostatus för alla komponenter."""
        for component_id, status in self.components.items():
            try:
                # Hämta komponentstatus
                comp_data = await self.event_bus.get_latest_event(
                    Eventtype.COMPONENT_STATUS
                )

                if comp_data and component_id in comp_data:
                    component_status = comp_data[component_id]

                    # Uppdatera status
                    if not component_status.get("operational", True):
                        status.error_count += 1
                        status.last_error = component_status.get("error", "Okänt fel")

                        if component_id in self.critical_components:
                            await self._handle_critical_component_failure(
                                component_id,
                                status.last_error
                            )
                    
                    status.last_check = time.time()

            except Exception as e:
                logger.error(f"Fel vid hälsokontroll för {component_id}: {e}")

    async def _check_safety_sensors(self):
        """Läs säkerhetssensorer (nödstopp, dörrar, brandlarm)."""
        try:
            safery_data = await self.event_bus.get_latest_event(
                Eventtype.SAFETY_SENSOR_UPDATE
            )

            if not safery_data:
                return
            
            # Kontrollera nödstopp
            if safery_data.get("emergency_stop", False):
                await self.trigger_emergency_stop("Nödstopp aktiverat")

            # Kontrollera dörrar
            if not safery_data.get("doors_closed", True):
                await self._handle_door_open()

            # Kontroööera brandlarm
            if safery_data.get("fire_detected", False):
                await self._handle_fire_detected()

            # Kontrollera vattemläckage
            if safery_data.get("water_leak", False):
                await self._handle_water_leak()
        
        except Exception as e:
            logger.error(f"Fel vid säkerhetssensorkontroll: {e}")

    async def trigger_emergency_stop(self, reason: str):
        """
        Initiera nödstopp

        Args:
            reason: Orsak till nödstopp
        """
        if self.emergency_stop_active:
            return
        
        logger.critical(f"NÖDSTOPP: {reason}")

        # Uppdatera tillstånd
        self.state = SafetyState.EMERGENCY_STOP
        self.emergency_stop_active = True
        self.last_state_change = time.time()
        self.metrics["emergency_stops"] += 1

        # Skicka nödstoppshändelse
        await self.event_bus.publish(
             Eventtype.EMERGENCY_STOP,
            {
                "reason": reason,
                "timestamp": time.time(),
                "initiator": "safety_monitor"
            }
        )

        # Stäng av alla aktiva komponenter
        await self._shutdown_all_components()

        # Aktivera nödsignaler
        await self._activate_emergency_signals()

        # Logga händelsem
        self._log_emergency_stop(reason)

    async def _shutdown_all_components(self):
        """Stäng av alla maskinkomponenter."""
        shutdown_commands = [
            (Eventtype.FRYER_CONTROL, {"command": "shutdown"}),
            (Eventtype.GRILL_CONTROL, {"command": "shutdown"}),
            (Eventtype.ROBOT_ARM_CONTROL, {"command": "stop"}),
            (Eventtype.CONVEYOR_CONTROL, {"command": "stop"})
        ]

        for event_type, command in shutdown_commands:
            try: 
                await self.event_bus.publish(event_type, command)
            except Exception as e:
                logger.error(f"Kunde inte skicka stängningskommando: {e}")

    async def _activate_emergency_signals(self):
        """Aktivera nödsignaler och larm"""
        try:
            # Aktivera visuella larm
            await self.event_bus.publish(
                Eventtype.VISUAL_ALARM,
                {"active": True, "pattern": "emergency"}
            )

            # Aktivera ljudlarm
            await self.event_bus.publish(
                Eventtype.AUDIO_ALARM,
                {"active": True, "tone": "emergency"}
            )

            # Skicka notis till admin
            await self.event_bus.publish(
                Eventtype.NOTIFICATION,
                {
                    "type": "emergency",
                    "message": "NÖDSTOPP AKTIVERAT - Maskinen stoppad",
                    "priority": "critical"
                }
            )

        except Exception as e:
            logger.error(f"Kunde inte aktivera nödsignaler: {e}")

    def _log_emergency_stop(self, reason: str):
        """Logga nödstopphändelse."""
        log_entry = {
            "timestamp": time.time(),
            "event": "emergency_stop",
            "reason": reason,
            "state": self.state.value,
            "metrics": self.metrics.copy()
        }

        # Skriv till loggfil
        logger.critical(f"EMERGENCY_STOP_LOG: {log_entry}")

        # Sicka till händelsebuss för datavasloggning
        asyncio.create_task(
            self.event_bus.publish(Eventtype.SYSTEM_LOG, log_entry)
        )

    async def reset_emergency_stop(self):
        """
        Återställ nödstopp efter manuell bekräftelse.
        Kräver att alla fel är åtgärdade.
        """
        if not self.emergency_stop_active:
            return
        
        logger.info(f"Återställer nödstopp...")

        # Kontrollera att alla fel är åtgärdade
        if not await self._varify_system_ready():
            logger.warning("Kan inte återställa - system inte klart")
            return
        
        # Återställ tillstånd
        self.emergency_stop_active = False
        self.state = SafetyState.NORMAL

        # Skicka återställningshändelse
        await self.event_bus.publish(
            Eventtype.EMERGENCY_RESET,
            {
                "timestamp": time.time(),
                "previous_state": SafetyState.EMERGENCY_STOP.value
            }
        )

        logger.info("NÖDSTOPP återställt")

    async def _verify_system_ready(self) -> bool:
        """Varifera att system är redo att starta efter nödstopp."""
        checks = [
            self._check_temperatures_safe(),
            self._check_safety_sensors_normal(),
            self._check_component_operational(),
        ]

        results = await asyncio.gather(*checks, return_exceptions=True)

        # Alla kontroller måste returnera True
        return all(r is True for r in results)
    
    async def _check_tempertatures_sefe(self) -> bool:
        """Kontrollera att temperaturer är inom säkra gränser."""
        try:
            temp_data = await self.event_bus.get_latest_event(
                Eventtype.TEMPERATURE_UPDATE
            )

            if not temp_data:
                return True
            
            for temp in temp_data.values():
                if temp > self.thresholds.max_temp - 10: # Marginal
                    return False
                
                return True
            
        except Exception:
            return False
        
    async def _check_safety_sensors_normal(self) -> bool:
        """Kontrollera att säkerhetsseneorer är i normalläge."""
        try:
            safety_data = self.event_bus.get_latest_event(
                Eventtype.SAFETY_SENSOR_UPDATE
            )

            if not safety_data:
                return True
            
            return all([
                not safety_data.get("emergency_stop", False),
                safety_data.get("doors_closed", True),
                not safety_data.get("fire_detected", False),
                not safety_data.get("water_leak", False)
            ])
        
        except Exception:
            return False
        
    async def _check_components_operational(self) -> bool:
        """Kontrollera att kritiska komponenter är operaktiva."""
        for component_id in self.critical_components:
            if component_id in self.components:
                status = self.components[component_id]
                if status.error_count > 0 and not status.enabled:
                    return False
                
        return True
    
    def register_callback(self, event: SafetyEvent, callback: Callable):
        """
        Registrera callback för säkerhetshändelse.

        Args:
            event: Typ av händelse
            callback: Funktion att anropa
        """
        if event in self.callbacks:
            self.callbacks[event].append(callback)
            logger.debug(f"Registreade callback för {event.name}")

    async def _execute_callbacks(self, event: SafetyEvent, **kwargs):
        """Exekvera alla registrerade callbacks för en händelse."""
        if event not in self.callbacks:
            return
        
        for callback in self.callbacks[event]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(**kwargs)
                else:
                    callback(**kwargs)
            except Exception as e:
                logger.error(f"Callback fel för {event.name}: {e}")

    async def _reduce_heating(self, component: str):
        """Reducerar värmen på en komponent."""
        try:
            if component == "fryer":
                await self.event_bus.publish(
                    Eventtype.FRYER_CONTROL,
                    {"commande": "reduce_power", "percentage": 50}
                )
            elif component == "grill":
                await self.event_bus.publish(
                    Eventtype.GRILL_CONTROL,
                    {"command": "reduce_temp", "degrees": 50}
                )
        except Exception as e:
            logger.error(f"Kunde inte reducera värme på {component}: {e}")

    async def _handle_high_current(self, current: float):
        """Hantera hög ström."""
        message = f"Hög ström: {current}A (max: {self.thresholds.max_current}A)"
        logger.warning(message)

        await self.event_bus.publish(
            Eventtype.SAFETY_EVENT,
            {
                "event": SafetyEvent.SAFETY_LIMIT_EXCEEDED.name,
                "parameter": "current",
                "value": current,
                "threshold": self.thresholds.max_current
            }
        )

    async def _handle_door_open(self):
        """Hantera öppna dörrar."""
        logger.warning("Säkerhetsdörr öppen")

        await self.event_bus.publish(
            Eventtype.SAFETY_EVENT,
            {
                "event": SafetyEvent.DOOR_OPEN.name,
                "timestamp": time.time()
            }
        )

        # Stoppa rörlifa delar
        await self.event_bus.publish(
            Eventtype.ROBOT_ARM_CONTROL,
            {"command": "pause"}
        )

    async def _handle_fire_detected(self):
        """Hantera branddetektering."""
        logger.critical("BRAND DETEKTERAD!")

        await self.event_bus.publish(
            Eventtype.SAFETY_EVENT,
            {
                "event": SafetyEvent.FIRE_DETECTED.name,
                "timestamp": time.time(),
                "serverity": "critical"
            }
        )

        # Aktivera brandsprinkler (om installerad)
        await self.event_bus.publish(
            Eventtype.FIRE_SUPPRESSION,
            {"activate": True}
        )

        # Trigger nödstopp
        await self.trigger_emergency_stop("Brand detekterad")

    async def _handle_water_leak(self):
        """Hantera vattenläckage detekterat"""
        logger.warning("Vattenläckage detekterat")

        await self.event_bus.publish(
            Eventtype.SAFETY_EVENT,
            {
                "event": SafetyEvent.WATER_LEAK.name,
                "timestamp": time.time()
            }
        )

        # Stäng av vattenförsörjning
        await self.event_bus.publish(
            Eventtype.WATER_CONTROL,
            {"valve": "close"}
        )

    async def _handle_high_pressure(self, pressure: float):
        """Hantera högt tryck."""
        logger.warning(f"Högt tryck: {pressure} bar")

        await self.event_bus.publish(
            Eventtype.SAFETY_EVENT,
            {
                "event": SafetyEvent.PRESSURE_HEIGH.name,
                "pressure": pressure,
                "threshold": self.thresholds.max_pressure
            }
        )

    async def _handle_critical_component_failure(self, component: str, error: str):
        """Hantera fel på kritisk komponent."""
        logger.error(f"Kritiskt fel på {component}: {error}")

        self.metrics["component_failures"] += 1

        # Inaktivera komponenten
        if component in self.components:
            self.components[component].enabled = False

        # Skicka notis
        await self.event_bus.publish(
            Eventtype.NOTIFICATION,
            {
                "type": "component_failure",
                "component": component,
                "error": error,
                "priority": "high"
            }
        )

    async def _handle_temperature_low(self, component: str, temp: float):
        """Hantera för låg temperatur."""
        logger.waning(f"Låg temperatur på {component}: {temp}°C")

    async def _handle_low_voltage(self, voltage: float):
        """Hantera låg spänning."""
        logger.warning(f"Låg spänning: {voltage}V")

    async def _handle_high_voltage(self, voltage: float):
        """Hantera hög spänning."""
        logger.warning(f"Hög spänning: {voltage}V")

    async def _handle_high_vibration(self, vibration: float):
        """Hantera hög vibration"""
        logger.warning(f"Hög vibration: {vibration} m/s²")

    def get_status(self) -> Dict:
        """
        Hämta aktuell status för säkerhetsststemet.

        Returns:
            Dictionary med statusinformation
        """
        return {
            "state": self.state.value,
            "emergebcy_stop_active": self.emergency_stop_active,
            "last_state_change": self.last_state_change,
            "components_operational": sum(1 for c in self.components.values() if c.enabled),
            "components_total": len(self.components),
            "metrics": self.metrics.copy(),
            "threshplds": {
                "max_temperature": self.thresholds.max_temp,
                "max_current": self.thresholds.max_current,
                "max_pressure": self.thresholds.max_pressure
            }
        }
    
    def get_component_status(self, component_id: str) -> Optional[Dict]:
        """
        Hämta status för specifik komponent.

        Args:
            component_id: Komponentens ID

        Returns:
            Komponentstatus eller None om inte finns
        """
        if component_id not in self.components:
            return None
        
        status = self.components[component_id]
        return {
            "component_id": status.component_id,
            "enbled": status.enabled,
            "error_count": status.error_count,
            "last_error": status.last_error,
            "last_check": status.last_check,
            "mainteance_due": status.maintenace_due,
            "critical": component_id in self.critical_components
        }
    
    def get_temperature_history(self, component: str) -> List[float]:
        """
        Hämta temperaturhistorik för komponent.

        Args:
            component: Komponents namn

        Returns:
            Lista med temperaturvärden
        """
        return self.temperature_readings.get(component, []).copy()
    
    def set_maintenance_mode(self, enabled: bool):
        """
        Aktivera/inaktivera underhållsläge.

        Args:
            enabled: True för underhållsläge
        """
        if enabled:
            self.state = SafetyState.MAINTENANCE_MODE
            logger.info("Underhållsläge aktiverat")
        elif self.state == SafetyState.MAINTENANCE_MODE:
            self.state = SafetyState.NORMAL
            logger.info("Underhållsläge inaktiverat")

    def is_system_operational(self) -> bool:
        """
        Kontrollera om systemet är operationellt.

        Returns:
            True om systemet kan köras
        """
        return (
            not self.emergency_stop_active and
            self.state in [SafetyState.NORMAL, SafetyState.WARNING] and
            all(c.enabled for c in self.critical_components)
        )
    
# Singletion-instans för enkel åtkomst
_safety_monitor_instance = None

def get_safety_monitor(event_bus: EventBus = None, config_path: str = None) -> SafetyMonitor:
    """
    Hämta eller skapa SafetyMonitor-instans (singleton).

    Args:
        event_bus: Händelsebuss (krävs vid första anrop)
        config_path: Sökväg till konfig

    Returns:
        SafetyMonitor-instance
    """
    global _safety_monitor_instance

    if _safety_monitor_instance is None:
        if event_bus is None:
            raise ValueError("event_bus krävs för att skapa första instans")
        
        _safety_monitor_instance = SafetyMonitor(
            event_bus=event_bus,
            config_path=config_path or "config.yaml"
        )

    return _safety_monitor_instance

async def main():
    """Testkör säkerhetsövervakaren"""
    from ..core.event_bus import EventBus

    # Skapa test-händelsebuss
    event_bus = EventBus()

    # Skapa säkerhetsövervakare
    monitor = SafetyMonitor(event_bus)

    # Starta övervakning
    monitoring_task = asyncio.create_task(monitor.start_monitoring())

    try:
        # Kör i 30 sekunder för test
        await asyncio.sleep(30)

    except KeyboardInterrupt:
        print("\nAvbryter...")

    finally:
        # Stopa övervakning
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    asyncio.run(main())