"""Offline security boundaries for the local, single-user PDF research app.

No download, extraction of ZIP uploads, proxies or external HTTP. PDF can still
contain adversarial data: process only on a trusted local computer.
"""
from __future__ import annotations
import re
from pathlib import Path

PDF_HEADER_WINDOW = 1024
PDF_SIGNATURE = b'%PDF-'
PDF_PATH_SUFFIX = '.pdf'
WEB_ANALYZE_HARD_TIMEOUT_SECONDS = 125

def validate_local_pdf(path: Path):
    """Reject non-PDF and symlink intake before calling native parser."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != PDF_PATH_SUFFIX:
        raise ValueError('invalid_pdf_path')
    with path.open('rb') as f:
        head = f.read(PDF_HEADER_WINDOW)
    if not head.startswith(PDF_SIGNATURE):
        raise ValueError('pdf_header_required')
    if b'PK\x03\x04' == head[:4]:
        raise ValueError('zip_upload_not_supported')
    return True

def is_private_data_root(path:Path):
    """Reject symlink data root or symlinked blob/db entries."""
    root=Path(path).expanduser()
    if root.is_symlink(): raise ValueError('symlink_data_root_not_allowed')
    for name in ('tenderlens.sqlite3','pdf_blobs'):
        entry=root/name
        if entry.is_symlink(): raise ValueError('symlink_private_store_entry_not_allowed')
    return True

def check_static_offline(static_root):
    """Check application-controlled browser assets for third-party network origins."""
    root=Path(static_root)
    forbidden=re.compile(r'(?:https?:)?//[a-z][a-z0-9.-]+(?:/|:)',re.I)
    for file in sorted(root.rglob('*')):
        if file.is_file() and file.suffix in {'.js','.css','.html'}:
            content=file.read_text(encoding='utf-8')
            for match in forbidden.findall(content):
                if not (match.startswith('//localhost') or match.startswith('//127.0.0.1')):
                    raise ValueError('external_browser_url_detected:'+file.name)
    return True
