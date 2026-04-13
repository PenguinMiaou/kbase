"""Smart chunking with table awareness."""
import re
from kbase.config import CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS


def chunk_document(text: str, file_type: str, metadata: dict = None) -> list[dict]:
    """Split document text into chunks with metadata.

    Returns list of {text, metadata} dicts.
    """
    metadata = metadata or {}

    if not text or not text.strip():
        return []

    if file_type in (".pptx", ".ppt"):
        return _chunk_by_slides(text, metadata)
    elif file_type in (".xlsx", ".xls", ".csv"):
        # Tables: keep each sheet as one chunk (they'll also go to SQLite)
        return _chunk_table_text(text, metadata)
    elif file_type == ".pdf":
        return _chunk_by_pages(text, metadata)
    else:
        return _chunk_by_headings(text, metadata)


def _chunk_by_slides(text: str, metadata: dict) -> list[dict]:
    """Split PPTX text by slide markers."""
    slides = re.split(r"\[Slide \d+\]", text)
    slide_nums = re.findall(r"\[Slide (\d+)\]", text)

    chunks = []
    for i, slide_text in enumerate(slides):
        slide_text = slide_text.strip()
        if not slide_text:
            continue
        slide_num = slide_nums[i - 1] if i > 0 and i - 1 < len(slide_nums) else str(i)
        # If slide is too long, sub-chunk it
        if len(slide_text) > CHUNK_MAX_CHARS * 2:
            sub_chunks = _split_text(slide_text)
            for j, sc in enumerate(sub_chunks):
                chunks.append({
                    "text": sc,
                    "metadata": {**metadata, "slide": slide_num, "sub_chunk": j},
                })
        else:
            chunks.append({
                "text": slide_text,
                "metadata": {**metadata, "slide": slide_num},
            })
    return chunks if chunks else [{"text": text[:CHUNK_MAX_CHARS], "metadata": metadata}]


def _chunk_by_pages(text: str, metadata: dict) -> list[dict]:
    """Split PDF text by page markers."""
    pages = re.split(r"\[Page \d+\]", text)
    page_nums = re.findall(r"\[Page (\d+)\]", text)

    chunks = []
    for i, page_text in enumerate(pages):
        page_text = page_text.strip()
        if not page_text:
            continue
        page_num = page_nums[i - 1] if i > 0 and i - 1 < len(page_nums) else str(i)
        if len(page_text) > CHUNK_MAX_CHARS * 2:
            sub_chunks = _split_text(page_text)
            for j, sc in enumerate(sub_chunks):
                chunks.append({
                    "text": sc,
                    "metadata": {**metadata, "page": page_num, "sub_chunk": j},
                })
        else:
            chunks.append({
                "text": page_text,
                "metadata": {**metadata, "page": page_num},
            })
    return chunks if chunks else [{"text": text[:CHUNK_MAX_CHARS], "metadata": metadata}]


def _chunk_by_headings(text: str, metadata: dict) -> list[dict]:
    """Split markdown/text by headings, then by size."""
    # Split on headings
    sections = re.split(r"(?=^#{1,4}\s)", text, flags=re.MULTILINE)
    chunks = []

    for section in sections:
        section = section.strip()
        if not section:
            continue
        # Extract heading as context
        heading_match = re.match(r"^(#{1,4})\s+(.+)", section)
        heading = heading_match.group(2).strip() if heading_match else ""

        if len(section) <= CHUNK_MAX_CHARS:
            chunks.append({
                "text": section,
                "metadata": {**metadata, "heading": heading},
            })
        else:
            sub_chunks = _split_text(section)
            for j, sc in enumerate(sub_chunks):
                chunks.append({
                    "text": sc,
                    "metadata": {**metadata, "heading": heading, "sub_chunk": j},
                })

    return chunks if chunks else [{"text": text[:CHUNK_MAX_CHARS], "metadata": metadata}]


def _chunk_table_text(text: str, metadata: dict) -> list[dict]:
    """For spreadsheet text: keep sheet sections together."""
    sheets = re.split(r"(?=^## Sheet:)", text, flags=re.MULTILINE)
    chunks = []
    for sheet in sheets:
        sheet = sheet.strip()
        if not sheet:
            continue
        sheet_match = re.match(r"## Sheet:\s*(.+)", sheet)
        sheet_name = sheet_match.group(1).strip() if sheet_match else ""

        # Tables can be big - split if needed but try to keep rows together
        if len(sheet) <= CHUNK_MAX_CHARS * 3:
            chunks.append({
                "text": sheet,
                "metadata": {**metadata, "sheet": sheet_name},
            })
        else:
            sub_chunks = _split_text(sheet)
            for j, sc in enumerate(sub_chunks):
                chunks.append({
                    "text": sc,
                    "metadata": {**metadata, "sheet": sheet_name, "sub_chunk": j},
                })
    return chunks if chunks else [{"text": text[:CHUNK_MAX_CHARS], "metadata": metadata}]


def _split_text(text: str) -> list[str]:
    """Split text into chunks respecting paragraph boundaries."""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 <= CHUNK_MAX_CHARS:
            current = current + "\n\n" + para if current else para
        else:
            if current:
                chunks.append(current)
            # If single paragraph exceeds max, split by sentences
            if len(para) > CHUNK_MAX_CHARS:
                sentences = re.split(r"(?<=[。！？.!?\n])\s*", para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= CHUNK_MAX_CHARS:
                        current = current + " " + sent if current else sent
                    else:
                        if current:
                            chunks.append(current)
                        current = sent
            else:
                current = para

    if current:
        chunks.append(current)

    # Add overlap between chunks
    if len(chunks) > 1 and CHUNK_OVERLAP_CHARS > 0:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-CHUNK_OVERLAP_CHARS:]
            overlapped.append(prev_tail + "\n" + chunks[i])
        chunks = overlapped

    return chunks
