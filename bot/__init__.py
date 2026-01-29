"""
Bot Package
===========

Organized structure for Kaia Discord bot components.

This package extracts functionality from the monolithic Kaiacord.py
into a clean, maintainable structure while preserving all existing
functionality.

Structure:
- core.py: Main bot class and Discord client setup
- handlers/:Message, command, and event handlers
- services/: RAG, vision, image generation wrappers
- managers/: Configuration, state, rate limiting
"""

__version__ = "2.0.0"
