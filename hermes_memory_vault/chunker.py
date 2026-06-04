from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TextChunk:
    text: str
    seq: int


def chunk_text(text: str, *, max_chars: int = 12000) -> list[TextChunk]:
    """Split text into deterministic character-bounded chunks.

    MVP callers normally store one chunk per Hermes turn or imported file; this
    compatibility helper exists so future canonicalize/chunking phases can use
    the design-brief module name without changing imports.
    """
    max_chars = max(1000, int(max_chars or 12000))
    if len(text) <= max_chars:
        return [TextChunk(text=text, seq=1)]
    chunks: list[TextChunk] = []
    start = 0
    seq = 1
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            split = text.rfind("\n\n", start, end)
            if split > start + 500:
                end = split + 2
        chunks.append(TextChunk(text=text[start:end], seq=seq))
        start = end
        seq += 1
    return chunks
