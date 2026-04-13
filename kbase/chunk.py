"""Smart chunking with table awareness + parent-child hierarchy."""
import re
from kbase.config import CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS

# Parent chunk is 3x the child chunk for broader context
PARENT_MULTIPLIER = 3


def chunk_document(text: str, file_type: str, metadata: dict = None) -> list[dict]:
    """Split document text into child chunks + parent chunks.

    Child chunks (small, ~1500 chars): used for precise embedding matching.
    Parent chunks (large, ~4500 chars): stored as context, returned to LLM.

    Returns list of {text, metadata} dicts. Parent chunks have metadata["is_parent"]=True.
    """
    metadata = metadata or {}

    if not text or not text.strip():
        return []

    if file_type in (".pptx", ".ppt"):
        children = _chunk_by_slides(text, metadata)
    elif file_type in (".xlsx", ".xls", ".csv"):
        children = _chunk_table_text(text, metadata)
    elif file_type == ".pdf":
        children = _chunk_by_pages(text, metadata)
    else:
        children = _chunk_by_headings(text, metadata)

    # Generate parent chunks by merging adjacent children
    parents = _generate_parents(children, metadata)
    # Link children to their parent
    for child in children:
        child["metadata"]["is_parent"] = False

    return children + parents


def _generate_parents(children: list[dict], metadata: dict) -> list[dict]:
    """Merge adjacent child chunks into larger parent chunks for context."""
    if len(children) <= 1:
        return []

    parents = []
    parent_max = CHUNK_MAX_CHARS * PARENT_MULTIPLIER
    current_text = ""
    current_children = []

    for i, child in enumerate(children):
        child_text = child["text"]
        if len(current_text) + len(child_text) + 2 <= parent_max:
            current_text = current_text + "\n\n" + child_text if current_text else child_text
            current_children.append(i)
        else:
            if current_text and len(current_children) > 1:
                parents.append({
                    "text": current_text,
                    "metadata": {**metadata, "is_parent": True, "child_range": f"{current_children[0]}-{current_children[-1]}"},
                })
            current_text = child_text
            current_children = [i]

    # Last parent
    if current_text and len(current_children) > 1:
        parents.append({
            "text": current_text,
            "metadata": {**metadata, "is_parent": True, "child_range": f"{current_children[0]}-{current_children[-1]}"},
        })

    return parents


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
    """Semantic-aware text splitting: paragraph → sentence → character boundaries.

    Prioritizes natural language boundaries (paragraph breaks, Chinese/English
    sentence endings) over arbitrary character cuts.
    """
    # Step 1: Split by paragraph boundaries (double newline, or single newline before heading)
    paragraphs = re.split(r"\n\s*\n|\n(?=#{1,4}\s)|(?<=。)\n|(?<=\.)\n", text)
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
            # Step 2: Large paragraph → split by sentences (Chinese + English)
            if len(para) > CHUNK_MAX_CHARS:
                # Chinese-aware sentence splitting: 。！？；\n and English .!?
                sentences = re.split(r"(?<=[。！？；.!?\n])\s*", para)
                current = ""
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    if len(current) + len(sent) + 1 <= CHUNK_MAX_CHARS:
                        current = current + sent if current else sent
                    else:
                        if current:
                            chunks.append(current)
                        # Step 3: Single mega-sentence → split by comma/clause
                        if len(sent) > CHUNK_MAX_CHARS:
                            clauses = re.split(r"(?<=[，,；;：:\)])\s*", sent)
                            current = ""
                            for cl in clauses:
                                if len(current) + len(cl) + 1 <= CHUNK_MAX_CHARS:
                                    current = current + cl if current else cl
                                else:
                                    if current:
                                        chunks.append(current)
                                    current = cl
                        else:
                            current = sent
            else:
                current = para

    if current:
        chunks.append(current)

    # Step 4: Add overlap between chunks for context continuity
    if len(chunks) > 1 and CHUNK_OVERLAP_CHARS > 0:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-CHUNK_OVERLAP_CHARS:]
            overlapped.append(prev_tail + "\n" + chunks[i])
        chunks = overlapped

    return chunks
