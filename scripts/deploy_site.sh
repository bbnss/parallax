#!/bin/bash
# deploy_site.sh — Publish the built site to the gh-pages branch (GitHub Pages)
#
# Called by run_pipeline.sh after preview generation. The site is no longer a
# single index.html: it is a directory (home page, feeds, and an append-only
# archive of monthly shards plus one file per analysis). Uses a temp clone so
# the main working tree is never disturbed.

set -e

SITE_DIR="${PARALLAX_SITE_DIR:-$HOME/parallax-data/site}"
DEPLOY_DIR="${PARALLAX_DEPLOY_DIR:-/tmp/parallax-deploy}"
# Overridable so the deploy can be rehearsed against a local clone.
REPO_URL="${PARALLAX_REPO_URL:-https://github.com/bbnss/parallax.git}"

if [ ! -f "$SITE_DIR/index.html" ]; then
    echo "  [deploy] No site at $SITE_DIR — skipping deploy"
    exit 0
fi

echo "  [deploy] Deploying $SITE_DIR to GitHub Pages..."

rm -rf "$DEPLOY_DIR"
git clone --branch gh-pages --single-branch --depth 1 "$REPO_URL" "$DEPLOY_DIR" 2>/dev/null

# The archive is append-only and the live branch is its only backup. A build
# that somehow lost history must never be allowed to publish that loss, so
# refuse when the local archive holds fewer stories than the published one.
live_manifest="$DEPLOY_DIR/archive/manifest.json"
local_manifest="$SITE_DIR/archive/manifest.json"
if [ ! -f "$local_manifest" ]; then
    echo "  [deploy] ABORT: $local_manifest is missing — refusing to publish a partial build"
    rm -rf "$DEPLOY_DIR"
    exit 1
fi
if [ -f "$live_manifest" ]; then
    live_total=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('total',0))" "$live_manifest")
    local_total=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('total',0))" "$local_manifest")
    if [ "$local_total" -lt "$live_total" ]; then
        echo "  [deploy] ABORT: local archive has $local_total stories, live has $live_total"
        echo "  [deploy] Restore $SITE_DIR from the gh-pages branch before deploying again."
        rm -rf "$DEPLOY_DIR"
        exit 1
    fi
fi

# No --delete: the archive only ever grows, and a mistake here would erase
# published history that exists nowhere else.
rsync -a "$SITE_DIR"/ "$DEPLOY_DIR"/ --exclude '.git'

cd "$DEPLOY_DIR"
git add -A

if git diff --cached --quiet; then
    echo "  [deploy] No changes — skipping"
    rm -rf "$DEPLOY_DIR"
    exit 0
fi

echo "  [deploy] Publishing: $(git diff --cached --numstat | wc -l | tr -d ' ') file(s) changed"
git commit -q -m "Daily update $(date +%Y-%m-%d)"
git push -q

echo "  [deploy] Site updated: https://bbnss.github.io/parallax/"

rm -rf "$DEPLOY_DIR"
