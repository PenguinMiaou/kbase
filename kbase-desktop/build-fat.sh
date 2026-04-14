#!/bin/bash
# ============================================================
# Build KBase Fat DMG — offline installer with bundled Python
# Produces: ~500MB .app with everything included
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
UV="${HOME}/.local/bin/uv"
PYTHON_VER="3.12"
VENV_DIR="${SCRIPT_DIR}/src-tauri/python-env"

echo "=== KBase Fat Build ==="
echo ""

# Step 1: Ensure uv is available
if [ ! -f "$UV" ]; then
    echo "[1/5] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
echo "[1/5] uv ready"

# Step 2: Create isolated Python venv with all deps
echo "[2/5] Creating Python environment (Python ${PYTHON_VER})..."
rm -rf "$VENV_DIR"
"$UV" venv "$VENV_DIR" --python "$PYTHON_VER"

# Step 3: Install kbase-app into the venv
echo "[3/5] Installing kbase-app + dependencies..."
"$UV" pip install --python "$VENV_DIR/bin/python3" \
    -e "$PROJECT_DIR" \
    pywebview jieba xlrd lxml 2>&1 | tail -5
echo "  Installed $(${VENV_DIR}/bin/python3 -c 'import kbase; print(f"kbase {kbase.__version__}")')"

# Step 4: Pre-download embedding model
echo "[4/5] Pre-downloading embedding model..."
"$VENV_DIR/bin/python3" -c "
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('BAAI/bge-small-zh-v1.5')
print(f'  Model ready: {m.get_sentence_embedding_dimension()}d')
"

# Step 5: Build Tauri app (it will pick up python-env from Resources)
echo "[5/5] Building Tauri app..."

# Copy python-env into the resource location Tauri will bundle
mkdir -p "${SCRIPT_DIR}/src-tauri/python-env"

# Update tauri.conf.json to include python-env in resources
npx tauri build 2>&1 | tail -5

# Now manually inject python-env into the built .app
APP_DIR="${SCRIPT_DIR}/src-tauri/target/release/bundle/macos/KBase.app"
if [ -d "$APP_DIR" ]; then
    echo "  Injecting Python environment into app bundle..."
    cp -R "$VENV_DIR" "$APP_DIR/Contents/Resources/python-env"

    # Fix shebangs in venv scripts to use relative paths
    for f in "$APP_DIR/Contents/Resources/python-env/bin/"*; do
        if [ -f "$f" ] && head -1 "$f" | grep -q "python"; then
            sed -i '' "1s|.*|#!/usr/bin/env python3|" "$f" 2>/dev/null || true
        fi
    done

    echo "  App size: $(du -sh "$APP_DIR" | cut -f1)"
fi

# Recreate DMG with fat app
DMG_DIR="${SCRIPT_DIR}/src-tauri/target/release/bundle/dmg"
VERSION=$(grep '"version"' "${SCRIPT_DIR}/src-tauri/tauri.conf.json" | head -1 | sed 's/.*: "//;s/".*//')
FAT_DMG="${DMG_DIR}/KBase_${VERSION}_aarch64_full.dmg"

echo "  Creating fat DMG..."
STAGING=$(mktemp -d)
cp -R "$APP_DIR" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
hdiutil create -volname "KBase-${VERSION}" -srcfolder "$STAGING" -ov -format UDBZ "$FAT_DMG" 2>&1 | tail -1
rm -rf "$STAGING"

echo ""
echo "=== Build Complete ==="
echo "  Lite DMG: ${DMG_DIR}/KBase_${VERSION}_aarch64.dmg ($(du -sh "${DMG_DIR}/KBase_${VERSION}_aarch64.dmg" 2>/dev/null | cut -f1))"
echo "  Full DMG: ${FAT_DMG} ($(du -sh "$FAT_DMG" | cut -f1))"
echo ""

# Cleanup venv from src-tauri (not needed after build)
rm -rf "$VENV_DIR"
