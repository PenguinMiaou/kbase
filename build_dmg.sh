#!/bin/bash
# ============================================================
# KBase — Build macOS DMG Installer
# Usage: bash build_dmg.sh
# Output: dist/KBase-0.1.0.dmg
# ============================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="KBase"
VERSION="0.2.0"
DMG_NAME="${APP_NAME}-${VERSION}"

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║       KBase DMG Builder               ║"
echo "  ║       macOS Application Package       ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ── Step 1: Ensure venv and dependencies ──
echo -e "${YELLOW}[1/5] Setting up build environment...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip -q 2>/dev/null
pip install -e . -q 2>&1 | tail -2
pip install jieba pyinstaller -q 2>&1 | tail -2
echo -e "  ${GREEN}Build environment ready${NC}"

# ── Step 2: Create app icon from SVG ──
echo -e "${YELLOW}[2/5] Creating app icon...${NC}"
ICON_DIR="build/KBase.iconset"
mkdir -p "$ICON_DIR"

# Generate a simple icon using Python if no icon exists
if [ ! -f "build/KBase.icns" ]; then
    python3 - << 'PYEOF'
import os, struct

def create_png(size, path):
    """Create a minimal blue-gradient PNG with 'K' letter."""
    try:
        # Try using PIL if available
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Blue gradient circle
        for i in range(size):
            for j in range(size):
                cx, cy = size/2, size/2
                dist = ((i-cx)**2 + (j-cy)**2)**0.5
                r = size * 0.45
                if dist < r:
                    alpha = 255
                    blue = int(120 + 80 * (1 - dist/r))
                    img.putpixel((i, j), (30, 60, min(blue, 220), alpha))
        # Draw K
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", int(size*0.5))
        except:
            font = ImageFont.load_default()
        draw.text((size*0.28, size*0.18), "K", fill=(255, 255, 255, 255), font=font)
        img.save(path, 'PNG')
        return True
    except ImportError:
        return False

iconset = "build/KBase.iconset"
sizes = [16, 32, 64, 128, 256, 512]
ok = False
for s in sizes:
    ok = create_png(s, f"{iconset}/icon_{s}x{s}.png") or ok
    create_png(s*2, f"{iconset}/icon_{s}x{s}@2x.png")

if not ok:
    # Fallback: create 1x1 blue PNGs so iconutil doesn't fail
    import zlib
    def mini_png(path, size=16):
        # Minimal valid PNG: single blue pixel tiled
        header = b'\x89PNG\r\n\x1a\n'
        # IHDR
        ihdr_data = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
        ihdr_crc = struct.pack('>I', zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff)
        ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + ihdr_crc
        # IDAT
        raw = b''
        for _ in range(size):
            raw += b'\x00' + b'\x1e\x3c\xdc' * size  # blue pixels
        compressed = zlib.compress(raw)
        idat_crc = struct.pack('>I', zlib.crc32(b'IDAT' + compressed) & 0xffffffff)
        idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + idat_crc
        # IEND
        iend_crc = struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
        iend = struct.pack('>I', 0) + b'IEND' + iend_crc
        with open(path, 'wb') as f:
            f.write(header + ihdr + idat + iend)

    for s in sizes:
        mini_png(f"{iconset}/icon_{s}x{s}.png", s)
        mini_png(f"{iconset}/icon_{s}x{s}@2x.png", s*2)

print("Icon PNGs created")
PYEOF
    iconutil -c icns "$ICON_DIR" -o "build/KBase.icns" 2>/dev/null || echo "  iconutil skipped (icons optional)"
fi
echo -e "  ${GREEN}Icon ready${NC}"

# ── Step 3: PyInstaller build ──
echo -e "${YELLOW}[3/5] Building application with PyInstaller (this takes a few minutes)...${NC}"

# Clean previous build
rm -rf build/KBase dist/KBase dist/KBase.app 2>/dev/null

# Update spec to use icon if it exists
if [ -f "build/KBase.icns" ]; then
    sed -i '' "s|icon=None|icon='build/KBase.icns'|" kbase.spec 2>/dev/null || true
fi

pyinstaller kbase.spec --noconfirm 2>&1 | tail -5
echo -e "  ${GREEN}Application built${NC}"

# Verify .app exists
if [ ! -d "dist/KBase.app" ]; then
    echo -e "  ${RED}ERROR: KBase.app not found in dist/${NC}"
    echo "  Check build log above for errors"
    exit 1
fi

APP_SIZE=$(du -sh "dist/KBase.app" | cut -f1)
echo -e "  ${GREEN}KBase.app size: $APP_SIZE${NC}"

# ── Step 4: Create DMG ──
echo -e "${YELLOW}[4/5] Creating DMG installer...${NC}"

DMG_TMP="dist/${DMG_NAME}-tmp.dmg"
DMG_FINAL="dist/${DMG_NAME}.dmg"

# Remove old DMG
rm -f "$DMG_TMP" "$DMG_FINAL" 2>/dev/null

# Create staging directory
STAGING="dist/dmg-staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"

# Copy app to staging
cp -R "dist/KBase.app" "$STAGING/"

# Create Applications symlink
ln -s /Applications "$STAGING/Applications"

# Create README in staging
cat > "$STAGING/README.txt" << 'README'
KBase - Local Knowledge Base
Copyright@PenguinMiaou

Installation:
  Drag KBase.app to Applications folder.

First Launch:
  1. Open KBase from Applications
  2. Browser will open automatically at http://127.0.0.1:8765
  3. Go to Settings to configure your LLM API key
  4. Use Ingest tab to add your files

If macOS blocks the app:
  System Settings → Privacy & Security → Open Anyway
README

# Create DMG
hdiutil create -volname "$DMG_NAME" -srcfolder "$STAGING" -ov -format UDBZ "$DMG_FINAL"

# Clean up staging
rm -rf "$STAGING"

DMG_SIZE=$(du -sh "$DMG_FINAL" | cut -f1)
echo -e "  ${GREEN}DMG created: $DMG_FINAL ($DMG_SIZE)${NC}"

# ── Step 5: Verify ──
echo -e "${YELLOW}[5/5] Verifying package...${NC}"
hdiutil verify "$DMG_FINAL" 2>/dev/null && echo -e "  ${GREEN}DMG verified OK${NC}" || echo -e "  ${YELLOW}Verify skipped${NC}"

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Build complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Output: $DMG_FINAL"
echo "  Size:   $DMG_SIZE"
echo ""
echo "  To install: Double-click the DMG, drag KBase to Applications"
echo "  To share:   Send the DMG file to colleagues"
echo ""
