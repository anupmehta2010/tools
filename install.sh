#!/usr/bin/env bash
# tk one-shot installer (macOS / Linux).
#
#   curl -fsSL https://raw.githubusercontent.com/anupmehta2010/tools/main/install.sh | bash
#
# Or from a cloned checkout:
#   ./install.sh
#
# Flags:
#   MINIMAL=1    don't pip install anything; bundle only
#   NO_BUNDLE=1  don't build the .pyz
#   DEST=/path   install shim here (default: $HOME/.local/bin)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${DEST:-$HOME/.local/bin}"

echo "tk installer  (root: $ROOT)"

if ! command -v python3 >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PY=python
  else
    echo "Python not found. Install Python 3.10+." >&2
    exit 1
  fi
else
  PY=python3
fi
VER=$($PY -c "import sys; print('%d.%d' % sys.version_info[:2])")
echo "  $PY $VER  ($(command -v $PY))"

if [ "${MINIMAL:-0}" != "1" ] && [ -f "$ROOT/requirements.txt" ]; then
  echo "Installing optional Python deps (set MINIMAL=1 to skip)…"
  $PY -m pip install --quiet -r "$ROOT/requirements.txt" || true
fi

if [ "${NO_BUNDLE:-0}" != "1" ]; then
  echo "Building single-file tk.pyz…"
  $PY "$ROOT/tk.py" bundle zipapp -o "$ROOT/tk.pyz" >/dev/null
fi

mkdir -p "$DEST"
SHIM="$DEST/tk"
PYZ="$ROOT/tk.pyz"
[ "${NO_BUNDLE:-0}" = "1" ] && PYZ="$ROOT/tk.py"
cat > "$SHIM" <<EOF
#!/usr/bin/env bash
exec $PY "$PYZ" "\$@"
EOF
chmod +x "$SHIM"

case ":$PATH:" in
  *":$DEST:"*) ;;
  *) echo "  Add to your shell rc:  export PATH=\"$DEST:\$PATH\"" ;;
esac

echo
echo "Installed:  $SHIM"
echo "Try:        tk doctor   /   tk ui   /   tk --help"
