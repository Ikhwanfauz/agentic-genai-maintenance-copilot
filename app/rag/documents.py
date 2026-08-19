import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EngineeringDocumentChunk:
    chunk_id: str
    document_id: str
    title: str
    section: str
    source_path: str
    applicable_assets: str
    content: str


def slugify(value: str) -> str:
    normalized = re.sub(
        r"[^a-z0-9]+",
        "-",
        value.lower(),
    )
    return normalized.strip("-")


def metadata_value(
    lines: list[str],
    field_name: str,
) -> str | None:
    prefix = f"{field_name}:"

    for line in lines:
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()

    return None


def load_engineering_document(
    document_path: Path,
) -> list[EngineeringDocumentChunk]:
    lines = document_path.read_text(encoding="utf-8").splitlines()

    title_line = next(
        (line for line in lines if line.startswith("# ")),
        None,
    )
    document_id = metadata_value(lines, "Document ID")
    applicable_assets = metadata_value(
        lines,
        "Applicable assets",
    )

    if title_line is None:
        raise ValueError(f"Document '{document_path}' has no level-one title.")

    if document_id is None:
        raise ValueError(f"Document '{document_path}' has no Document ID.")

    title = title_line.removeprefix("# ").strip()
    chunks: list[EngineeringDocumentChunk] = []

    current_section: str | None = None
    current_body: list[str] = []

    def append_current_section() -> None:
        if current_section is None:
            return

        body = "\n".join(current_body).strip()

        if not body:
            return

        chunks.append(
            EngineeringDocumentChunk(
                chunk_id=(f"{document_id.lower()}-{slugify(current_section)}"),
                document_id=document_id,
                title=title,
                section=current_section,
                source_path=document_path.name,
                applicable_assets=applicable_assets or "unspecified",
                content=(f"{title}\n\nSection: {current_section}\n\n{body}"),
            )
        )

    for line in lines:
        if line.startswith("## "):
            append_current_section()
            current_section = line.removeprefix("## ").strip()
            current_body = []
            continue

        if current_section is not None:
            current_body.append(line)

    append_current_section()

    if not chunks:
        raise ValueError(f"Document '{document_path}' has no section content.")

    return chunks


def load_engineering_document_chunks(
    documents_directory: Path,
) -> list[EngineeringDocumentChunk]:
    document_paths = sorted(documents_directory.glob("*.md"))

    if not document_paths:
        raise ValueError(f"No Markdown documents found in '{documents_directory}'.")

    chunks = [
        chunk
        for document_path in document_paths
        for chunk in load_engineering_document(document_path)
    ]

    chunk_ids = [chunk.chunk_id for chunk in chunks]

    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Engineering document chunk IDs must be unique.")

    return chunks
