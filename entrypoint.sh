#!/bin/bash
set -e

# Default to running generation if not specified, or if explicit 'true'
if [ "$GENERATE_ON_START" = "true" ]; then
    echo "[Entrypoint] Running documentation generation..."
    python generate_docs.py
else
    echo "[Entrypoint] Skipping generation (GENERATE_ON_START is not true)."
fi

echo "[Entrypoint] Building MkDocs site..."
# Build to the Nginx html directory
mkdocs build -d /usr/share/nginx/html

echo "[Entrypoint] Starting Nginx..."
exec nginx -g "daemon off;"
