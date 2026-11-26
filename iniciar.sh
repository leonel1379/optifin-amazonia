#!/usr/bin/env bash
# OptiFin Amazonía — arranque con un clic (Linux / macOS)
# Uso: doble clic (si el sistema lo permite) o en la terminal:  bash iniciar.sh
cd "$(dirname "$0")" || exit 1
if [ ! -f .venv/instalado.ok ]; then
  echo "Preparando el programa (solo la primera vez, 1 a 3 minutos)..."
  PY=""
  for c in python3.14 python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
      PY="$c"; break
    fi
  done
  if [ -z "$PY" ]; then
    echo "Se necesita Python 3.11 o superior: https://www.python.org/downloads/"
    exit 1
  fi
  "$PY" -m venv .venv || exit 1
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt || exit 1
  touch .venv/instalado.ok
fi
exec .venv/bin/python main.py "$@"
