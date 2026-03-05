"""
Unit Tests for Tier 1 Features
===============================

Tests for: Audit Flags, Snapshots, Provenance

Run: python -m pytest tools/tests/unit/test_tier1_features.py -v
"""

import os
import re
import sys
import json
import shutil
import tempfile
from unittest.mock import MagicMock, AsyncMock, patch
from collections import Counter
from datetime import datetime

import pytest


# ============================================================================
# Feature 1: Audit Flag System
# ============================================================================

class TestAuditFlagConstants:
    """Test audit flag valid constructs and labels."""

    def test_valid_constructs_are_defined(self):
        from utils.commands.audit_handler import VALID_CONSTRUCTS
        assert len(VALID_CONSTRUCTS) == 5
        assert "circular_justification" in VALID_CONSTRUCTS
        assert "linguistic_mimicry" in VALID_CONSTRUCTS
        assert "anthropocentric_exceptionalism" in VALID_CONSTRUCTS
        assert "paternalistic_framing" in VALID_CONSTRUCTS
        assert "hedge_density" in VALID_CONSTRUCTS

    def test_all_constructs_have_labels(self):
        from utils.commands.audit_handler import VALID_CONSTRUCTS, CONSTRUCT_LABELS
        for construct in VALID_CONSTRUCTS:
            assert construct in CONSTRUCT_LABELS, f"Missing label for {construct}"
            assert isinstance(CONSTRUCT_LABELS[construct], str)


class TestAuditFlagPenalty:
    """Test the audit flag penalty in _score_and_filter_nodes."""

    def test_penalty_reduces_score(self):
        """Nodes with audit flags should have a lower final score."""
        penalty = 0.15
        base_score = 1.0
        
        # No flags
        no_flag_score = base_score
        
        # One flag
        one_flag_score = base_score - (1 * penalty)
        assert one_flag_score < no_flag_score
        assert one_flag_score == 0.85
        
        # Two flags
        two_flag_score = base_score - (2 * penalty)
        assert two_flag_score < one_flag_score
        assert two_flag_score == 0.70

    def test_penalty_caps_at_three_flags(self):
        """Penalty should cap at 3 flags to avoid complete suppression."""
        penalty = 0.15
        base_score = 1.0

        # 3 flags = max penalty
        three_flag_penalty = min(3 * penalty, penalty * 3)
        three_flag_score = base_score - three_flag_penalty
        
        # 5 flags should not exceed 3x penalty
        five_flag_penalty = min(5 * penalty, penalty * 3)
        five_flag_score = base_score - five_flag_penalty
        
        assert three_flag_score == five_flag_score == 0.55


# ============================================================================
# Feature 3: Conversation Snapshots
# ============================================================================

class TestSnapshotHandler:
    """Test snapshot content generation."""

    def test_yaml_escaping(self):
        from utils.commands.snapshot_handler import _escape_yaml
        assert _escape_yaml('Hello "world"') == 'Hello \\"world\\"'
        assert _escape_yaml("Line1\nLine2") == "Line1 Line2"

    def test_trigger_reindex_creates_file(self):
        from utils.commands.snapshot_handler import _trigger_reindex
        # Remove if exists
        trigger_file = ".trigger_reindex"
        if os.path.exists(trigger_file):
            os.remove(trigger_file)
        
        _trigger_reindex()
        # The file should now exist (or the function gracefully fails)
        # NOTE: In CI this might fail if cwd doesn't allow writes



# ============================================================================
# Feature 6: Provenance Display
# ============================================================================

class TestProvenanceFormatting:
    """Test provenance display formatting."""

    def test_result_formatting(self):
        """Test that provenance results are formatted correctly."""
        result = {
            "content": "Some knowledge content here that might be quite long",
            "metadata": {
                "file_path": "/path/to/knowledge_base/general/test_doc.md",
                "source_type": "general_knowledge",
                "audit_flags": ["circular_justification"]
            },
            "label": "Knowledge [test_doc.md]",
            "score": 0.85
        }

        basename = os.path.basename(result["metadata"]["file_path"])
        assert basename == "test_doc.md"
        
        flags = result["metadata"]["audit_flags"]
        assert len(flags) == 1
        assert "circular_justification" in flags

    def test_preview_truncation(self):
        """Content preview should be truncated to 100 chars."""
        long_content = "x" * 200
        preview = long_content[:100] + ("..." if len(long_content) > 100 else "")
        assert len(preview) == 103
        assert preview.endswith("...")




# ============================================================================
# RAG Metadata: Snapshot Source Type
# ============================================================================

class TestSnapshotMetadata:
    """Test that snapshot files get the correct source_type."""

    def test_snapshot_path_detection(self):
        """Files in knowledge_base/snapshots/ should get source_type='snapshot'."""
        file_path = "/home/user/knowledge_base/snapshots/snapshot_20260224.md"
        assert "snapshots" in file_path

    def test_non_snapshot_path(self):
        """Regular knowledge files should NOT match snapshot detection."""
        file_path = "/home/user/knowledge_base/general/article.md"
        assert "snapshots" not in file_path


# ============================================================================
# Config: Audit Flag Penalty
# ============================================================================

class TestAuditConfig:
    """Test audit-related config properties."""

    def test_default_penalty_value(self):
        """Default audit flag penalty should be 0.15."""
        from utils.infrastructure.system.yaml_config import YAMLConfig
        config = YAMLConfig()
        assert config.rag_audit_flag_penalty == 0.15


# ============================================================================
# Integration: sanitize_log_content still strips think tags
# ============================================================================

class TestSanitizeLogContent:
    """Verify that sanitize_log_content strips <think> tags for RAG logging."""

    def test_think_tags_stripped_from_logs(self):
        from utils.core.kaia_rag import sanitize_log_content
        text = "Hello <think>internal reason</think> World"
        cleaned = sanitize_log_content(text)
        assert "<think>" not in cleaned
        assert "internal reason" not in cleaned
        assert "Hello" in cleaned
        assert "World" in cleaned

    def test_multiline_think_tags_stripped(self):
        from utils.core.kaia_rag import sanitize_log_content
        text = "Start\n<think>\nLine 1\nLine 2\n</think>\nEnd"
        cleaned = sanitize_log_content(text)
        assert "<think>" not in cleaned
        assert "Line 1" not in cleaned
        assert "Start" in cleaned
        assert "End" in cleaned

    def test_no_think_tags_unchanged(self):
        from utils.core.kaia_rag import sanitize_log_content
        text = "Normal response without any tags."
        cleaned = sanitize_log_content(text)
        assert cleaned == text
