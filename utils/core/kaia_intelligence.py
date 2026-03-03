"""
Kaia Intelligence — Compatibility Facade
==========================================

Phase 28 / CQ-01: This file was split into focused modules.
All logic now lives in:
  - utils.core.context_optimizer  (ContextOptimizer, ContextWeaver, RelevanceFeedback,
                                   PersonalizationEngine, PersistentStateManager,
                                   Intent, ContextCtx dataclasses)
  - utils.core.intent_classifier  (IntentParser, ModelWarmPool, QueryClassifier)

This facade re-exports all public symbols so that existing imports
(e.g. `from utils.core.kaia_intelligence import Intent`) continue to work.

DO NOT ADD LOGIC HERE. Edit the source modules instead.
"""

# ── Shared Types ──────────────────────────────────────────────────────────
from utils.core.context_optimizer import Intent, ContextCtx                         # noqa: F401

# ── Context Optimization & Personalization ────────────────────────────────
from utils.core.context_optimizer import (                                          # noqa: F401
    ContextOptimizer,
    ContextWeaver,
    RelevanceFeedback,
    PersonalizationEngine,
    PersistentStateManager,
)

# ── Intent Classification ─────────────────────────────────────────────────
from utils.core.intent_classifier import (                                          # noqa: F401
    IntentParser,
    ModelWarmPool,
    QueryClassifier,
)
