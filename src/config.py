"""Central configuration loader for NotizieGeopolitica."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Project root is the parent of src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# Ollama
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", OLLAMA_MODEL)  # fallback to main model if not set

# Paths
DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "data/notizie.db")
CACHE_DIR = PROJECT_ROOT / os.getenv("CACHE_DIR", "data/cache")
SOURCES_FILE = PROJECT_ROOT / "src" / "collector" / "sources.yaml"

# Collector
FETCH_DELAY_SECONDS = int(os.getenv("FETCH_DELAY_SECONDS", "2"))
USER_AGENT = os.getenv("USER_AGENT", "NotizieGeopolitica/1.0 (personal research project)")

# Hugo
HUGO_SITE_DIR = PROJECT_ROOT / os.getenv("HUGO_SITE_DIR", "site")
