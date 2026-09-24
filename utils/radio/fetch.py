"""One polite HTTP GET for the radio feeds, plus the on-disk cache they share."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import aiohttp

from utils.core.atomic_write import write_atomic
from utils.core.sanitizer import read_capped
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

USER_AGENT = "Kaiacord/1.0 (self-hosted Discord bot; polls every few hours; github.com/Ekco-S64QTN6/Kaiacord)"
TIMEOUT_S = 20
MAX_BYTES = 2_000_000
CACHE_DIR = "memory/radio"


class FeedError(Exception):
    """A feed did not answer the way it is expected to. Said out loud, never
    folded into an empty result that would read as 'no traffic'."""


async def get_json(url: str, params: Optional[dict] = None) -> Any:
    from utils.core.sanitizer import public_only_connector
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_S)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers,
                                         connector=public_only_connector()) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    raise FeedError(f"{url} answered HTTP {resp.status}")
                raw = await read_capped(resp, MAX_BYTES)
    except FeedError:
        raise
    except Exception as e:
        raise FeedError(f"{url}: {type(e).__name__}: {e}") from e
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError as e:
        raise FeedError(f"{url} did not return JSON") from e


def cache_path(name: str) -> Path:
    return Path(telemetry_path(f"{CACHE_DIR}/{name}.json"))


def read_cache(name: str) -> dict:
    try:
        return json.loads(cache_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_cache(name: str, data: dict) -> None:
    data = {**data, "fetched_at": time.time()}
    write_atomic(cache_path(name), json.dumps(data, indent=1))


def is_stale(cache: dict, max_age_s: float) -> bool:
    return time.time() - float(cache.get("fetched_at", 0)) > max_age_s
