#!/bin/bash
# ============================================================
# KBase - One-Click Install Script (macOS / Linux)
# Uses uv for fast, reliable Python + dependency management
# ============================================================
set -e

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║          KBase Installer v0.7         ║"
echo "  ║   Local Knowledge Base System         ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

UV_BIN="$HOME/.local/bin/uv"

# Step 1: Install uv (fast Python package manager)
echo -e "${YELLOW}[1/4] Setting up uv package manager...${NC}"
if command -v uv &> /dev/null; then
    echo -e "  ${GREEN}Found: $(uv --version)${NC}"
elif [ -f "$UV_BIN" ]; then
    echo -e "  ${GREEN}Found: $($UV_BIN --version)${NC}"
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "  Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo -e "  ${GREEN}Installed: $(uv --version)${NC}"
fi

# Step 2: Install KBase
echo -e "${YELLOW}[2/4] Installing KBase + Python 3.12...${NC}"

# Check if installing from local source or PyPI
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/pyproject.toml" ] && grep -q "kbase-app" "$SCRIPT_DIR/pyproject.toml" 2>/dev/null; then
    # Local source install
    echo "  Installing from local source..."
    uv tool install --from "$SCRIPT_DIR" kbase-app --python 3.12 --force 2>&1 | tail -5
else
    # PyPI install
    echo "  Installing from PyPI..."
    uv tool install kbase-app --python 3.12 --force 2>&1 | tail -5
fi
echo -e "  ${GREEN}KBase installed${NC}"

# Step 3: Desktop integration (optional pywebview)
echo -e "${YELLOW}[3/4] Setting up desktop mode...${NC}"
# Install pywebview for native window
UV_TOOL_DIR="$HOME/.local/share/uv/tools/kbase-app"
if [ -d "$UV_TOOL_DIR" ]; then
    uv pip install --python "$UV_TOOL_DIR/bin/python3" pywebview 2>&1 | tail -3
    echo -e "  ${GREEN}Desktop mode ready (native window)${NC}"
else
    echo -e "  ${YELLOW}Skipped — will use browser mode${NC}"
fi

# Step 4: LibreOffice check
echo -e "${YELLOW}[4/4] Checking LibreOffice...${NC}"
if command -v soffice &> /dev/null; then
    echo -e "  ${GREEN}LibreOffice found${NC}"
else
    echo -e "  ${YELLOW}Not found — file preview will use fallback mode${NC}"
    if [[ "$(uname)" == "Darwin" ]] && command -v brew &> /dev/null; then
        echo "  Tip: brew install --cask libreoffice"
    fi
fi

# Create desktop shortcut on macOS
if [[ "$(uname)" == "Darwin" ]]; then
    SHORTCUT="$HOME/Desktop/KBase.command"
    cat > "$SHORTCUT" << 'EOF'
#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
echo "Starting KBase..."
kbase-desktop 2>/dev/null || kbase web
EOF
    chmod +x "$SHORTCUT"
    echo -e "  ${GREEN}Desktop shortcut created: KBase.command${NC}"
fi

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Installation complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Commands:"
echo ""
echo "  kbase web                  # Start Web UI (browser)"
echo "  kbase-desktop              # Start Desktop App (native window)"
echo "  kbase ingest /path/files   # Index files"
echo "  kbase search \"query\"       # Search"
echo ""
echo "  Data stored in: ~/.kbase/"
echo "  Docs: https://github.com/PenguinMiaou/kbase"
echo ""

# Add to PATH hint
if ! command -v kbase &> /dev/null; then
    echo -e "${YELLOW}  Add to PATH:${NC}"
    echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
    echo ""
fi
