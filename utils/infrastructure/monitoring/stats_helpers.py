"""
Stats Poller Helper Functions
==============================

Safe accessor functions for stats_poller to prevent NameError issues.

This module provides defensive wrappers around the global stats_poller
to prevent crashes when stats_poller is not yet initialized or has been
cleaned up during shutdown.

Usage:
    from utils.infrastructure.monitoring.stats_helpers import safe_stop_stats_poller, safe_start_stats_poller
    
    # In image generation:
    safe_stop_stats_poller()
    # ... generate image ...
    safe_start_stats_poller()
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Reference to global stats_poller (will be set by main module)
_stats_poller_ref: Optional[object] = None


def set_stats_poller(poller) -> None:
    """
    Set the global stats_poller reference.
    
    This should be called once during startup after stats_poller is initialized.
    
    Args:
        poller: RealTimeStatsPoller instance
    """
    global _stats_poller_ref
    _stats_poller_ref = poller
    logger.debug("Stats poller reference registered")


def get_stats_poller() -> Optional[object]:
    """
    Get the stats_poller instance if available.
    
    Returns:
        RealTimeStatsPoller instance or None if not initialized
    """
    return _stats_poller_ref


def safe_stop_stats_poller() -> bool:
    """
    Safely stop the stats poller if it exists.
    
    Returns:
        True if stopped successfully, False otherwise
    """
    try:
        if _stats_poller_ref is not None:
            _stats_poller_ref.stop()
            logger.debug("Stats poller stopped")
            return True
        else:
            logger.warning("Stats poller not initialized, skipping stop")
            return False
    except AttributeError as e:
        logger.warning(f"Stats poller missing stop method: {e}")
        return False
    except Exception as e:
        logger.error(f"Error stopping stats poller: {e}")
        return False


def safe_start_stats_poller() -> bool:
    """
    Safely start the stats poller if it exists.
    
    Returns:
        True if started successfully, False otherwise
    """
    try:
        if _stats_poller_ref is not None:
            _stats_poller_ref.start()
            logger.debug("Stats poller started")
            return True
        else:
            logger.warning("Stats poller not initialized, skipping start")
            return False
    except AttributeError as e:
        logger.warning(f"Stats poller missing start method: {e}")
        return False
    except Exception as e:
        logger.error(f"Error starting stats poller: {e}")
        return False


def safe_get_stats() -> dict:
    """
    Safely get current stats from the poller.
    
    Returns:
        Stats dict if available, empty dict otherwise
    """
    try:
        if _stats_poller_ref is not None and hasattr(_stats_poller_ref, 'get_stats'):
            return _stats_poller_ref.get_stats()
        else:
            logger.debug("Stats poller not available or missing get_stats")
            return {}
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {}


def safe_record_response_time(response_time: float) -> bool:
    """
    Safely record a response time measurement.
    
    Args:
        response_time: Response time in seconds
        
    Returns:
        True if recorded successfully, False otherwise
    """
    try:
        if _stats_poller_ref is not None and hasattr(_stats_poller_ref, 'record_response_time'):
            _stats_poller_ref.record_response_time(response_time)
            return True
        else:
            logger.debug("Stats poller not available, skipping response time recording")
            return False
    except Exception as e:
        logger.error(f"Error recording response time: {e}")
        return False


def safe_increment_messages() -> bool:
    """
    Safely increment message count.
    
    Returns:
        True if incremented successfully, False otherwise
    """
    try:
        if _stats_poller_ref is not None and hasattr(_stats_poller_ref, 'increment_messages'):
            _stats_poller_ref.increment_messages()
            return True
        else:
            logger.debug("Stats poller not available, skipping message increment")
            return False
    except Exception as e:
        logger.error(f"Error incrementing messages: {e}")
        return False


def is_stats_poller_available() -> bool:
    """
    Check if stats poller is available.
    
    Returns:
        True if stats_poller is initialized and available
    """
    return _stats_poller_ref is not None
