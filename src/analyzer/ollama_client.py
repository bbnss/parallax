"""Thin wrapper around the Ollama REST API for NotizieGeopolitica.

Tracks cumulative token usage across all calls in a session.
"""

import json
import logging
import time
import threading

import requests

from src import config

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"Content-Type": "application/json"})

# ── Token tracking ──────────────────────────────────────────────────────────
_token_lock = threading.Lock()
_token_stats = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "calls": 0,
    "errors": 0,
    "total_duration_ms": 0,
}


def get_token_stats():
    """Return a copy of cumulative token statistics."""
    with _token_lock:
        return dict(_token_stats)


def reset_token_stats():
    """Reset token counters (e.g. at pipeline start)."""
    with _token_lock:
        for k in _token_stats:
            _token_stats[k] = 0


def generate(
    prompt,
    model=None,
    temperature=0.3,
    max_retries=3,
    timeout=120,
):
    """Send a generation request to Ollama and return the response text.

    Args:
        prompt: The prompt string to send
        model: Model name (defaults to config.OLLAMA_MODEL)
        temperature: Sampling temperature (0.0–1.0)
        max_retries: Number of retries on failure
        timeout: Request timeout in seconds

    Returns:
        Generated text string, or empty string on failure
    """
    model = model or config.OLLAMA_MODEL
    url = f"{config.OLLAMA_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 2048,
        },
    }

    for attempt in range(1, max_retries + 1):
        try:
            response = _SESSION.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            text = data.get("response", "").strip()

            # Track tokens
            prompt_eval = data.get("prompt_eval_count", 0)
            eval_count = data.get("eval_count", 0)
            total_dur = data.get("total_duration", 0) / 1_000_000  # ns → ms

            with _token_lock:
                _token_stats["prompt_tokens"] += prompt_eval
                _token_stats["completion_tokens"] += eval_count
                _token_stats["total_tokens"] += prompt_eval + eval_count
                _token_stats["calls"] += 1
                _token_stats["total_duration_ms"] += total_dur

            logger.debug(
                f"Ollama [{model}] {len(text)} chars, "
                f"in={prompt_eval} out={eval_count} tokens, "
                f"{total_dur:.0f}ms"
            )
            return text

        except requests.exceptions.Timeout:
            with _token_lock:
                _token_stats["errors"] += 1
            logger.warning(f"Ollama timeout on attempt {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(5 * attempt)
        except requests.exceptions.RequestException as e:
            with _token_lock:
                _token_stats["errors"] += 1
            logger.warning(f"Ollama request failed on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                time.sleep(3 * attempt)

    logger.error(f"Ollama failed after {max_retries} attempts for prompt: {prompt[:80]}...")
    return ""


def is_available():
    """Check if Ollama is running and the configured model is available."""
    try:
        resp = _SESSION.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        available = config.OLLAMA_MODEL in models
        if not available:
            logger.warning(
                f"Model '{config.OLLAMA_MODEL}' not found. Available: {models}"
            )
        return available
    except Exception as e:
        logger.error(f"Ollama not reachable at {config.OLLAMA_URL}: {e}")
        return False
