#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
    echo 'Run bash RUN_LOCAL_TESTS.sh first'; exit 2
fi
WORK="$(mktemp -d "${TMPDIR:-/tmp}/TENDERLENS_PUBLIC_DEMO_XXXXXXXX")"
"$ROOT/.venv/bin/python" - "$WORK" <<'PYTHON'
from pathlib import Path
import sys
from tender_screen.storage import LocalStore
with LocalStore(Path(sys.argv[1])) as store:
    name='TenderLens synthetic demonstration'
    store.project(name)
    imported=store.import_pdfs(name,sorted(Path('examples/fast_dev3_conflict_pack').glob('*.pdf')))
    result=store.analyze_project(name)
    assert imported['count_added']==3 and result['review_questions']==3
    print('SYNTHETIC_PRELOAD=PASS pdf=3 questions=3')
PYTHON
if command -v open >/dev/null 2>&1; then
    (sleep 2; open 'http://127.0.0.1:8765/' >/dev/null 2>&1 || true) &
fi
echo "LOCAL_DATA_ROOT=$WORK"
echo 'BROWSER=http://127.0.0.1:8765/'
echo 'Ctrl+C to stop; bind address is loopback only.'
exec "$ROOT/.venv/bin/python" -m tender_screen.web.run --data-root "$WORK" --port 8765
