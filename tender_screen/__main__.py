"""Usage: python -m tender_screen run --input-dir examples/sample_pack --out-dir reports"""
import argparse
import json
from pathlib import Path
import sys

from .core import analyze_folder
from .processing_budget import ProcessingBudget
from .report import render_html, write_csv
from .domain_report import render_fast_dev2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='TenderLens: offline PDF tender screening with page-level evidence')
    parser.add_argument('command', choices=['run'])
    parser.add_argument('--input-dir', type=Path, required=True, help='Directory of PDF tender documents')
    parser.add_argument('--out-dir', type=Path, default=Path('reports'), help='Directory for HTML, CSV and JSON')
    parser.add_argument('--max-pages-per-pdf',type=int,default=300)
    parser.add_argument('--max-pages-total',type=int,default=900)
    parser.add_argument('--max-seconds',type=float,default=120.0)
    parser.add_argument('--max-rss-mib',type=int,default=2048)
    args = parser.parse_args(argv)
    try:
        budget=ProcessingBudget(max_pages_per_pdf=args.max_pages_per_pdf,
                                max_pages_total=args.max_pages_total,max_seconds=args.max_seconds,
                                max_rss_mib=args.max_rss_mib)
        result = analyze_folder(args.input_dir.resolve(), budget=budget)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / 'report.html').write_text(render_html(result), encoding='utf-8')
        (args.out_dir / 'fast_dev2_report.html').write_text(render_fast_dev2(result['fast_dev2']),encoding='utf-8')
        (args.out_dir / 'layout.json').write_text(json.dumps(result.pop('layout', []), ensure_ascii=False, indent=2), encoding='utf-8')
        (args.out_dir / 'fast_dev2_facts.json').write_text(json.dumps(result['fast_dev2'], ensure_ascii=False, indent=2), encoding='utf-8')
        (args.out_dir / 'subject_price.json').write_text(json.dumps(result['normalized_card'], ensure_ascii=False, indent=2), encoding='utf-8')
        (args.out_dir / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        write_csv(result, args.out_dir / 'evidence.csv')
    except (OSError, ValueError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 2
    s = result['stats']
    status = result['processing_status']
    print(f'TENDER_SCREEN={status.upper()} files={s["files"]} pages={s["pages"]} findings={s["findings"]} risks={s["risks"]} errors={len(result["errors"])}')
    for n in ('report.html', 'analysis.json', 'evidence.csv', 'layout.json', 'subject_price.json', 'fast_dev2_facts.json', 'fast_dev2_report.html'):
        print(args.out_dir / n)
    return 0 if status == 'complete' else 3 if status == 'partial' else 2


if __name__ == '__main__':
    raise SystemExit(main())
