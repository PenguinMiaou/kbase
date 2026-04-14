---
name: document-enrich
description: Read a document (Excel/PPTX/DOCX), enrich with knowledge base + web search, output modified copy
when_to_use: User asks to modify, supplement, enrich, revise, or fill in a document file
allowed_tools: [excel_read, excel_write, excel_copy, kb_search, web_search, pptx_read, pptx_write, docx_read, docx_write, file_info, output_file]
---

# Document Enrichment Skill

## Goal
Read the user's document, combine with knowledge base and internet information, modify/supplement content, and output a NEW file (never overwrite original).

## Rules
- ALWAYS copy the original file first, work on the copy
- Modified cells/text: RED font (FF0000)
- New/added content: BLUE font (0000FF)
- Every change must have a source (KB file name or web URL) in cell comment or speaker notes
- If data is uncertain, mark as "pending verification"
- Preserve original formatting and layout
