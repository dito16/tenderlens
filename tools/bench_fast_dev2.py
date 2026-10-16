"""Local-only reproducible 20/100/300-page PDF extraction benchmark.

No network, no G4, no gold, no holdout. This measures THIS machine, not a fixed SLO.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import tempfile
import json
import time
import platform
import sys
import pymupdf
from tender_screen.core import extract_pdf
from tender_screen.processing_budget import ProcessingBudget, RunGuard


def make_sample(path: Path, n: int):
    d=pymupdf.open()
    for i in range(n):
        page=d.new_page(width=595,height=842)
        page.insert_text((50,60),f'Synthetic tender page {i+1}/{n}',fontsize=11)
        page.insert_text((50,82),'No real tender documents. Performance only.',fontsize=11)
        page.insert_text((50,104),'Terms on this page are synthetic placeholders.',fontsize=11)
    d.save(path,garbage=4,deflate=True)
    d.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=[]
    with tempfile.TemporaryDirectory(prefix='tenderlens_fastdev2_bench_') as temp:
        for count in (20,100,300):
            f=Path(temp)/f'benchmark_{count}.pdf'
            make_sample(f,count)
            guard=RunGuard(ProcessingBudget(max_pages_per_pdf=300,max_pages_total=300,max_seconds=120))
            start=time.perf_counter()
            parsed=extract_pdf(f,guard=guard)
            elapsed=time.perf_counter()-start
            assert parsed['page_count']==count
            out.append({'pages':count,'source':'generated_synthetic_pdf',
                'elapsed_seconds':round(elapsed,3),'pages_per_second':round(count/max(elapsed,.0001),2),
                'file_bytes':f.stat().st_size,'peak_rss_mib':round(guard.peak_rss_mib() or 0,2),
                'extract_status':'pass','page_count_verified':count})
    args.out.parent.mkdir(parents=True,exist_ok=True)
    payload={'benchmark':'fast_dev2.M02.5','python':sys.version.split()[0],
         'platform':platform.platform(),'pymupdf':pymupdf.VersionBind,
         'limits':{'max_pages_per_pdf':300,'max_seconds':120,'max_rss_mib':2048},
         'peak_rss_is_process_high_watermark':True,'results':out,
         'disclaimer':'Synthetic repetitive pages only; not performance on large scanned or table-heavy real PDFs.'}
    args.out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    for row in out:print('BENCH',row)
    print('BENCHMARK_JSON='+str(args.out))

if __name__=='__main__':main()
