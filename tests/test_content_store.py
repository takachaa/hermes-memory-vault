from pathlib import Path

from hermes_memory_vault.content_store import (
    body_sha256,
    compose_markdown,
    parse_markdown,
    write_chunk_markdown,
)


def test_body_sha256_excludes_frontmatter():
    body = "# Title\n\nDurable body text\n"
    first = compose_markdown({"id": "one", "content_sha256": "placeholder"}, body)
    second = compose_markdown({"id": "two", "tags": ["x", "y"]}, body)

    assert body_sha256(first) == body_sha256(second) == body_sha256(body)


def test_compose_parse_roundtrip_frontmatter_and_body():
    markdown = compose_markdown(
        {
            "id": "chunk_1",
            "source_kind": "hermes_turn",
            "tags": ["conversation", "hermes"],
            "token_count": 7,
        },
        "# Body\n\nHello vault\n",
    )

    meta, body = parse_markdown(markdown)

    assert meta["id"] == "chunk_1"
    assert meta["source_kind"] == "hermes_turn"
    assert meta["tags"] == ["conversation", "hermes"]
    assert meta["token_count"] == 7
    assert body == "# Body\n\nHello vault\n"


def test_write_chunk_markdown_adds_content_sha_and_is_atomic(tmp_path: Path):
    target = tmp_path / "content" / "sessions" / "turn.md"
    body = "# Turn\n\nA remembered fact.\n"

    result = write_chunk_markdown(target, {"id": "chunk_1"}, body)

    assert result.path == target
    assert target.exists()
    meta, parsed_body = parse_markdown(target.read_text(encoding="utf-8"))
    assert parsed_body == body
    assert meta["content_sha256"] == body_sha256(body)
    assert result.content_sha256 == body_sha256(body)
