#!/usr/bin/env bash
# =============================================================================
#  Ribbon Tracker — local macOS build
# =============================================================================
#  Produces dist/RibbonTracker.app and refreshes the copy at
#  ~/Desktop/RibbonTracker.app so you can double-click it.
#
#  PYTHON CHOICE — uses the Mac's built-in /usr/bin/python3 (3.9.x). Any Python
#  BELOW 3.12 works because we pin setuptools==65.5.1, and 3.12 removed
#  pkgutil.ImpImporter which that setuptools needs. Don't build on 3.12+.
#
#  Build deps install into the user site (~/Library/Python/3.9/...) via
#  `pip install --user`, NOT a venv. Matches the SpliceReport / Secret Sauce
#  pattern.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PY="/usr/bin/python3"
if [[ ! -x "$PY" ]]; then
    echo "[build-mac] ERROR — /usr/bin/python3 missing. Run: xcode-select --install" >&2
    exit 1
fi
PY_VER=$("$PY" --version 2>&1)
echo "[build-mac] Using: $PY ($PY_VER)"

if "$PY" -c "import sys; sys.exit(0 if sys.version_info < (3, 12) else 1)"; then
    :
else
    echo "[build-mac] ERROR — $PY_VER is 3.12+ which removed pkgutil.ImpImporter." >&2
    echo "             setuptools 65.5.1 (our pin) needs it at boot. Use Python < 3.12." >&2
    exit 1
fi

# ── 1. Install build deps into the user site (idempotent) ────────────────────
"$PY" -m pip install --user --upgrade pip wheel >/dev/null
"$PY" -m pip install --user -r requirements-desktop.txt
"$PY" -m pip install --user --force-reinstall "setuptools==65.5.1"

USER_BIN="$("$PY" -m site --user-base)/bin"
export PATH="$USER_BIN:$PATH"

# ── 2. PyInstaller build ─────────────────────────────────────────────────────
rm -rf build dist
"$PY" -m PyInstaller RibbonTracker-mac.spec --noconfirm --clean

if [[ ! -d "dist/RibbonTracker.app" ]]; then
    echo "[build-mac] ERROR — dist/RibbonTracker.app missing after PyInstaller." >&2
    exit 1
fi

# ── 3. Refresh the .app on the Desktop ──────────────────────────────────────
DEST="$HOME/Desktop/RibbonTracker.app"
if [[ -d "$DEST" ]]; then
    echo "[build-mac] Replacing existing $DEST ..."
    rm -rf "$DEST"
fi
cp -R "dist/RibbonTracker.app" "$DEST"

# Strip the quarantine bit so Gatekeeper only nags once on YOUR Mac.
xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true

echo
echo "[build-mac] ============================================================"
echo "[build-mac]  Build OK."
echo "[build-mac]    Source : $HERE/dist/RibbonTracker.app"
echo "[build-mac]    Desktop: $DEST"
echo "[build-mac] ============================================================"
echo "[build-mac]  Gatekeeper note for the FIRST run on a fresh Mac:"
echo "[build-mac]    right-click RibbonTracker.app → Open → Open (one-time)"
echo "[build-mac]    or:  xattr -dr com.apple.quarantine '$DEST'"
echo "[build-mac] ============================================================"
