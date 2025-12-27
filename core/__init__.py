"""
Core module for the hamburger machine system.
This module contains the central control logic and state management.
"""

from .controller import MachineController
from .state_manager import StateManager, SystemState, OperationMode
from .safety_monitor import SafetyMonitor, SafetyStatus
from .event_bus import EventBus, Event, EventType

__version__ = "1.0.0"
__author__ = "Hamburger Machine Team"

# Export the main classes
__all__ = [
    # Controller
    "MachineController",
    
    # State management
    "StateManager",
    "SystemState",
    "OperationMode",

    # Safety
    "SafetyMonitor",
    "SafetyStatus",

    # Event system
    "EventBus",
    "Event",
    "EventType",
]

# Initialize module-level logger
import logging

# Create module logger
_logger = logging.getLogger(__name__)

def get_verision() -> str:
    """Get the current verision of core module."""
    return __version__

def initialize_core() -> None:
    """
    Initialize the core module.
    This should be called at application startup.
    """
    _logger.info(f"Initializing Hamburger Machine Core v{__version__}")
    _logger.info("Core module ready")

# Automatic initialization check
_initialized = False

def is_initialized() -> bool:
    """Check if the core module has been initialized."""
    return _initialized

def set_initialized() -> None:
    """Mark the core module as initialized."""
    global _initialized
    _initialized = True
    _logger.debug("Core module marked as initialized")

# Contants for the core module
SYSTEM_NAME = "Hamburger Machine Control System"
MAX_RETRY_ATTEMPTS = 3
DEFAULT_TIMEOUT = 30.0 # seconds

# Exceptions
class CoreError(Exception):
    """Base exception for core module errors"""
    pass

class InitializationError(CoreError):
    """Raised when core initialization fails."""
    pass

class StateTransitionError(CoreError):
    """Raised when an invalid state transition is attempted."""
    pass

# Optional: Import utility functions if needed
try:
    from ..utils.logger import setup_loggning
    from ..utils.config_loader import load_config
except ImportError:
    # This allows the core module to be imported independently,
    pass