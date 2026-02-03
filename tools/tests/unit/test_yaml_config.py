"""
Unit Tests: YAML Configuration
================================

Tests for YAML configuration loading and validation.
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, mock_open


class TestYAMLConfigLoader:
    """Tests for YAML configuration loader"""
    
    def test_load_yaml_file(self, temp_dir):
        """Test loading YAML file"""
        from utils.infrastructure.system.yaml_config import load_yaml_file
        
        # Create test YAML
        yaml_file = temp_dir / "test.yaml"
        yaml_file.write_text("""
models:
  chat: "test-model"
  vision: "test-vision"
""")
        
        result = load_yaml_file(yaml_file)
        
        assert 'models' in result
        assert result['models']['chat'] == 'test-model'
        assert result['models']['vision'] == 'test-vision'
    
    def test_load_yaml_file_missing(self, temp_dir):
        """Test loading non-existent YAML returns empty dict"""
        from utils.infrastructure.system.yaml_config import load_yaml_file
        
        result = load_yaml_file(temp_dir / "missing.yaml")
        
        assert result == {}
    
    def test_deep_merge(self):
        """Test deep dictionary merging"""
        from utils.infrastructure.system.yaml_config import deep_merge
        
        base = {
            'models': {
                'chat': 'base-chat',
                'vision': 'base-vision'
            },
            'gpu': {
                'enabled': True
            }
        }
        
        override = {
            'models': {
                'chat': 'override-chat'  # Override chat
                # vision stays from base
            },
            'new_section': {
                'value': 123
            }
        }
        
        result = deep_merge(base, override)
        
        assert result['models']['chat'] == 'override-chat'
        assert result['models']['vision'] == 'base-vision'
        assert result['gpu']['enabled'] is True
        assert result['new_section']['value'] == 123
    
    def test_get_nested(self):
        """Test getting nested dictionary values"""
        from utils.infrastructure.system.yaml_config import get_nested
        
        data = {
            'level1': {
                'level2': {
                    'level3': 'value'
                }
            }
        }
        
        assert get_nested(data, 'level1.level2.level3') == 'value'
        assert get_nested(data, 'level1.level2') == {'level3': 'value'}
        assert get_nested(data, 'missing.path', 'default') == 'default'
    
    def test_set_nested(self):
        """Test setting nested dictionary values"""
        from utils.infrastructure.system.yaml_config import set_nested
        
        data = {}
        
        set_nested(data, 'level1.level2.level3', 'value')
        
        assert data['level1']['level2']['level3'] == 'value'
    
    def test_validate_config_valid(self):
        """Test configuration validation with valid config"""
        from utils.infrastructure.system.yaml_config import validate_config
        
        config = {
            'discord': {
                'token': 'test_token_123'
            },
            'models': {
                'chat': 'gemma3:12b',
                'vision': 'llama3.2-vision',
                'embedding': 'nomic-embed-text'
            },
            'paths': {
                'knowledge_base': './knowledge_base'
            },
            'performance': {
                'max_memory_messages': 30,
                'rag_top_k': 8,
                'requests_per_minute': 30
            },
            'gpu': {
                'image_gen_min_vram_gb': 8.0
            }
        }
        
        is_valid, errors = validate_config(config)
        
        assert is_valid
        assert len(errors) == 0
   
    def test_validate_config_missing_token(self):
        """Test validation fails without Discord token"""
        from utils.infrastructure.system.yaml_config import validate_config
        
        config = {
            'models': {
                'chat': 'test',
                'vision': 'test',
                'embedding': 'test'
            },
            'paths': {
                'knowledge_base': './knowledge_base'
            },
            'performance': {
                'max_memory_messages': 30,
                'rag_top_k': 8,
                'requests_per_minute': 30
            },
            'gpu': {
                'image_gen_min_vram_gb': 8.0
           }
        }
        
        is_valid, errors = validate_config(config)
        
        assert not is_valid
        assert any('token' in error.lower() for error in errors)
    
    def test_validate_config_invalid_values(self):
        """Test validation fails with invalid values"""
        from utils.infrastructure.system.yaml_config import validate_config
        
        config = {
            'discord': {
                'token': 'test'
            },
            'models': {
                'chat': 'test',
                'vision': 'test',
                'embedding': 'test'
            },
            'paths': {
                'knowledge_base': './knowledge_base'
            },
            'performance': {
                'max_memory_messages': 0,  # Invalid
                'rag_top_k': 0,  # Invalid
                'requests_per_minute': 0  # Invalid
            },
            'gpu': {
                'image_gen_min_vram_gb': 2.0  # Too low
            }
        }
        
        is_valid, errors = validate_config(config)
        
        assert not is_valid
        assert len(errors) >= 4  # All 4 invalid values


class TestYAMLConfig:
    """Tests for YAMLConfig class"""
    
    def test_yaml_config_properties(self, monkeypatch, temp_dir):
        """Test YAMLConfig properties"""
        from utils.infrastructure.system.yaml_config import YAMLConfig
        
        # Mock environment
        monkeypatch.setenv('DISCORD_TOKEN', 'test_token')
        
        # Mock config files to not exist
        monkeypatch.setattr('pathlib.Path.exists', lambda x: str(x).endswith('default_config.yaml'))
        
        # Mock load_yaml_file to return valid config
        def mock_load_yaml(path):
            if 'default_config.yaml' in str(path):
                return {
                    'discord': {
                        'token': 'default_token',
                        'blacklisted_channels': 'general,test'
                    },
                    'models': {
                        'chat': 'gemma3:12b',
                        'vision': 'llama3.2-vision:11b',
                        'embedding': 'nomic-embed-text'
                    },
                    'paths': {
                        'knowledge_base': './knowledge_base',
                        'persist': './storage'
                    },
                    'performance': {
                        'max_memory_messages': 30,
                        'max_log_size_mb': 100,
                        'max_consecutive_quips': 3,
                        'rag_top_k': 8,
                        'requests_per_minute': 30,
                        'enable_semantic_cache': True
                    },
                    'startup': {
                        'news_update': False,
                        'news_timeout': 10
                    },
                    'gpu': {
                        'image_gen_min_vram_gb': 8.0
                    }
                }
            return {}
        
        with patch('utils.infrastructure.system.yaml_config.load_yaml_file', mock_load_yaml):
            # This will use mocked env var
            config = YAMLConfig()
            
            # Test properties
            assert config.discord_token == 'test_token'  # From env
            assert config.chat_model == 'gemma3:12b'
            assert config.vision_model == 'llama3.2-vision:11b'
            assert config.embedding_model == 'nomic-embed-text'
            assert config.max_memory_messages == 30
            assert config.rag_top_k == 8
    
    def test_yaml_config_should_use_cache(self, monkeypatch):
        """Test cache usage logic"""
        from utils.infrastructure.system.yaml_config import YAMLConfig
        
        # Mock to avoid file I/O
        monkeypatch.setenv('DISCORD_TOKEN', 'test')
        monkeypatch.setattr('pathlib.Path.exists', lambda x: str(x).endswith('default_config.yaml'))
        
        def mock_load_yaml(path):
            return {
                'discord': {'token': 'test'},
                'models': {'chat': 'test', 'vision': 'test', 'embedding': 'test'},
                'paths': {'knowledge_base': './knowledge_base'},
                'performance': {
                    'max_memory_messages': 30,
                    'rag_top_k': 8,
                    'requests_per_minute': 30,
                    'enable_semantic_cache': True
                },
                'startup': {'news_update': False},
                'gpu': {'image_gen_min_vram_gb': 8.0}
            }
        
        with patch('bot.managers.yaml_config.load_yaml_file', mock_load_yaml):
            config = YAMLConfig()
            
            # Should NOT cache identity queries
            assert not config.should_use_cache("who are you", "IDENTITY")
            assert not config.should_use_cache("what are you", "WHOAMI")
            
            # Should cache normal queries
            assert config.should_use_cache("what is Python", "KNOWLEDGE")
            assert config.should_use_cache("how do I use async", "CASUAL")
