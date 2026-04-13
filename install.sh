#!/bin/bash
# ============================================================
# KBase - One-Click Install Script (macOS / Linux)
# ============================================================
set -e

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║          KBase Installer              ║"
echo "  ║   Local Knowledge Base System         ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check Python
echo -e "${YELLOW}[1/5] Checking Python...${NC}"
if command -v python3 &> /dev/null; then
    PY_VER=$(python3 --version 2>&1)
    echo -e "  ${GREEN}Found: $PY_VER${NC}"
else
    echo -e "  ${RED}Python 3 not found!${NC}"
    echo "  Please install Python 3.9+ first:"
    echo "    macOS: brew install python@3.10"
    echo "    Linux: sudo apt install python3 python3-pip"
    exit 1
fi

# Check Python version >= 3.9
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MINOR" -lt 9 ]; then
    echo -e "  ${RED}Python 3.9+ required (found 3.$PY_MINOR)${NC}"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Create virtual environment
echo -e "${YELLOW}[2/5] Creating virtual environment...${NC}"
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    python3 -m venv "$SCRIPT_DIR/.venv"
    echo -e "  ${GREEN}Created .venv${NC}"
else
    echo -e "  ${GREEN}Using existing .venv${NC}"
fi

# Activate venv
source "$SCRIPT_DIR/.venv/bin/activate"

# Install dependencies
echo -e "${YELLOW}[3/5] Installing dependencies (this may take a few minutes)...${NC}"
pip install --upgrade pip -q 2>/dev/null
echo "  Installing core packages..."
pip install -e "$SCRIPT_DIR" -q 2>&1 | tail -3
echo "  Installing search enhancements (jieba + reranker)..."
pip install jieba FlagEmbedding -q 2>&1 | tail -3
echo -e "  ${GREEN}Dependencies installed${NC}"

# Install LibreOffice for file preview (PPTX/DOCX/XLSX -> PDF)
echo -e "${YELLOW}[4/6] Checking LibreOffice (for file preview)...${NC}"
if command -v soffice &> /dev/null; then
    echo -e "  ${GREEN}LibreOffice found${NC}"
else
    echo "  LibreOffice not found — needed for PPTX/DOCX preview"
    if [[ "$(uname)" == "Darwin" ]]; then
        if command -v brew &> /dev/null; then
            echo "  Installing via Homebrew (this may take a few minutes)..."
            brew install --cask libreoffice 2>&1 | tail -3
            echo -e "  ${GREEN}LibreOffice installed${NC}"
        else
            echo -e "  ${YELLOW}Install manually: brew install --cask libreoffice${NC}"
            echo -e "  ${YELLOW}Or download from: https://www.libreoffice.org/download${NC}"
        fi
    elif command -v apt-get &> /dev/null; then
        echo "  Installing via apt..."
        sudo apt-get install -y libreoffice-core 2>&1 | tail -3
        echo -e "  ${GREEN}LibreOffice installed${NC}"
    else
        echo -e "  ${YELLOW}Install manually from: https://www.libreoffice.org/download${NC}"
    fi
fi

# Create CLI wrapper
echo -e "${YELLOW}[5/6] Creating CLI shortcut...${NC}"
WRAPPER="$SCRIPT_DIR/kbase-cli"
cat > "$WRAPPER" << 'WRAPPER_EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
python3 -m kbase.cli "$@"
WRAPPER_EOF
chmod +x "$WRAPPER"
echo -e "  ${GREEN}Created: $WRAPPER${NC}"

# Quick test
echo -e "${YELLOW}[6/6] Running quick test...${NC}"
python3 -c "from kbase.store import KBaseStore; print('  All modules OK')" 2>/dev/null || echo -e "  ${RED}Module test failed${NC}"

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Installation complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Quick Start:"
echo ""
echo "  1. Index your files:"
echo "     ./kbase-cli ingest /path/to/your/files"
echo ""
echo "  2. Search:"
echo "     ./kbase-cli search \"your question\""
echo ""
echo "  3. Launch Web UI:"
echo "     ./kbase-cli web"
echo "     Then open http://localhost:8765"
echo ""
echo "  4. Get JSON output (for LLM/scripts):"
echo "     ./kbase-cli -f json search \"query\""
echo ""
echo "  For full docs: cat $SCRIPT_DIR/README.md"
echo ""

# Optional: add to PATH
if [[ ":$PATH:" != *":$SCRIPT_DIR:"* ]]; then
    echo -e "${YELLOW}  Tip: Add to PATH for global access:${NC}"
    echo "    echo 'export PATH=\"$SCRIPT_DIR:\$PATH\"' >> ~/.zshrc"
    echo "    source ~/.zshrc"
    echo ""
fi
