import time

print("Profiling imports...")

start = time.time()
import os
print(f"import os: {time.time() - start:.4f}s")

start = time.time()
import sys
print(f"import sys: {time.time() - start:.4f}s")

start = time.time()
import asyncio
print(f"import asyncio: {time.time() - start:.4f}s")

start = time.time()
import uuid
print(f"import uuid: {time.time() - start:.4f}s")

start = time.time()
import re
print(f"import re: {time.time() - start:.4f}s")

start = time.time()
import traceback
print(f"import traceback: {time.time() - start:.4f}s")

start = time.time()
import random
print(f"import random: {time.time() - start:.4f}s")

start = time.time()
import time as t_lib
print(f"import time: {time.time() - start:.4f}s")

start = time.time()
import logging
print(f"import logging: {time.time() - start:.4f}s")

start = time.time()
import psutil
print(f"import psutil: {time.time() - start:.4f}s")

start = time.time()
import threading
print(f"import threading: {time.time() - start:.4f}s")

start = time.time()
import concurrent.futures
print(f"import concurrent.futures: {time.time() - start:.4f}s")

start = time.time()
from datetime import datetime
print(f"from datetime import datetime: {time.time() - start:.4f}s")

start = time.time()
from pathlib import Path
print(f"from pathlib import Path: {time.time() - start:.4f}s")

start = time.time()
from typing import List, Dict, Optional, Any
print(f"from typing import ...: {time.time() - start:.4f}s")

start = time.time()
from dotenv import load_dotenv
print(f"from dotenv import load_dotenv: {time.time() - start:.4f}s")

start = time.time()
load_dotenv()
print(f"load_dotenv(): {time.time() - start:.4f}s")

start = time.time()
import sys
import os
sys.path.append(os.getcwd())

start = time.time()
from utils.infrastructure.logging.unified_logging import replace_all_logging, logger
print(f"from utils...unified_logging: {time.time() - start:.4f}s")

start = time.time()
replace_all_logging()
print(f"replace_all_logging(): {time.time() - start:.4f}s")

start = time.time()
from utils.infrastructure.logging.kaia_logger import log_info
print(f"from utils...kaia_logger: {time.time() - start:.4f}s")

start = time.time()
import ollama
print(f"import ollama: {time.time() - start:.4f}s")

start = time.time()
import discord
print(f"import discord: {time.time() - start:.4f}s")

start = time.time()
from discord.ext import commands
print(f"from discord.ext import commands: {time.time() - start:.4f}s")

start = time.time()
from utils.infrastructure.system.shutdown_fixed import shutdown_manager
print(f"import shutdown_manager: {time.time() - start:.4f}s")

start = time.time()
from utils.infrastructure.monitoring.async_task_registry import task_registry
print(f"import task_registry: {time.time() - start:.4f}s")

start = time.time()
from utils.infrastructure.system.yaml_config import config
print(f"import config: {time.time() - start:.4f}s")

start = time.time()
from utils.infrastructure.system.bot_state import bot_state
print(f"import bot_state: {time.time() - start:.4f}s")

