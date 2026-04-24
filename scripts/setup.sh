#!/bin/bash
# First-time setup for NotizieGeopolitica

set -e

cd "$(dirname "$0")/.."
echo "Setting up NotizieGeopolitica..."

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install via: brew install python"
    exit 1
fi

# Create venv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create data dirs
mkdir -p data/cache

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  source .venv/bin/activate"
echo "  python -m src.cli status"
echo "  python -m src.cli collect --skip-scrape  # quick test"
echo "  python -m src.cli collect                 # full collection"
