import os
from typing import Tuple, List, Optional

from spellchecker import SpellChecker

from marker.bbox import correct_rotation
from marker.ocr.page import ocr_entire_page
from marker.ocr.utils import detect_bad_ocr, font_flags_decomposer
from marker.settings import settings
from marker.schema import Span, Line, Block, Page
from concurrent.futures import ThreadPoolExecutor

import fitz as pymupdf

os.environ["TESSDATA_PREFIX"] = settings.TESSDATA_PREFIX


def get_text(doc):
    full_text = ""
    for page in doc:
        full_text += page.get_text("text", sort=True, flags=settings.TEXT_FLAGS)
        full_text += "\n"
    return full_text


def sort_rotated_text(blocks, tolerance=1.25):
    vertical_groups = {}
    for block in blocks:
        group_key = round(block.bbox[1] / tolerance) * tolerance
        if group_key not in vertical_groups:
            vertical_groups[group_key] = []
        vertical_groups[group_key].append(block)

    # Sort each group horizontally and flatten the groups into a single list
    sorted_page_blocks = []
    for _, group in sorted(vertical_groups.items()):
        sorted_group = sorted(group, key=lambda x: x.bbox[0])
        sorted_page_blocks.extend(sorted_group)

    return sorted_page_blocks


def get_blocks(
    doc: pymupdf.Document,
    pnum: int,
    tess_lang: str,
    all_spans: List[Span],
    spellchecker: Optional[SpellChecker] = None,
    ocr=False,
) -> Tuple[List[Block], int]:
    page: pymupdf.Page = doc.load_page(pnum)
    rotation = page.rotation

    if ocr:
        blocks: List[Block] = ocr_entire_page(page, tess_lang, spellchecker)
    else:
        blocks: List[Block] = page.get_text(
            "dict", sort=True, flags=settings.TEXT_FLAGS
        )["blocks"]

    return_blocks = []
    span_id = 0
    for index, block in enumerate(blocks):
        block_lines = []
        for line in block["lines"]:
            spans = []
            for i, s in enumerate(line["spans"]):
                block_text = s["text"]
                bbox = s["bbox"]
                span_obj = Span(
                    text=block_text,
                    bbox=correct_rotation(bbox, page),
                    span_id=f"{pnum}_{span_id}",
                    font=f"{s['font']}_{font_flags_decomposer(s['flags'])}",  # Add font flags to end of font
                    color=s["color"],
                    ascender=s["ascender"],
                    descender=s["descender"],
                    flags=s["flags"],
                    origin=s["origin"],
                    size=s["size"],
                )
                spans.append(span_obj)
                all_spans.append(span_obj)
                span_id += 1
            line_obj = Line(
                spans=spans,
                bbox=correct_rotation(line["bbox"], page),
            )

            if line_obj.area > 0:
                block_lines.append(line_obj)
        block_obj = Block(
            lines=block_lines, bbox=correct_rotation(block["bbox"], page), pnum=pnum
        )

        if len(block_lines) > 0:
            return_blocks.append(block_obj)

    # If the page was rotated, sort the text again
    if rotation > 0:
        return_blocks = sort_rotated_text(return_blocks)
    return return_blocks


def get_page(
    doc: pymupdf.Document,
    pnum: int,
    tess_lang: str,
    spell_lang: Optional[str],
    no_text: bool,
    all_spans: List[Span],
    disable_ocr: bool = False,
    min_ocr_page: int = 2,
):
    ocr_pages = 0
    ocr_success = 0
    ocr_failed = 0

    spellchecker = SpellChecker(language=spell_lang) if spell_lang else None

    blocks = get_blocks(doc, pnum, tess_lang, all_spans, spellchecker)
    page = Page(blocks=blocks, pnum=pnum, bbox=doc[pnum].bound())

    # OCR page if we got minimal text, or if we got too many spaces
    conditions = [
        (
            no_text  # Full doc has no text, and needs full OCR
            or (
                len(page.prelim_text) > 0
                and detect_bad_ocr(page.prelim_text, spellchecker)
            )  # Bad OCR
        ),
        min_ocr_page < pnum < len(doc) - 1,
        not disable_ocr,
    ]
    if all(conditions) or settings.OCR_ALL_PAGES:
        page = doc[pnum]
        blocks = get_blocks(doc, pnum, tess_lang, spellchecker, ocr=True)
        page = Page(
            blocks=blocks, pnum=pnum, bbox=doc[pnum].bound(), rotation=page.rotation
        )
        ocr_pages = 1
        if len(blocks) == 0:
            ocr_failed = 1
        else:
            ocr_success = 1
    return page, {
        "ocr_pages": ocr_pages,
        "ocr_failed": ocr_failed,
        "ocr_success": ocr_success,
    }


def get_pages(
    doc: pymupdf.Document,
    tess_lang: str,
    spell_lang: Optional[str],
    max_pages: Optional[int] = None,
    parallel: int = settings.OCR_PARALLEL_WORKERS,
):
    pages: List[Page] = []
    all_spans: List[Span] = []

    ocr_pages = 0
    ocr_failed = 0
    ocr_success = 0

    process_pages = min(max_pages, len(doc)) if max_pages else len(doc)
    if_no_text = len(get_text(doc).strip()) == 0

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        args_list = [
            (doc, pnum, tess_lang, spell_lang, if_no_text, all_spans)
            for pnum in range(process_pages)
        ]
        if parallel == 1:
            func = map
        else:
            func = pool.map
        results = func(lambda args: get_page(*args), args_list)

        for result in results:
            page, ocr_stats = result
            pages.append(page)
            ocr_pages += ocr_stats["ocr_pages"]
            ocr_failed += ocr_stats["ocr_failed"]
            ocr_success += ocr_stats["ocr_success"]

    with open("all_spans.txt", "w") as file:
        for span in all_spans:
            file.write(str(span) + "\n")
    return (
        pages,
        doc.get_toc(),
        {"ocr_pages": ocr_pages, "ocr_failed": ocr_failed, "ocr_success": ocr_success},
    )
