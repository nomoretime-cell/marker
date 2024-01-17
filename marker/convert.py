import fitz as pymupdf
from marker.analyzer.spans import SpanType, SpansAnalyzer

from marker.cleaners.table import merge_table_blocks, create_new_tables
from marker.debug.data import dump_bbox_debug_data
from marker.extract_text import get_pages
from marker.cleaners.headers import filter_header_footer, filter_common_titles
from marker.cleaners.equations import replace_equations
from marker.ordering import order_blocks
from marker.postprocessors.editor import edit_full_text
from marker.segmentation import get_pages_types
from marker.cleaners.bullets import replace_bullets
from marker.markdown import merge_spans, merge_lines, get_string
from marker.schema import Page, BlockType, MergedBlock, FullyMergedBlock, Span
from typing import List, Dict, Tuple, Optional
import re
import magic
from marker.settings import settings


def find_filetype(fpath):
    mimetype = magic.from_file(fpath).lower()

    # Get extensions from mimetype
    # The mimetype is not always consistent, so use in to check the most common formats
    if "pdf" in mimetype:
        return "pdf"
    elif "epub" in mimetype:
        return "epub"
    elif "mobi" in mimetype:
        return "mobi"
    elif mimetype in settings.SUPPORTED_FILETYPES:
        return settings.SUPPORTED_FILETYPES[mimetype]
    else:
        print(f"Found nonstandard filetype {mimetype}")
        return "other"


def annotate_spans_type(pages: List[Page], pages_types: List[List[BlockType]]):
    for i, page in enumerate(pages):
        page_types = pages_types[i]
        page.add_types(page_types)


def get_length_of_text(fname: str) -> int:
    filetype = find_filetype(fname)
    if filetype == "other":
        return 0

    doc = pymupdf.Document(fname, filetype=filetype)
    full_text = ""
    for page in doc:
        full_text += page.get_text("text", sort=True, flags=settings.TEXT_FLAGS)

    return len(full_text)


def get_all_spans(pages: List[Page]) -> List[Span]:
    spans: List[Span] = []
    for page in pages:
        for block in page.blocks:
            for line in block.lines:
                for span in line.spans:
                    spans.append(span)
    # FOR DEBUG
    with open("all_spans_type.txt", "w", encoding="utf-8") as file:
        for span in spans:
            file.write(str(span) + "\n")
    return spans


def update_equations_in_spans(
    pages: List[Page], pages_types: List[List[BlockType]]
) -> List[Span]:
    spans: List[Span] = []
    for page_index, page in enumerate(pages):
        for block in page.blocks:
            for line_index, line in enumerate(block.lines):
                containsFormula = False
                for span in line.spans:
                    if span.size < page.text_font and span.block_type == "Text":
                        containsFormula = True
                        break
                if containsFormula:
                    pages_types[page_index][line_index].block_type = "Formula"
                    for span in line.spans:
                        span.block_type = "Formula"

    # FOR DEBUG
    with open("all_updated_spans_type.txt", "w", encoding="utf-8") as file:
        for span in spans:
            file.write(str(span) + "\n")
    return spans


def convert_single_pdf(
    fname: str,
    model_lst: List,
    max_pages=None,
    metadata: Optional[Dict] = None,
    parallel_factor: int = 1,
    debug_mode: bool = False,
) -> Tuple[str, Dict]:
    lang = settings.DEFAULT_LANG
    if metadata:
        lang = metadata.get("language", settings.DEFAULT_LANG)

    # Use tesseract language if available
    tess_lang = settings.TESSERACT_LANGUAGES.get(lang, "eng")
    spell_lang = settings.SPELLCHECK_LANGUAGES.get(lang, None)
    if "eng" not in tess_lang:
        tess_lang = f"eng+{tess_lang}"

    # Output metadata
    out_meta = {"language": lang}

    filetype = find_filetype(fname)
    if filetype == "other":
        return "", out_meta

    out_meta["filetype"] = filetype

    doc: pymupdf.Document = pymupdf.Document(fname, filetype=filetype)
    if filetype != "pdf":
        conv = doc.convert_to_pdf()
        doc = pymupdf.open("pdf", conv)

    pages, toc, ocr_stats = get_pages(
        doc,
        tess_lang,
        spell_lang,
        max_pages=max_pages,
        parallel=parallel_factor * settings.OCR_PARALLEL_WORKERS,
    )

    out_meta["toc"] = toc
    out_meta["pages"] = len(pages)
    out_meta["ocr_stats"] = ocr_stats
    if len([b for p in pages for b in p.blocks]) == 0:
        print(f"Could not extract any text blocks for {fname}")
        return "", out_meta

    # Unpack models from list
    nougat_model, segment_model, order_model, edit_model = model_lst

    pages_types: List[List[BlockType]] = get_pages_types(
        doc,
        pages,
        segment_model,
        batch_size=settings.LAYOUT_BATCH_SIZE * parallel_factor,
    )

    # Find headers and footers
    bad_span_ids: List[int] = filter_header_footer(pages)
    out_meta["block_stats"] = {"header_footer": len(bad_span_ids)}

    annotate_spans_type(pages, pages_types)

    # Get text font size
    spans: List[Span] = get_all_spans(pages)
    sa = SpansAnalyzer(spans)
    if len(sa.type2fontSize[SpanType.Text.value]) > 0:
        for page in pages:
            page.text_font = sa.type2fontSize[SpanType.Text.value][0].font_size
    # update_equations_in_spans(pages, pages_types)

    # Dump debug data if flags are set
    dump_bbox_debug_data(doc, pages)

    pages = order_blocks(
        doc,
        pages,
        order_model,
        batch_size=settings.ORDERER_BATCH_SIZE * parallel_factor,
    )

    # Fix code blocks
    # code_block_count = identify_code_blocks(blocks)
    # out_meta["block_stats"]["code"] = code_block_count
    # indent_blocks(blocks)

    # Fix table blocks
    # merge_table_blocks(pages)
    # table_count = create_new_tables(pages)
    # out_meta["block_stats"]["table"] = table_count

    for page in pages:
        for block in page.blocks:
            block.filter_spans(bad_span_ids)
            block.filter_bad_span_types()

    pages, eq_stats = replace_equations(
        doc,
        pages,
        pages_types,
        nougat_model,
        batch_size=settings.NOUGAT_BATCH_SIZE * parallel_factor,
        debug_mode=debug_mode,
    )
    out_meta["block_stats"]["equations"] = eq_stats

    # Copy to avoid changing original data
    merged_pages: List[List[MergedBlock]] = merge_spans(pages)
    merged_blocks: List[FullyMergedBlock] = merge_lines(merged_pages, pages)
    merged_blocks = filter_common_titles(merged_blocks)
    pages_string: str = get_string(merged_blocks)

    # Handle empty blocks being joined
    pages_string = re.sub(r"\n{3,}", "\n\n", pages_string)
    pages_string = re.sub(r"(\n\s){3,}", "\n\n", pages_string)

    # Replace bullet characters with a -
    pages_string = replace_bullets(pages_string)

    # Postprocess text with editor model
    pages_string, edit_stats = edit_full_text(
        pages_string,
        edit_model,
        batch_size=settings.EDITOR_BATCH_SIZE * parallel_factor,
    )
    out_meta["postprocess_stats"] = {"edit": edit_stats}

    return pages_string, out_meta
