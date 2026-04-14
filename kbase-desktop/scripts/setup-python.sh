#!/bin/bash
# KBase Python Environment Bootstrap (macOS/Linux)
# Called by Tauri on first launch to install Python + kbase
set -e

KBASE_HOME="$HOME/.kbase"
UV_BIN="$HOME/.local/bin/uv"

echo "[KBase] Setting up Python environment..."

# Install uv if missing
if [ ! -f "$UV_BIN" ]; then
    echo "[KBase] Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Install kbase via uv tool
echo "[KBase] Installing KBase..."
"$UV_BIN" tool install kbase-app --python 3.12

echo "[KBase] Setup complete!"
