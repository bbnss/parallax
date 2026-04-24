#!/bin/bash
# deploy_site.sh — Push latest preview.html to gh-pages branch (GitHub Pages)
#
# Called by run_pipeline.sh after preview generation.
# Uses a temp clone to avoid disturbing the main working tree.

set -e

REPO_DIR="/Users/bbnss/kDrive2/Claude/NotizieGeopolitica"
PREVIEW="$REPO_DIR/data/preview.html"
DEPLOY_DIR="/tmp/parallax-deploy"
REPO_URL="https://github.com/bbnss/parallax.git"

if [ ! -f "$PREVIEW" ]; then
    echo "  [deploy] No preview.html found — skipping deploy"
    exit 0
fi

echo "  [deploy] Deploying to GitHub Pages..."

# Clean temp dir and shallow-clone gh-pages
rm -rf "$DEPLOY_DIR"
git clone --branch gh-pages --single-branch --depth 1 "$REPO_URL" "$DEPLOY_DIR" 2>/dev/null

# Copy preview as index.html
cp "$PREVIEW" "$DEPLOY_DIR/index.html"

cd "$DEPLOY_DIR"

# Check if anything changed
if git diff --quiet index.html 2>/dev/null; then
    echo "  [deploy] No changes — skipping"
    rm -rf "$DEPLOY_DIR"
    exit 0
fi

# Commit and push
git add index.html
git commit -m "Daily update $(date +%Y-%m-%d)"
git push

echo "  [deploy] Site updated: https://bbnss.github.io/parallax/"

# Cleanup
rm -rf "$DEPLOY_DIR"
