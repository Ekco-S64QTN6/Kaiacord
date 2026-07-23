#!/usr/bin/env python3
"""
Kaia Health Check
==================

Quick health check for Kaia bot system.

Checks:
- Python version
- GPU availability
- Ollama installation and models
- Discord token
- Configuration
- File permissions
- Dependencies
"""

import sys
import os
import subprocess
from pathlib import Path

# Fix sys.path to allow utils resolution when run via python tools/maintenance/health_check.py
sys.path.append(os.getcwd())


class HealthCheck:
    """Health check runner"""
    
    def __init__(self):
        self.checks = []
        self.warnings = []
        self.errors = []
        
    def check(self, name: str, condition: bool, details: str = ""):
        """Record a check result"""
        self.checks.append((name, condition, details))
        if not condition:
            self.errors.append(f"{name}: {details}")
        return condition
    
    def warn(self, name: str, message: str):
        """Record a warning"""
        self.warnings.append(f"{name}: {message}")
    
    def check_python_version(self):
        """Check Python version"""
        version = sys.version_info
        is_ok = version.major == 3 and version.minor >= 9
        details = f"{version.major}.{version.minor}.{version.micro}"
        self.check("Python Version", is_ok, details)
        if not is_ok:
            self.warn("Python", "Kaia requires Python 3.9+")
    
    def check_gpu(self):
        """Check GPU availability"""
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            
            if cuda_available:
                device_name = torch.cuda.get_device_name(0)
                total_vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
                details = f"{device_name} ({total_vram:.1f} GiB)"
                self.check("CUDA Available", True, details)
                
                if total_vram < 12:
                    self.warn("VRAM", f"Only {total_vram:.1f} GiB available. 12+ GiB recommended.")
            else:
                self.check("CUDA Available", False, "Running on CPU")
                self.warn("GPU", "No CUDA GPU detected. Performance will be slower.")
                
        except ImportError:
            self.check("PyTorch", False, "Not installed")
            self.errors.append("PyTorch not installed. Run: pip install torch")
    
    def check_ollama(self):
        """Check Ollama installation and models"""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                self.check("Ollama Installed", True, "")
                
                # Read required models from config — no hardcoded model names
                try:
                    from utils.infrastructure.system.yaml_config import config
                    chat_model = config.chat_model
                    classification_model = config.get('models.classification_model', 'gemma2:2b')
                    embedding_model = config.get('models.embedding', 'nomic-embed-text-cpu')
                except Exception:
                    chat_model = "gemma3:12b"
                    classification_model = "gemma2:2b"
                    embedding_model = "nomic-embed-text-cpu"

                output = result.stdout.lower()
                required_models = [chat_model, classification_model, embedding_model]
                found_models = []
                
                for model in required_models:
                    # Strip -cpu suffix for matching since ollama list shows base name
                    check_name = model.replace("-cpu", "")
                    if check_name.lower() in output:
                        found_models.append(model)
                
                if len(found_models) == len(required_models):
                    self.check("Ollama Models", True, ", ".join(found_models))
                else:
                    missing = set(required_models) - set(found_models)
                    self.check("Ollama Models", False, f"Missing: {', '.join(missing)}")
                    pull_cmds = " && ".join(f"ollama pull {m}" for m in missing)
                    self.warn("Models", f"Run: {pull_cmds}")
            else:
                self.check("Ollama", False, "Not responding")
                
        except FileNotFoundError:
            self.check("Ollama", False, "Not installed")
            self.errors.append("Ollama not found. Install from ollama.ai")
        except subprocess.TimeoutExpired:
            self.check("Ollama", False, "Timeout")
            self.warn("Ollama", "Ollama is not responding. Is it running?")
    
    def check_config(self):
        """Check configuration"""
        try:
            from utils.infrastructure.system.yaml_config import config
            
            # Check Discord token
            token_ok = bool(config.discord_token and len(config.discord_token) > 50)
            self.check("Discord Token", token_ok, "Set" if token_ok else "Missing")
            
            if not token_ok:
                self.errors.append("Set DISCORD_TOKEN in .env file")
            
            # Check other config
            self.check("Knowledge Base", os.path.exists(config.knowledge_base_dir), config.knowledge_base_dir)
            self.check("Persist Dir", os.path.exists(config.persist_dir), config.persist_dir)
            
        except ImportError as e:
            self.check("Config", False, str(e))
            self.errors.append("Cannot import utils.infrastructure.system.yaml_config")
    
    def check_permissions(self):
        """Check file permissions"""
        dirs_to_check = ["knowledge_base", "logs", "memory"]
        
        for dir_name in dirs_to_check:
            dir_path = Path(dir_name)
            
            if dir_path.exists():
                is_writable = os.access(dir_path, os.W_OK)
                self.check(f"{dir_name}/ writable", is_writable, str(dir_path))
                
                if not is_writable:
                    self.errors.append(f"Run: chmod -R u+w {dir_name}/")
            else:
                # Directory doesn't exist - will be created at runtime
                self.check(f"{dir_name}/ exists", False, "Will be created")
    
    def check_dependencies(self):
        """Check Python dependencies"""
        required = [
            "discord",
            "ollama",
            "llama_index",
            "requests",
            "psutil",
        ]
        
        missing = []
        for package in required:
            try:
                __import__(package)
            except ImportError:
                missing.append(package)
        
        if missing:
            self.check("Dependencies", False, f"Missing: {', '.join(missing)}")
            self.errors.append("Run: pip install -r requirements.txt")
        else:
            self.check("Dependencies", True, "All installed")
    
    def run_all(self):
        """Run all health checks"""
        print("\n" + "="*50)
        print("  Kaia Health Check")
        print("="*50 + "\n")
        
        self.check_python_version()
        self.check_gpu()
        self.check_ollama()
        self.check_config()
        self.check_permissions()
        self.check_dependencies()
        
        # Print results
        print("\nResults:")
        print("-" * 50)
        
        for name, condition, details in self.checks:
            status = "✅" if condition else "❌"
            if details:
                print(f"{status} {name:25s} {details}")
            else:
                print(f"{status} {name}")
        
        # Print warnings
        if self.warnings:
            print("\n⚠️  Warnings:")
            print("-" * 50)
            for warning in self.warnings:
                print(f"  {warning}")
        
        # Print errors
        if self.errors:
            print("\n❌ Errors:")
            print("-" * 50)
            for error in self.errors:
                print(f"  {error}")
        
        # Summary
        print("\n" + "="*50)
        total = len(self.checks)
        passed = sum(1 for _, condition, _ in self.checks if condition)
        print(f"  {passed}/{total} checks passed")
        
        if self.errors:
            print(f"  {len(self.errors)} errors found")
            print("="*50 + "\n")
            return 1
        elif self.warnings:
            print(f"  {len(self.warnings)} warnings")
            print("="*50 + "\n")
            return 0
        else:
            print("  All systems go! 🚀")
            print("="*50 + "\n")
            return 0


if __name__ == "__main__":
    checker = HealthCheck()
    sys.exit(checker.run_all())
