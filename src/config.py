"""Central configuration loader for NotizieGeopolitica."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Project root is the parent of src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# Ollama
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# Quality model — used for comparator output, geopolitical gate, cluster title refinement.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:12b")
# Fast model — used for high-volume summarization and keyword extraction.
# This one carries ~90% of the nightly work (2 calls per article, ~420 articles).
FAST_MODEL = os.getenv("FAST_MODEL", "gemma4:e2b")
# Model reasoning. Gemma 4 reasons by default on Ollama and the reasoning is then
# discarded, so it costs time and buys nothing: measured at 30.9s → 5.4s per article
# on the summarize+keywords pair, and 25.8s → 1.2s on the YES/NO gates, same answers.
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false").lower() == "true"
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", OLLAMA_MODEL)  # fallback to main model if not set

# Paths
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "data/notizie.db")
CACHE_DIR = PROJECT_ROOT / os.getenv("CACHE_DIR", "data/cache")
SOURCES_FILE = PROJECT_ROOT / "src" / "collector" / "sources.yaml"

# Collector
FETCH_DELAY_SECONDS = int(os.getenv("FETCH_DELAY_SECONDS", "2"))
# Minimum body length for an article to be worth summarizing. Below this the
# scrape effectively failed (paywall, 403, Cloudflare) and the LLM has nothing
# to compress: asked anyway it answers "No content was provided in the article,
# therefore a summary cannot be generated." — which then got stored *as* the
# summary. Worse, those identical strings clustered together perfectly.
MIN_CONTENT_CHARS = int(os.getenv("MIN_CONTENT_CHARS", "100"))
USER_AGENT = os.getenv("USER_AGENT", "NotizieGeopolitica/1.0 (personal research project)")

# Hugo
HUGO_SITE_DIR = PROJECT_ROOT / os.getenv("HUGO_SITE_DIR", "site")
