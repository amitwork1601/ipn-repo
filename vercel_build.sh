#!/bin/bash
set -e  # Exit on error

echo "Installing Python dependencies..."
pip install -r requirements.txt --break-system-packages

echo "Generating Documentation..."
python generate_docs.py

echo "Ensure Explorer page exists..."
cp viewer_assets/explorer.md docs/ 2>/dev/null || true

echo "Building Website with MkDocs..."
# Use python -m mkdocs to ensure we use the installed module
python -m mkdocs build --clean --site-dir site

echo "Copying raw markdown for Interactive Explorer..."
cp docs/*.md site/ 2>/dev/null || true

echo "Build Complete!"
