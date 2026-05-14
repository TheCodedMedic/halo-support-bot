import os

DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")
ACTIVE_DOC_PATH = os.path.join(DOCS_DIR, ".active_doc")


def load_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def load_pdf_file(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf is not installed. Run: pip install pypdf")
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def load_document(path: str) -> str:
    """Extract text from a .txt or .pdf file."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return load_pdf_file(path)
    elif ext == ".txt":
        return load_text_file(path)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Upload a .pdf or .txt file.")


def get_active_document() -> tuple[str | None, str | None]:
    """Return (filename, content) of the currently active knowledge base.

    Priority:
    1. ACTIVE_DOCUMENT env var — survives all redeploys (use on Railway)
    2. .active_doc pointer file — set via admin panel
    3. None — no knowledge base loaded
    """
    # 1. Environment variable takes priority — always works after redeploy
    env_doc = os.getenv("ACTIVE_DOCUMENT")
    if env_doc:
        doc_path = os.path.join(DOCS_DIR, env_doc)
        if os.path.exists(doc_path):
            try:
                return env_doc, load_document(doc_path)
            except Exception:
                pass

    # 2. Fall back to the .active_doc pointer file (set via admin panel)
    if os.path.exists(ACTIVE_DOC_PATH):
        with open(ACTIVE_DOC_PATH, "r") as f:
            filename = f.read().strip()
        doc_path = os.path.join(DOCS_DIR, filename)
        if os.path.exists(doc_path):
            try:
                return filename, load_document(doc_path)
            except Exception:
                pass

    return None, None


def set_active_document(filename: str) -> None:
    """Record which file in /docs is the active knowledge base."""
    with open(ACTIVE_DOC_PATH, "w") as f:
        f.write(filename)
