"""M05 fixture generator; synthetic only, no network or private documents.

Reads a frozen inputs description. Expected outcomes are in a *separate* JSON
and are deliberately not imported here or generated from implementation output.
"""
import argparse
import html
import json
from pathlib import Path

import pymupdf as fitz


def generate(spec_file: Path, output: Path):
    specs = json.loads(spec_file.read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=True)
    for case, files in sorted(specs.items()):
        target = output / case
        target.mkdir(parents=True, exist_ok=True)
        for name, value in sorted(files.items()):
            assert name.endswith('.pdf') and '/' not in name and '\\' not in name
            path = target / name
            if isinstance(value, dict):
                path.write_bytes(value['invalid_bytes'].encode('utf-8'))
                continue
            assert isinstance(value, list) and 1 <= len(value) <= 3
            document = fitz.open()
            try:
                for text in value:
                    page = document.new_page()
                    if text:
                        markup = '<p>' + html.escape(text) + '</p>'
                        spare, scale = page.insert_htmlbox(fitz.Rect(25, 25, 565, 750), markup)
                        assert spare >= 0 and 0 < scale <= 1, (case, name, spare, scale)
                document.save(path, garbage=4, deflate=True)
            finally:
                document.close()
    print('M05_SYNTHETIC_CASES='+str(len(specs))+' PDF_FILES='+str(sum(len(s) for s in specs.values())))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--spec',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args()
    generate(args.spec,args.out_dir)
