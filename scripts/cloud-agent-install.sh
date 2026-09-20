#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the naver-chatbot FastAPI app.
set -euo pipefail

cd "$(dirname "$0")/.."

# Python 3.12 ships without the venv module on the base image; ensure it exists.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "cloud-agent-install: dependencies ready"
