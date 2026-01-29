"""
Kaia Exception Hierarchy
=========================

Centralized exception hierarchy for Kaia bot.

All Kaia-specific exceptions inherit from KaiaError for easy catching.
"""


class KaiaError(Exception):
    """Base exception for all Kaia errors"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ============================================================================
# GPU and Memory Errors
# ============================================================================

class GPUError(KaiaError):
    """Base class for GPU-related errors"""
    pass


class GPUMemoryError (KaiaError):
    """GPU memory allocation failed"""
    pass


class CUDAOutOfMemoryError(GPUMemoryError):
    """CUDA out of memory error"""
    pass


class VRAMInsufficientError(GPUMemoryError):
    """Insufficient VRAM for operation"""
    pass


class GPUNotAvailableError(GPUError):
    """GPU not available (CPU fallback)"""
    pass


# ============================================================================
# Model Errors
# ============================================================================

class ModelError(KaiaError):
    """Base class for model-related errors"""
    pass


class ModelLoadError(ModelError):
    """Failed to load model"""
    pass


class ModelUnloadError(ModelError):
    """Failed to unload model"""
    pass


class ModelTimeoutError(ModelError):
    """Model operation timed out"""
    pass


# ============================================================================
# Vision System Errors
# ============================================================================

class VisionError(KaiaError):
    """Base class for vision system errors"""
    pass


class VisionTimeoutError(VisionError):
    """Vision analysis timed out"""
    pass


class ImageDownloadError(VisionError):
    """Failed to download image"""
    pass


class ImageOptimizationError(VisionError):
    """Failed to optimize image"""
    pass


# ============================================================================
# Image Generation Errors
# ============================================================================

class ImageGenerationError(KaiaError):
    """Base class for image generation errors"""
    pass


class ImageGenDisabledError(ImageGenerationError):
    """Image generation disabled by circuit breaker"""
    pass


class ImageGenTimeoutError(ImageGenerationError):
    """Image generation timed out"""
    pass


# ============================================================================
# RAG System Errors
# ============================================================================

class RAGError(KaiaError):
    """Base class for RAG system errors"""
    pass


class RAGLockTimeout(RAGError):
    """RAG operation timed out waiting for lock"""
    pass


class RAGIndexError(RAGError):
    """RAG indexing failed"""
    pass


class RAGQueryError(RAGError):
    """RAG query failed"""
    pass


# ============================================================================
# Configuration Errors
# ============================================================================

class ConfigError(KaiaError):
    """Base class for configuration errors"""
    pass


class ConfigValidationError(ConfigError):
    """Configuration validation failed"""
    pass


class ConfigLoadError(ConfigError):
    """Failed to load configuration"""
    pass


# ============================================================================
# Rate Limiting Errors
# ============================================================================

class RateLimitError(KaiaError):
    """User exceeded rate limit"""
    pass


# ============================================================================
# News System Errors
# ============================================================================

class NewsError(KaiaError):
    """Base class for news system errors"""
    pass


class NewsUpdateError(NewsError):
    """Failed to update news"""
    pass


class NewsRetrievalError(NewsError):
    """Failed to retrieve news"""
    pass


# ============================================================================
# Helper Functions
# ============================================================================

def get_user_friendly_message(error: Exception) -> str:
    """
    Convert exception to user-friendly message.
    
    Args:
        error: Exception instance
        
    Returns:
        User-friendly error message
    """
    if isinstance(error, CUDAOutOfMemoryError):
        return "gpu ran out of memory. image generation disabled temporarily. chat still works."
    
    elif isinstance(error, VRAMInsufficientError):
        return "not enough gpu memory right now. try again in a moment."
    
    elif isinstance(error, VisionTimeoutError):
        return "vision analysis took too long. the image might be too complex or the server's busy."
    
    elif isinstance(error, ImageDownloadError):
        return "couldn't download that image. make sure it's a valid image file."
    
    elif isinstance(error, ImageGenDisabledError):
        return "image generation is disabled. restart required."
    
    elif isinstance(error, RAGLockTimeout):
        return "knowledge base is busy. try again in a moment."
    
    elif isinstance(error, RateLimitError):
        return "slow down. you're sending messages too fast."
    
    elif isinstance(error, ModelTimeoutError):
        return "that took too long to process. try a simpler request."
    
    elif isinstance(error, KaiaError):
        # Generic Kaia error
        return f"something went wrong: {error.message}"
    
    else:
        # Unknown error
        return "something broke. check the logs."


def should_auto_report(error: Exception) -> bool:
    """
    Determine if error should be automatically reported.
    
    Args:
        error: Exception instance
        
    Returns:
        True if error should be reported
    """
    # Don't report user errors (rate limits, etc.)
    if isinstance(error, (RateLimitError, ConfigValidationError)):
        return False
    
    # Don't report expected errors (timeouts, insufficient VRAM)
    if isinstance(error, (VisionTimeoutError, VRAMInsufficientError)):
        return False
    
    # Report all other Kaia errors
    return isinstance(error, KaiaError)
