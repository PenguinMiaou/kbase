#!/bin/bash
# ============================================================
# KBase Release Script — bump version, build, deploy, verify
# Usage:
#   bash release.sh patch          # 0.2.0 → 0.2.1
#   bash release.sh minor          # 0.2.0 → 0.3.0
#   bash release.sh major          # 0.2.0 → 1.0.0
#   bash release.sh deploy         # deploy current build to remote
#   bash release.sh verify         # verify remote is running
#   bash release.sh debug          # show remote stderr
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

# Remote config (override with env vars)
REMOTE_HOST="${KBASE_REMOTE_HOST:-172.20.10.3}"
REMOTE_USER="${KBASE_REMOTE_USER:-yanyan}"
REMOTE_PASS="${KBASE_REMOTE_PASS:-314151}"
SSH="sshpass -p '$REMOTE_PASS' ssh -o StrictHostKeyChecking=no $REMOTE_USER@$REMOTE_HOST"
SCP="sshpass -p '$REMOTE_PASS' scp"

# ---- Get current version ----
CUR_VER=$(python3 -c "exec(open('kbase/__init__.py').read()); print(__version__)")
IFS='.' read -r MAJOR MINOR PATCH <<< "$CUR_VER"

case "$1" in
  patch)
    PATCH=$((PATCH + 1))
    NEW_VER="$MAJOR.$MINOR.$PATCH"
    ;;
  minor)
    MINOR=$((MINOR + 1))
    PATCH=0
    NEW_VER="$MAJOR.$MINOR.$PATCH"
    ;;
  major)
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
    NEW_VER="$MAJOR.$MINOR.$PATCH"
    ;;
  deploy)
    # Skip version bump, just deploy existing DMG
    DMG=$(ls -t dist/KBase-*.dmg 2>/dev/null | head -1)
    if [ -z "$DMG" ]; then echo -e "${RED}No DMG found in dist/${NC}"; exit 1; fi
    echo -e "${YELLOW}Deploying $DMG to $REMOTE_USER@$REMOTE_HOST...${NC}"
    eval "$SSH 'pkill -f KBase 2>/dev/null; lsof -ti:8765 | xargs kill 2>/dev/null; true'"
    eval "$SCP '$DMG' $REMOTE_USER@$REMOTE_HOST:/tmp/kbase-update.dmg"
    eval "$SSH '
      hdiutil attach /tmp/kbase-update.dmg -nobrowse -quiet
      VOL=\$(ls /Volumes/ | grep KBase | head -1)
      rm -rf /Applications/KBase.app
      cp -R \"/Volumes/\$VOL/KBase.app\" /Applications/
      hdiutil detach \"/Volumes/\$VOL\" -quiet
      rm /tmp/kbase-update.dmg
      open /Applications/KBase.app
      echo \"Deployed and launched\"
    '"
    sleep 5
    eval "$SSH 'curl -s http://127.0.0.1:8765/api/version'" && echo ""
    exit 0
    ;;
  verify)
    echo -e "${YELLOW}Verifying remote KBase...${NC}"
    eval "$SSH '
      echo \"=== version ===\"
      curl -s http://127.0.0.1:8765/api/version
      echo \"\"
      echo \"=== ingest-dirs ===\"
      curl -s http://127.0.0.1:8765/api/ingest-dirs 2>&1 | head -100
      echo \"\"
      echo \"=== search ===\"
      curl -s \"http://127.0.0.1:8765/api/search?q=test&type=keyword&top_k=1\" 2>&1 | head -100
    '"
    exit 0
    ;;
  debug)
    echo -e "${YELLOW}Remote stderr (last 30 lines):${NC}"
    eval "$SSH '
      pkill -f KBase 2>/dev/null; lsof -ti:8765 | xargs kill 2>/dev/null; sleep 1
      /Applications/KBase.app/Contents/MacOS/KBase > /tmp/kbase-out.log 2> /tmp/kbase-err.log &
      sleep 4
      curl -s http://127.0.0.1:8765/api/version 2>/dev/null
      curl -s -X POST http://127.0.0.1:8765/api/chat -H \"Content-Type: application/json\" -d \"{\\\"question\\\":\\\"hi\\\"}\" 2>/dev/null | head -50
      echo \"\"
      echo \"=== STDERR ===\"
      tail -30 /tmp/kbase-err.log
    '"
    exit 0
    ;;
  *)
    echo "Usage: bash release.sh [patch|minor|major|deploy|verify|debug]"
    echo "  Current version: $CUR_VER"
    exit 0
    ;;
esac

echo -e "${YELLOW}Bumping version: $CUR_VER → $NEW_VER${NC}"

# ---- 1. Bump version in all files ----
echo -e "${YELLOW}[1/5] Updating version references...${NC}"
sed -i '' "s/__version__ = \"$CUR_VER\"/__version__ = \"$NEW_VER\"/" kbase/__init__.py
sed -i '' "s/\"version\": \"$CUR_VER\"/\"version\": \"$NEW_VER\"/" version.json
# Update download URLs in version.json
sed -i '' "s|/v$CUR_VER/|/v$NEW_VER/|g" version.json
sed -i '' "s/KBase-$CUR_VER/KBase-$NEW_VER/g" version.json
sed -i '' "s/version=\"$CUR_VER\"/version=\"$NEW_VER\"/" setup.py
sed -i '' "s/VERSION=\"$CUR_VER\"/VERSION=\"$NEW_VER\"/" build_dmg.sh
sed -i '' "s/'CFBundleVersion': '$CUR_VER'/'CFBundleVersion': '$NEW_VER'/" kbase.spec
sed -i '' "s/'CFBundleShortVersionString': '$CUR_VER'/'CFBundleShortVersionString': '$NEW_VER'/" kbase.spec
echo -e "  ${GREEN}Version updated to $NEW_VER${NC}"

# ---- 2. Git commit + push ----
echo -e "${YELLOW}[2/5] Committing and pushing...${NC}"
git add -A
git commit -m "release: v$NEW_VER

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>" || true
git push origin main
echo -e "  ${GREEN}Pushed to GitHub${NC}"

# ---- 3. Build DMG ----
echo -e "${YELLOW}[3/5] Building DMG...${NC}"
source .venv/bin/activate 2>/dev/null || true
rm -rf build/kbase dist/KBase.app dist/KBase
pyinstaller kbase.spec --noconfirm 2>&1 | tail -3
STAGING=dist/dmg-staging
rm -rf "$STAGING" && mkdir -p "$STAGING"
cp -R dist/KBase.app "$STAGING/"
ln -s /Applications "$STAGING/Applications"
DMG="dist/KBase-$NEW_VER.dmg"
rm -f "$DMG"
hdiutil create -volname "KBase-$NEW_VER" -srcfolder "$STAGING" -ov -format UDBZ "$DMG"
rm -rf "$STAGING"
echo -e "  ${GREEN}Built: $DMG ($(du -sh "$DMG" | cut -f1))${NC}"

# ---- 4. Deploy to remote ----
echo -e "${YELLOW}[4/5] Deploying to remote...${NC}"
eval "$SSH 'pkill -f KBase 2>/dev/null; lsof -ti:8765 | xargs kill 2>/dev/null; true'"
eval "$SCP '$DMG' $REMOTE_USER@$REMOTE_HOST:/tmp/kbase-update.dmg"
eval "$SSH '
  hdiutil attach /tmp/kbase-update.dmg -nobrowse -quiet
  VOL=\$(ls /Volumes/ | grep KBase | head -1)
  rm -rf /Applications/KBase.app
  cp -R \"/Volumes/\$VOL/KBase.app\" /Applications/
  hdiutil detach \"/Volumes/\$VOL\" -quiet
  rm /tmp/kbase-update.dmg
  open /Applications/KBase.app
  echo \"Deployed\"
'"
echo -e "  ${GREEN}Deployed to $REMOTE_HOST${NC}"

# ---- 5. Verify ----
echo -e "${YELLOW}[5/5] Verifying...${NC}"
sleep 5
REMOTE_VER=$(eval "$SSH 'curl -s http://127.0.0.1:8765/api/version'" 2>/dev/null)
echo "  Remote: $REMOTE_VER"

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  v$NEW_VER released and deployed!${NC}"
echo -e "${GREEN}============================================${NC}"
