from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import tempfile


@dataclass(slots=True)
class WriteResult:
    path: Path
    content_sha256: str


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if value is None:
        return "null"
    text = str(value)
    if not text or any(ch in text for ch in ":#[]{}\n\r") or text.strip() != text:
        return json.dumps(text, ensure_ascii=False)
    return text


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text == "":
        return ""
    if text in {"true", "false"}:
        return text == "true"
    if text == "null":
        return None
    if text.startswith("[") or text.startswith("{") or text.startswith('"'):
        try:
            return json.loads(text)
        except Exception:
            return text.strip('"')
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def compose_markdown(frontmatter: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key in sorted(frontmatter):
        value = frontmatter[key]
        if isinstance(value, (list, tuple)):
            rendered = "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in value) + "]"
        else:
            rendered = _format_scalar(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    if body and not body.startswith("\n"):
        lines.append("")
    return "\n".join(lines) + body


def parse_markdown(markdown: str) -> tuple[dict[str, Any], str]:
    if not markdown.startswith("---\n"):
        return {}, markdown
    end = markdown.find("\n---\n", 4)
    if end == -1:
        return {}, markdown
    raw = markdown[4:end]
    body = markdown[end + len("\n---\n"):]
    meta: dict[str, Any] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = _parse_scalar(value)
    return meta, body


def body_sha256(markdown_or_body: str) -> str:
    _, body = parse_markdown(markdown_or_body)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def write_chunk_markdown(path: Path, frontmatter: dict[str, Any], body: str) -> WriteResult:
    sha = body_sha256(body)
    meta = dict(frontmatter)
    meta["content_sha256"] = sha
    atomic_write_text(path, compose_markdown(meta, body))
    return WriteResult(path=path, content_sha256=sha)


def read_body(path: Path) -> str:
    _, body = parse_markdown(path.read_text(encoding="utf-8"))
    return body
