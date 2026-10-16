#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
VENV="$ROOT/.venv"
if [ ! -x "$VENV/bin/python" ]; then "$PY" -m venv "$VENV"; fi
VPY="$VENV/bin/python"
"$VPY" -m pip install --disable-pip-version-check -q -r requirements.txt
"$VPY" -m pip check
mkdir -p .local-qa
"$VPY" -m unittest discover -s tests -p 'test_*.py' -v > .local-qa/UNIT_AND_FLASK_E2E.log 2>&1 || { tail -60 .local-qa/UNIT_AND_FLASK_E2E.log; exit 2; }
if grep -q 'skipped=' .local-qa/UNIT_AND_FLASK_E2E.log; then
    echo 'ERROR: skipped tests are not accepted for publication'; exit 2
fi
if ! grep -qx 'OK' .local-qa/UNIT_AND_FLASK_E2E.log; then
    echo 'ERROR: test suite did not finish OK'; exit 2
fi
"$VPY" -m qa.dev_run --out "$ROOT/.local-qa/dev-results"
"$VPY" - "$ROOT" <<'PYTHON'
import sys,json
from pathlib import Path
base=Path(sys.argv[1])
s=json.loads((base/'.local-qa/dev-results/DEV_SUMMARY.json').read_text(encoding='utf-8'))
assert (s['facts'],s['questions'],s['matches'])==(9,3,9),s
assert s['not_blind'] is True and s['blind_quality'] is None
print('TESTS_NO_SKIPS=PASS')
print('SYNTHETIC_DEV_REGRESSION=PASS facts=9 questions=3')
print('INDEPENDENT_HOLDOUT=NOT_PERFORMED')
PYTHON
