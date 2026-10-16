"""M02.5 bounded, cancellable PDF extraction. No network, no background tasks."""
from __future__ import annotations
from dataclasses import dataclass
import time
import sys
import resource


class ProcessingLimitError(ValueError):
    """Explicit resource stop; never report a partially processed file as complete."""


@dataclass(frozen=True)
class ProcessingBudget:
    max_pages_per_pdf: int = 300
    max_pages_total: int = 900
    max_text_chars_per_page: int = 200_000
    max_seconds: float = 120.0
    max_file_bytes: int = 30 * 1024 * 1024
    max_rss_mib: int = 2048

    def __post_init__(self):
        if not all(isinstance(x, int) and x > 0 for x in (
                self.max_pages_per_pdf, self.max_pages_total,
                self.max_text_chars_per_page, self.max_file_bytes, self.max_rss_mib)):
            raise ValueError('resource_limits_must_be_positive_integers')
        if not 0 < self.max_seconds <= 3600:
            raise ValueError('max_seconds_out_of_range')


class RunGuard:
    def __init__(self, budget: ProcessingBudget, cancelled=None):
        self.budget = budget
        self.start = time.monotonic()
        self.visited_pages = 0
        self.cancelled = cancelled

    @staticmethod
    def peak_rss_mib():
        try:
            rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # Darwin ru_maxrss is bytes; Linux uses KiB.
            return rss/(1024*1024 if sys.platform=='darwin' else 1024)
        except (OSError, AttributeError):
            return None

    def checkpoint(self):
        if self.cancelled is not None and self.cancelled():
            raise ProcessingLimitError('processing_cancelled')
        if time.monotonic() - self.start > self.budget.max_seconds:
            raise ProcessingLimitError('processing_time_budget_exceeded')
        rss=self.peak_rss_mib()
        if rss is not None and rss > self.budget.max_rss_mib:
            raise ProcessingLimitError('processing_peak_memory_budget_exceeded')

    def before_file(self, page_count: int, byte_count: int):
        self.checkpoint()
        if byte_count > self.budget.max_file_bytes:
            raise ProcessingLimitError('pdf_file_byte_limit_exceeded')
        if page_count > self.budget.max_pages_per_pdf:
            raise ProcessingLimitError('pdf_page_limit_exceeded')
        if self.visited_pages + page_count > self.budget.max_pages_total:
            raise ProcessingLimitError('batch_page_limit_exceeded')

    def after_page(self, text_length: int):
        if text_length > self.budget.max_text_chars_per_page:
            raise ProcessingLimitError('page_text_limit_exceeded')
        self.visited_pages += 1
        self.checkpoint()
