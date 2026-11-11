#!/usr/bin/env bash
set -euo pipefail

MIN_PYTHON="3.11"

python_is_supported() {
  "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
    >/dev/null 2>&1
}

if [ -d .venv ]; then
  if [ ! -x .venv/bin/python ] || ! python_is_supported .venv/bin/python; then
    echo "ERROR: The existing .venv was created with an unsupported Python version."
    echo "This project requires Python ${MIN_PYTHON} or newer."
    echo
    echo "Remove the old environment and run verification again:"
    echo "  rm -rf .venv"
    echo "  ./scripts/verify.sh"
    exit 1
  fi
else
  PYTHON=""

  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_is_supported "$candidate"; then
      PYTHON="$candidate"
      break
    fi
  done

  if [ -z "$PYTHON" ]; then
    echo "ERROR: Python ${MIN_PYTHON} or newer is required."
    echo "Install a supported Python version, then run this script again."
    exit 1
  fi

  echo "Creating .venv with $("$PYTHON" --version)..."
  "$PYTHON" -m venv .venv
fi

source .venv/bin/activate

echo "Using $(python --version)"

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

rm -rf instance
python seed.py
python -m pytest

echo
echo "Verification complete. Start the app with:"
echo "  source .venv/bin/activate"
echo "  flask --app store run --debug"