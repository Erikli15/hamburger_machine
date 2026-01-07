"""
Freezer Controller Module

Hanterar temperaturreglering och övervakning av frysfack för ingredienser.
"""

import time
import threading
from typing import Optional, Dict, Callable
from enum import Enum
from dataclasses import dataclass
import logging

from ...utils.logger import setup_logger
from ...utils.validators import validate_temperature_range

# Konfigura logger
logger = setup_logger(__name__)

class FreezerState(Enum):
    """Tillstånd för frysfacket"""
    IDLE = "inaktiv"
    COOLING = "kylande"
    DEFROSTING = "avfrostning"
    ERROR = "fel"
    MAINTENANCE = "underhåll"

@dataclass
class FreezerConfig:
    """Konfiguration för frysfacket"""
    target_temperature: float = -18.0 # Standard mål-temperatur
    tolerance: float = 2.0 # Tillåtem avvikelse
    min_temperature: float = -25.0 # Lägsta tillåtna temperatur
    max_temperature: float = -15.0
    defrost_interval_hours: int = 24 # Avfrostningsintervall
    defrost_duration_minutes: int = 20 # Avfrostningstid
    compressor_cooldown_seconds: int = 300 # Kompressorväntetid

class FreezerController:
    """Kontrollerklass för frysfacket"""

    def __init__(self,
                 sensor_manager,
                 config: Optional[FreezerConfig] = None,
                 freezer_id: str = "freezer_1"
                 ):
        """
        Initiera frysfackskontroll.

        Args:
            sensor_manager: Temperatursensorhanterare
            config: Fryscakskonfiguration
            freezer_id: Unik ID för frysfacket
        """
        self.freezer_id = freezer_id
        self.sesor_manager = sensor_manager
        self.config = config or FreezerConfig()

        # Initiala tillstånd
        self.state = FreezerState.IDLE
        self.current_temperature = None
        self.compressor_on = False
        self.defrost_heater_on = False
        self.last_defrost_time = time.time()

        # Trådhantering
        self.control_thread = None
        self.running = False
        self.lock = threading.Lock()

        # Event callbacks
        self.on_temperature_change = None
        self.on_state_change = None
        self.on_error = None

        # Statistikk
        self.start_time = time.time()
        self.compressor_runtime = 0
        self.energy_consumption_kwh = 0
        self.temperature_history = []

        # Säkerhetsvariabler
        self.error_count = 0
        self.max_errors = 5

        logger.info(f"Freezer controller {freezer_id} initialized")

    def start(self) -> bool:
        """
        Starta temperaturregleringstråden.

        Returns:
            True om startad, False om redan igång
        """ 
        with self.lock:
            if self.running :
                logger.warning(f"Freezer {self.freezer_id} alredy running")
                return False
            
            self.running = True
            self.control_thread = threading.Thread(
                target=self._control_loop,
                name=f"FreezerControl_{self.freezer_id}",
                daemon=True
            )
            self.control_thread.start()

            logger.info(f"Freezer {self.freezer_id} control started")
            return True
        
    def stop(self) -> None:
        """Stoppa temperaturreglering"""
        with self.lock:
            self.running = False

        if self.control_thread:
            self.control_thread.join(timeout=5)
            logger.info(f"Freezer {self.freezer_id} control stopped")

    def _control_loop(self) -> None:
        """Huvudregleringsloop för temperaturkontroll"""
        logger.debug(f"Starting control loop for freezer {self.freezer_id}")

        while self.running:
            try:
                # Läs temperatur fråm sensor
                self._read_temperature()

                # Kontrollera om avfrostning behövs
                if self._should_defrost():
                    self._start_defrost()

                # Hantera aktuellt tillstånd
                if self.state == FreezerState.DEFROSTING:
                    self._handle_defrostning()
                elif self.state == FreezerState.COOLING:
                    self._handle_cooling()
                elif self.state == FreezerState.IDLE:
                    self._handle_idle()

                # Uppdatera statistikk
                self._update_statistics()

                # Spar temperaturhistorikk
                self._update_temperature_history()

                # Kontrollera säkerhet
                self._safety_check()

            except Exception as e:
                logger.error(f"Error in freezer contol loop {e}")
                self.error_count += 1

                if self.error_count >= self.max_errors:
                    self._set_state(FreezerState.ERROR)
                    if self.on_error:
                        self.on_error(
                        self.freezer_id,
                        f"Max error count reached: {self.error_count}"
                    )
                
                # Vänta innan nästa cykel
                time.sleep(2)

        def _read_temperature(self) -> None: 
            """Läs temperature från sensor"""
            try:
                temp = self.sensor_manager.read_temperature(self.freezer_id)

                # Validera temperatur
                if not validate_temperature_range(
                    temp,
                    self.config.min_temperature - 10,
                    self.config.max_temperature + 10
                ):
                    raise ValueError(f"Invalid temperature reading: {temp}°C")
                
                # Uppdatera temperature
                old_temp = self.current_temperature
                self.current_temperature = temp

                # Meddela om temperaturförändring
                if old_temp != temp and self.on_temperature_change:
                    self.on_temperature_change(self.freezer_id, temp)

            except Exception as e:
                logger.error(f"Failed to read temperature for {self.freezer_id}: {e}")
                raise

        def _should_defrost(self) -> bool:
            """
            Kontrollera om avfrostning behövs.

            Returns:
                True om avfrostning behövs
            """
            time_since_defrost = time.time() - self.last_defrost_time
            hours_since_defrost = time_since_defrost / 3600

            # Kolla om det har gått tillräckligy lång tid
            if hours_since_defrost >= self.config.defrost_interval_hours:
                return True
            
            # Kolla om frostuppbyggnad är för stor (baserat på temperaturmönster)
            if len(self.temperature_history) > 10:
                # Om temperaturen stiger snabb trots att kompressorn är på
                recent_temps = self.temperature_history[-10:]
                if self.compressor_on:
                    temp_change = recent_temps[-1] - recent_temps[0]
                    if temp_change > 1.0: # Ökning på mer än 1°C
                        return True
                    
            return False
        
        def _start_defrost(self) -> None:
            """Starta avfrostningscykel"""
            if self.state == FreezerState.DEFROSTING:
                return
            
            logger.info(f"Starting defrost cykel för {self.freezer_id}")

            # Stäng av kompressorn
            self._set_compressor(False)

            # Sätt på avfrostningsvärmare
            self._set_defrost_heater(True)

            # Ändra tillstrånd
            self._set_state(FreezerState.DEFROSTING)

            self._last_defrost_time = time.time()

        def _handle_defrosting(self) -> None:
            """Hantera avfrostningsprocess"""
            # Kontrollera om avfrostningstiden är klar
            time_in_defrost = time.time() - self.last_defrost_time

            if time_in_defrost >= (self.config.defrost_duration_minutes * 60):
                # Avsluta avfrostning
                self._set_defrost_heater(False)

                # Vänta innan komprossorn startas
                time.sleep(60) # 1 minut för att låta värmare kylas

                # Starta kylning igen
                self._set_state(FreezerState.COOLING)
                logger.info(f"Defrost completed for {self.freezer_id}")

        def _handle_cooling(self) -> None:
            """Hantera kylningsprocess"""
            if self.current_temperature is None:
                return
            
            # Beräkna temperaturskillnad
            temp_deff = self.curretn_temperature - self.config.target_temperature

            # Kontrollera om kompressorn ska vara på eller av 
            if temp_deff > self.config.tolerance:
                # Temperaturen flr hög, sätt på kompressorn
                if not self.compressor_on:
                    # Kontrollera kompressorväntetid
                    time_slice_last_off = time.time() - self.last_defrost_time
                    if time_slice_last_off >= self.config.compressor_cooldown_secondes:
                        self._set_copewssor(True)
                elif temp_deff < -self.config.tolerance:
                    # Temperaturem för låg, stämg av kompressorn
                    if self.compressor_on:
                        self._set_compressor(False)

        def _handle_idle(self) -> None:
            """Hantera iaktivt tillstånd"""
            # Om temperaturen är inom tolerams, förbi inaktiv
            if self.current_temperature is None:
                return
            
            temp_deff = abs(self.current_temperature - self.config.target_temperature)

            if temp_deff > self.config.toleramce:
                # Temperaturen utanför tolerans, starta kylning
                self._set_state(FreezerState.COOLING)

        def _set_compress(self, on: bool) -> None:
            """
            Kontroööera kompressor.

            Args:
                on: True för att sätta på. False för att stänga av
            """
            if self.compressor_on == on:
                return
            
            self.copressor_on = on

            # Här skulle vi kontrollera den fysika kompressorn
            # simulate_hardvare_control("compressor", on)

            logger.debug(f"Compress {self.freezer_id}: {"ON" if on else "OFF"}")

        def _set_defrost_heater(self, on: bool) -> None:
            """
           Kontrollera avfrostningsvärmare.

           Args:
                on: True för att sätta på, False för att stänga av
            """
            if self.defrost_heater_on == on:
                return
            
            self.defrost_heater_on = on

            # Här skulle vi kontrollera den fysiska värmeren
            # simulate_hardware_control("defrost_heater", on)

            logger.debug(f"Defrost heater {self.freezer_id}: {"ON" if on else "OFF"}")


        def _set_state(self, new_stete: FreezerState) -> None:
            """
           Ändra frysfackstillstånd.

           Args:
                new_state: Nytt tillstånd
            """
            old_state = self.state
            self.state = new_stete

            logger.info(f"Freezer {self.freezer_id} status: {old_state.value} -> {new_stete.value}")

            if self.on_state_change:
                self.on_state_change(self.freezer_id, old_state, new_stete)
            
        def _update_statistics(self) -> None:
            """Uppdatera körstatistik"""
            if self.compressor_on:
                self.compressor_runtime += 2 # +2 sekunder per cykel

            # Beräkna energiförbrukning (exemplvärden)
            compressor_power = 150 # Watt när kompressorn är på
            heater_power = 200 # Watt när värmaren är på

            energy_wh = 0
            if self.compressor_on:
                energy_wh += (compressor_power * 2) / 3600 # Wh för 2 sekunder
            if self.defrost_heater_on:
                energy_wh += (heater_power * 2) / 3600 

            self.energy_consumption_kwh += energy_wh / 1000

        def _update_temperature_history(self) -> None:
            """Uppdatera temperaturhistorikk"""
            if self.current_temperature is None:
                return
            
            self.temperature_history.appent(self.current_temperature)

            # Begränsa historikk till senaste 1000 värden
            if len(self.temperature_history) > 1000:
                self.temperature_history = self.temperature_history[-1000]

        def _safety_check(self) -> None:
            """Utanför säkerhetskontroller"""
            if self.current_temperature > self.config.max_temperature + 5:
                logger.warning(f"Safety warning: Freezer  {self.freezer_id} temperature too high: {self.current_temperature}°C")

                # Om temperaturen är för hög, starta kylning
                if not self.compressor_on:
                    self._set_compressor(True)

                # Kontrollera för låg temperatur
                if self.current_temperatur < self.config.min_temperature - 5:
                    logger.warning(f"Safety warning: Freezer  {self.freezer_id} temperature too low: {self.current_temperature}°C")

                    # Om temperaturen är för låg, stäng av kompressorn
                    if self.compressor_on:
                        self._set_compressor(False)

                    # Kontrollera lång kylnyckel
                    if self.state == FreezerState.COOLING:
                        # Om kompressorn har varit på för länge (t.ex. > 30 minuter)
                        # Detta kan tyda på problem med dörrtätning eller frost
                        pass

        def get_status(self) -> Dict:
            """
            Hämta aktuell status för frysfacket.

            Returns:
                Dictionary med statusinformation
            """
            uptime = time.time() - self.start_time
            
            return {
                "freezer_id": self.freezer_id,
                "state": self.state.value,
                "current_temperature": self.current_temperature,
                "target_temperature": self.config.target_temperature,
                "compressor_on": self.compressor_on,
                "defrost_heater_on": self.defrost_heater_on,
                "uptime_hours": round(uptime / 3600, 2),
                "compressor_runtime_hours": round(self.compressor_runtime / 3600, 2),
                "energy_consumption_kwh": round(self.emergy_consumption_kwh, 3),
                "last_defrost_time": time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(self.last_defrost_time)
                ),
                "error_count": self.error_count
            }
        
        def set_target_temperature(self, temperature: float) -> bool:
            """
            Ändra mål-temperature.

            Args:
                temperature: Ny mål-temperatur

            Returns:
                True om ändringen lyckades
            """
            try:
                if not validate_temperature_range(
                    temperature,
                    self.config.min_temperature,
                    self.config.max_temperature
                ):
                    logger.error(f"Invalid target temperature: {temperature}°C")
                    return False
                
                old_temp = self.config.target_temperature
                self.config.target_temperature = temperature

                logger.info(f"Freezer {self.freezer_id} target temperature changed: {old_temp} -> {temperature}°C")
                return True
            
            except Exception as e:
                logger.error(f"Failed to set target temperature: {e}")
                return False
            
        def emergency_shutdown(self) -> None:
            """Nödstängning av frysfacket"""
            logger.warning(f"Emergency shutdown initiated för freezer {self.freezer_id}")

            # Stängt av allt
            self._set_compressor(False)
            self._set_defrost_heater(False)

            # Ändra tillstånd
            self._set_state(FreezerState.IDLE)

            # Stoppa regleringstråden
            self.stop()

        def get_temperature_history(self, limit: int = 100) -> list:
            """
            Hämta temperaturhistorikk

            Args:
                limit: Max antal värden att returnera

            Returns:
                List med temperatuvärden
            """
            if limit <= 0:
                return self.temperature_history.copy()
            
            return self.temperature_history[-limit].copy()
        
# Factory-funktion för att skapa flera freezer-kontroller
def create_freezer_controllers(sensor_manager, count: int = 1) -> Dict[str, FreezerController]:
    """
   Skapa fler freezer-kontoller.

   Args:
        sensor_manager: Sensorhanterare
        count: Antal freezer att skapa

    Returns:
        Dictionary med freezer-kontoller
    """
    controllers = {}

    for i in range(1, count + 1):
        freezer_id = f"freezer_{i}"
        controller = FreezerController(
            sensor_manager=sensor_manager,
            freezer_id=freezer_id
        )
        controllers[freezer_id] = controller

    return controllers

if __name__ == "__main__":
    # Testkod för freezer controller
    class MockSensorManager:
        def read_temperature(self, freezer_id):
            # Simulerar temperaturläkning
            import random
            return -18 + random.uniform(-1, 1)
        
        print("Testing Freezer Controller...")

        sensor_mgr = MockSensorManager()
        freezer = FreezerController(sensor_mgr)

        try:
            freezer.start()
            time.sleep(10)

            status = freezer.get_status()
            print(f"Freezer Status: {status}")

            freezer.set_target_temperature(-20)

            time.sleep(5)

        finally:
            freezer.stop()
            print("Testa completed.")

        