"""Content extraction — reads input files (PDF, markdown, text) into plain text.

Supports PDF text extraction via pypdf, and direct reading of .md / .txt files.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Allowed file extensions for content extraction
ALLOWED_EXTENSIONS = frozenset({
    ".pdf", ".md", ".markdown", ".txt", ".text", ".rst", ".html", ".htm",
})

# Max content size accepted (characters) before truncation
MAX_CONTENT_CHARS = 100_000


def _validate_file_path(file_path: str) -> Path:
    """Validate and resolve a file path, rejecting path traversal attempts.

    Raises:
        ValueError: If the path contains traversal sequences or is not a regular file.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path).resolve()

    # Reject path traversal — the resolved path must not have come from '..' components
    if ".." in Path(file_path).parts:
        raise ValueError(
            f"Path traversal detected: '{file_path}'. "
            "Use absolute paths or paths relative to the working directory."
        )

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not path.is_file():
        raise ValueError(f"Not a regular file: {file_path}")

    # Check extension
    suffix = path.suffix.lower()
    if suffix and suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"File type '{suffix}' is not allowed. "
            f"Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    return path


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text content from a PDF file.

    Uses pypdf for text extraction. Falls back to page-by-page extraction
    if the full document read fails.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError(
            "pypdf is required for PDF extraction. "
            "Install it with: pip install pypdf"
        )

    reader = PdfReader(file_path)
    pages_text: list[str] = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            pages_text.append(text.strip())
        else:
            logger.warning("Page %d of %s yielded no text", i + 1, file_path)

    if not pages_text:
        raise ValueError(f"No text could be extracted from PDF: {file_path}")

    full_text = "\n\n".join(pages_text)
    logger.info("Extracted %d characters from %d pages of %s", len(full_text), len(reader.pages), file_path)
    return full_text


def read_text_file(file_path: str) -> str:
    """Read a plain text or markdown file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"File is empty: {file_path}")

    logger.info("Read %d characters from %s", len(text), file_path)
    return text


def extract_content(file_path: str) -> str:
    """Auto-detect file type and extract text content.

    Validates the path to prevent traversal attacks, then extracts based on extension.

    Supported formats:
    - .pdf → PDF text extraction
    - .md, .markdown → Markdown (read as-is)
    - .txt, .text, .rst → Plain text
    - .html, .htm → Read as-is (HTML tags preserved for context)

    Args:
        file_path: Path to the input file.

    Returns:
        Extracted text content.
    """
    validated = _validate_file_path(file_path)
    safe_path = str(validated)
    suffix = validated.suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(safe_path)
    elif suffix in ALLOWED_EXTENSIONS:
        return read_text_file(safe_path)
    else:
        try:
            return read_text_file(safe_path)
        except UnicodeDecodeError:
            raise ValueError(
                f"Unsupported file format: {suffix}. "
                f"Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )


def truncate_content(text: str, max_chars: int = 100_000) -> str:
    """Truncate content if it exceeds the model's context window.

    Gemini Flash has a large context window, but we still want to be
    sensible about extremely long documents.
    """
    if len(text) <= max_chars:
        return text

    logger.warning(
        "Content truncated from %d to %d characters", len(text), max_chars,
    )
    # Truncate at a sentence boundary
    truncated = text[:max_chars]
    last_period = truncated.rfind(".")
    if last_period > max_chars * 0.8:
        truncated = truncated[: last_period + 1]

    return truncated + "\n\n[Content truncated due to length]"
