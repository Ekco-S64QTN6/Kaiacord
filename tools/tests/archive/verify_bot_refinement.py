import unittest
import sys
import os
from pathlib import Path

# Mock dependencies
sys.path.append('/home/ekco/github/Kaiacord')

from utils.core.response_filter import BotSpeakFilter
from utils.core.kaia_intelligence import ContextOptimizer

class TestBotRefinement(unittest.TestCase):
    def test_roleplay_filter_hardening(self):
        """Test that various roleplay patterns are stripped."""
        samples = [
            ("(sighs)", ""),
            ("hey there (looks around)", "hey there"),
            ("i'm busy (Types slowly.)", "i'm busy"),
            ("*scratches head* what?", "what?"),
            ("*Nods* totally.", "totally."),
            ("((double parens))", ""),  # Should catch nested if aggressive enough
            ("(Checking logs...)", ""),
        ]
        
        for input_text, expected in samples:
            with self.subTest(input_text=input_text):
                result = BotSpeakFilter.harden(input_text)
                self.assertEqual(result, expected)

    def test_thread_id_resolution(self):
        """Test that thread IDs in RAG nodes are resolved to titles."""
        optimizer = ContextOptimizer()
        
        class MockNode:
            def __init__(self, text, path):
                self.text = text
                self.metadata = {'file_path': path}
            def get_content(self): return self.text

        nodes = [
            MockNode("Content of the thread.", "/home/ekco/github/Kaiacord/knowledge_base/forum_posts/thread_446838_youve-gotta-be.md")
        ]
        
        result = optimizer.optimize_context("general", "Persona", nodes, [])
        rag_text = result['rag']
        
        self.assertIn("source=\"Thread: 'Youve Gotta Be' (ID: 446838)\"", rag_text)
        self.assertIn('Content of the thread.', rag_text)

if __name__ == "__main__":
    unittest.main()
