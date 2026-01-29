#!/usr/bin/env python3
"""
Configuration Migration Script
===============================

Migrates configuration from .env and old config.py to new YAML format.

Usage:
    python scripts/migrate_config.py
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Any


def read_env_file(env_path: Path) -> Dict[str, str]:
    """Read .env file and return key-value pairs"""
    if not env_path.exists():
        return {}
    
    env_vars = {}
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Parse KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                env_vars[key] = value
    
    return env_vars


def migrate_config(env_vars: Dict[str, str]) -> Dict[str, Any]:
    """Convert .env variables to YAML config structure"""
    config = {
        'models': {},
        'gpu': {},
        'performance': {},
        'paths': {},
        'startup': {},
        'discord': {},
        'logging': {},
        'dashboard': {},
        'features': {},
        'api': {}
    }
    
    # Discord
    if 'DISCORD_TOKEN' in env_vars:
        config['discord']['token'] = f"${{{env_vars['DISCORD_TOKEN']}}}"  # Keep as env var reference
    
    if 'BLACKLISTED_CHANNELS' in env_vars:
        config['discord']['blacklisted_channels'] = env_vars['BLACKLISTED_CHANNELS']
    
    # Models
    if 'CHAT_MODEL' in env_vars:
        config['models']['chat'] = env_vars['CHAT_MODEL']
    
    if 'VISION_MODEL' in env_vars:
        config['models']['vision'] = env_vars['VISION_MODEL']
    
    if 'EMBEDDING_MODEL' in env_vars:
        config['models']['embedding'] = env_vars['EMBEDDING_MODEL']
    
    # API Keys
    if 'GEMINI_API_KEY' in env_vars:
        config['api']['gemini_key'] = f"${{{env_vars['GEMINI_API_KEY']}}}"  # Keep as env var reference
    
    # Remove empty sections
    config = {k: v for k, v in config.items() if v}
    
    return config


def generate_yaml_file(config: Dict[str, Any], output_path: Path):
    """Generate YAML config file with comments"""
    
    # Add header comment
    header = """# Kaia User Configuration
#
# This file was auto-generated from your .env file.
# 
# Hierarchy (highest to lowest priority):
# 1. Environment variables (e.g., DISCORD_TOKEN)
# 2. This file (config/kaia.yaml)
# 3. Default config (config/default_config.yaml)
#
# You can:
# - Keep secrets in .env (recommended)
# - Override defaults here
# - Use ${VARIABLE_NAME} to reference environment variables
#
"""
    
    with open(output_path, 'w') as f:
        f.write(header)
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    print(f"✅ Created: {output_path}")


def main():
    """Main migration function"""
    print("="*60)
    print(" Kaia Configuration Migration")
    print ("="*60)
    print()
    
    # Check for .env
    env_path = Path(".env")
    if not env_path.exists():
        print("⚠️  No .env file found")
        print("   If you've never configured Kaia, create .env first")
        print()
        env_vars = {}
    else:
        print(f"📄 Reading: {env_path}")
        env_vars = read_env_file(env_path)
        print(f"   Found {len(env_vars)} environment variables")
        print()
    
    # Check if default config exists
    default_config_path = Path("config/default_config.yaml")
    if not default_config_path.exists():
        print("❌ ERROR: config/default_config.yaml not found")
        print("   This file should exist in the repository")
        return 1
    
    print(f"✅ Found: {default_config_path}")
    print()
    
    # Generate user config
    output_path = Path("config/kaia.yaml")
    
    if output_path.exists():
        print(f"⚠️  WARNING: {output_path} already exists")
        response = input("   Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("   Aborted")
            return 0
        print()
    
    # Migrate
    print("🔄 Migrating configuration...")
    config = migrate_config(env_vars)
    
    if not config:
        print("⚠️  No configuration to migrate")
        print("   Your .env variables look good!")
        print("   A minimal kaia.yaml will be created for future customization")
        config = {'# Your custom settings': None}
    
    # Generate YAML
    generate_yaml_file(config, output_path)
    print()
    
    # Summary
    print("="*60)
    print(" Migration Complete!")
    print("="*60)
    print()
    print("Next steps:")
    print("  1. Review config/kaia.yaml")
    print("  2. Keep secrets in .env (DISCORD_TOKEN, GEMINI_API_KEY)")
    print("  3. Customize settings in config/kaia.yaml")
    print("  4. Run: python Kaiacord.py")
    print()
    
    # Warnings
    if 'DISCORD_TOKEN' not in env_vars:
        print("⚠️  WARNING: DISCORD_TOKEN not found in .env")
        print("   Set it before starting the bot")
        print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
