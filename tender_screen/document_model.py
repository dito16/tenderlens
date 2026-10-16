"""M02 source-grounded layout types. Coordinates use PDF page points, never guessed.

All object DTOs are JSON-safe. A missing span/bbox is None, not [0,0,0,0].
"""
from __future__ import annotations
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class TextBlock:
    text: str
    bbox: tuple[float, float, float, float]
    kind: str
    block_index: int


@dataclass(frozen=True)
class LayoutWord:
    text: str
    bbox: tuple[float, float, float, float]
    block: int
    line: int
    word: int
    normalized_span: tuple[int, int] | None


@dataclass(frozen=True)
class TableCell:
    row: int
    column: int
    value: str
    bbox: tuple[float, float, float, float] | None
    is_header: bool


@dataclass(frozen=True)
class LayoutTable:
    extraction_strategy: str
    quality: str
    bbox: tuple[float, float, float, float] | None
    row_count: int
    column_count: int
    cells: tuple[TableCell, ...]


def serializable(item):
    return asdict(item)
