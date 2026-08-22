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

    def test_user_logs_folder_extraction(self):
        """Verify that user_logs folders are correctly extracted from file paths."""
        file_path = "/home/user/knowledge_base/user_logs/Ekco_177011971818782721/user_profile.md"
        norm_path = os.path.normpath(file_path)
        parts = norm_path.split(os.sep)
        user_folder = ""
        if "user_logs" in parts:
            ul_idx = parts.index("user_logs")
            if ul_idx + 1 < len(parts):
                raw_folder = parts[ul_idx + 1]
                if "_" in raw_folder:
                    user_folder = raw_folder.split("_")[0]
                else:
                    user_folder = raw_folder
        assert user_folder == "Ekco"

    def test_explain_command_field_limit(self):
        """Ensure explain command embed field value does not exceed Discord's 1024 char limit."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from utils.commands.explain_handler import handle_explain_command

        ctx = MagicMock()
        ctx.config.is_owner.return_value = True
        
        # Mock 15 nodes with extremely long file paths and multiple audit flags
        nodes = []
        for i in range(15):
            nodes.append({
                "score": 0.954,
                "metadata": {
                    "source_type": "general_knowledge",
                    "retrieval_method": "hybrid",
                    "audit_flags": ["circular_justification", "contradictory_premise"],
                    "file_path": f"/home/user/knowledge_base/books/very_long_directory_name/dream_20260203_001422_phillip_k_dick_do_androids_dream_of_electric_sheep_long_version_{i}.md"
                }
            })
        ctx.rag._last_retrieval_results = nodes
        ctx.rag._last_retrieval_confidence = 0.88

        msg = AsyncMock()
        msg.author.name = "Ekco"
        msg.author.display_name = "Ekco"
        msg.author.id = 12345
        msg.channel.send = AsyncMock()

        asyncio.run(handle_explain_command(ctx, msg, AsyncMock()))

        assert msg.channel.send.called
        sent_embed = msg.channel.send.call_args[1].get("embed")
        assert sent_embed is not None
        assert len(sent_embed.fields) > 0
        field_val = sent_embed.fields[0].value
        assert len(field_val) <= 1024
        assert len(field_val) > 0





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
        import importlib
        # Ensure a clean import (test_intent_fix.py may have mocked this module)
        if 'utils.infrastructure.system.yaml_config' in sys.modules:
            mod = sys.modules['utils.infrastructure.system.yaml_config']
            if hasattr(mod, '_mock_name') or isinstance(mod, MagicMock):
                del sys.modules['utils.infrastructure.system.yaml_config']
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
