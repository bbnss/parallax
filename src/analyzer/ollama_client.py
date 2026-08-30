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
    # Reasoning text Ollama returns only when think=True. With thinking left at
    # Ollama's default it is generated, billed in time, and then discarded — the
    # reason this pipeline used to spend 81-100% of its tokens on nothing.
    "thinking_chars": 0,
    # Responses cut off because num_predict ran out (reasoning eats the budget too).
    "truncated": 0,
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
    think=None,
    num_predict=2048,
):
    """Send a generation request to Ollama and return the response text.

    Args:
        prompt: The prompt string to send
        model: Model name (defaults to config.OLLAMA_MODEL)
        temperature: Sampling temperature (0.0–1.0)
        max_retries: Number of retries on failure
        timeout: Request timeout in seconds
        think: Enable model reasoning. None uses config.OLLAMA_THINK (off by
            default). Gemma 4 reasons by default and Ollama then discards the
            reasoning, so leaving this off is a 5-20x speedup at identical output
            on every task this pipeline runs.
        num_predict: Output token budget. Reasoning tokens count against it, so a
            thinking call can exhaust it and return a truncated answer.

    Returns:
        Generated text string, or empty string on failure
    """
    model = model or config.OLLAMA_MODEL
    if think is None:
        think = config.OLLAMA_THINK
    url = f"{config.OLLAMA_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": think,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }

    for attempt in range(1, max_retries + 1):
        try:
            response = _SESSION.post(url, json=payload, timeout=timeout)
            # Not every model accepts `think` (translategemma answers 400). Retry
            # once without it rather than letting the retry loop burn its attempts
            # and hand back an empty string.
            if (response.status_code == 400 and "think" in payload
                    and "does not support thinking" in response.text):
                logger.debug(f"Model {model} rejects the think parameter — retrying without it")
                payload.pop("think")
                response = _SESSION.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            text = data.get("response", "").strip()

            # Track tokens
            prompt_eval = data.get("prompt_eval_count", 0)
            eval_count = data.get("eval_count", 0)
            total_dur = data.get("total_duration", 0) / 1_000_000  # ns → ms
            thinking = data.get("thinking") or ""
            truncated = data.get("done_reason") == "length"

            with _token_lock:
                _token_stats["prompt_tokens"] += prompt_eval
                _token_stats["completion_tokens"] += eval_count
                _token_stats["total_tokens"] += prompt_eval + eval_count
                _token_stats["calls"] += 1
                _token_stats["total_duration_ms"] += total_dur
                _token_stats["thinking_chars"] += len(thinking)
                if truncated:
                    _token_stats["truncated"] += 1

            if truncated:
                logger.warning(
                    f"Ollama [{model}] hit the {num_predict}-token budget — the "
                    f"response is cut off mid-text. Raise num_predict for this call."
                )

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
    """Check if Ollama is running and the configured models are available."""
    try:
        resp = _SESSION.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        required = {config.OLLAMA_MODEL, config.FAST_MODEL}
        missing = [m for m in required if m not in models]
        if missing:
            logger.warning(
                f"Required model(s) not found: {missing}. Available: {models}"
            )
            return False
        return True
    except Exception as e:
        logger.error(f"Ollama not reachable at {config.OLLAMA_URL}: {e}")
        return False
