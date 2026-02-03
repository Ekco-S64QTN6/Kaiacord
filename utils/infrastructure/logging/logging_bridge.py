"""
Logging Bridge Interface
=========================

Abstract interface to decouple logging from dashboard implementation,
preventing circular dependency issues.

The dashboard can implement this interface and register itself at startup,
allowing the logger to output to the dashboard without importing it directly.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from enum import Enum


class LogLevel(Enum):
    """Log levels matching kaia_logger"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    ACTION = "ACTION"
    MODEL_ACTION = "MODEL_ACTION"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    RESPONSE = "RESPONSE"
    CONTEXT_RETRIEVAL = "CONTEXT_RETRIEVAL"


class LoggingBridge(ABC):
    """
    Abstract interface for logging output destinations.
    
    Implementations can be dashboards, file loggers, or any other
    output mechanism. This decouples the logger from specific implementations.
    """
    
    @abstractmethod
    def log(self, level: LogLevel, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Log a message at the specified level.
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, etc.)
            message: The log message
            metadata: Optional metadata dict (e.g., request_id, file_path)
        """
        pass
    
    @abstractmethod
    def log_raw(self, message: str) -> None:
        """
        Log a raw message without formatting.
        
        Args:
            message: Raw message string
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this logging bridge is available.
        
        Returns:
            True if the bridge is ready to receive logs
        """
        pass


class NullLoggingBridge(LoggingBridge):
    """
    No-op logging bridge for when no dashboard is available.
    
    This prevents errors when logging is called before dashboard initialization.
    """
    
    def log(self, level: LogLevel, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """No-op log"""
        pass
    
    def log_raw(self, message: str) -> None:
        """No-op raw log"""
        pass
    
    def is_available(self) -> bool:
        """Always returns False"""
        return False


class LoggingBridgeRegistry:
    """
    Registry for logging bridges.
    
    Allows multiple bridges to be registered (e.g., dashboard + file logger).
    Messages are sent to all registered bridges.
    """
    
    def __init__(self):
        self._bridges: list[LoggingBridge] = []
        self._fallback: LoggingBridge = NullLoggingBridge()
    
    def register(self, bridge: LoggingBridge) -> None:
        """
        Register a logging bridge.
        
        Args:
            bridge: LoggingBridge implementation
        """
        if bridge not in self._bridges:
            self._bridges.append(bridge)
    
    def unregister(self, bridge: LoggingBridge) -> None:
        """
        Unregister a logging bridge.
        
        Args:
            bridge: LoggingBridge implementation to remove
        """
        if bridge in self._bridges:
            self._bridges.remove(bridge)
    
    def log(self, level: LogLevel, message: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Send log message to all registered bridges.
        
        Args:
            level: Log level
            message: Log message
            metadata: Optional metadata
        """
        # Send to all available bridges
        sent = False
        for bridge in self._bridges:
            if bridge.is_available():
                try:
                    bridge.log(level, message, metadata)
                    sent = True
                except Exception as e:
                    # Don't let logging errors crash the app
                    # Could log to stderr here if needed
                    pass
        
        # Use fallback if no bridges available
        if not sent:
            self._fallback.log(level, message, metadata)
    
    def log_raw(self, message: str) -> None:
        """
        Send raw message to all registered bridges.
        
        Args:
            message: Raw message
        """
        for bridge in self._bridges:
            if bridge.is_available():
                try:
                    bridge.log_raw(message)
                except Exception:
                    pass
    
    def has_bridges(self) -> bool:
        """
        Check if any bridges are registered.
        
        Returns:
            True if at least one bridge is registered
        """
        return len(self._bridges) > 0


# Global registry instance
_registry = LoggingBridgeRegistry()


def get_logging_registry() -> LoggingBridgeRegistry:
    """
    Get the global logging bridge registry.
    
    Returns:
        Global LoggingBridgeRegistry instance
    """
    return _registry


def register_logging_bridge(bridge: LoggingBridge) -> None:
    """
    Register a logging bridge with the global registry.
    
    Args:
        bridge: LoggingBridge implementation
    """
    _registry.register(bridge)


def unregister_logging_bridge(bridge: LoggingBridge) -> None:
    """
    Unregister a logging bridge from the global registry.
    
    Args:
        bridge: LoggingBridge implementation
    """
    _registry.unregister(bridge)
