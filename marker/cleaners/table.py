import io
import os
from marker.bbox import merge_boxes
from marker.cleaners.nougat import get_image_bytes, get_tokens_len, process
from marker.cleaners.utils import (
    merge_target_blocks,
    set_block_type,
    set_special_block_type,
)
from marker.schema import Line, Span, Block, Page
from tabulate import tabulate
from typing import List
import fitz


def merge_table_caption(block_idx, block, page):
    prev_block: Block = None
    next_block: Block = None
    if block_idx > 0:
        prev_block = page.blocks[block_idx - 1]
    if block_idx < len(page.blocks) - 1:
        next_block = page.blocks[block_idx + 1]

    prev_block_type = prev_block.most_common_block_type() if prev_block else None
    next_block_type = next_block.most_common_block_type() if next_block else None

    if (prev_block_type is None and next_block_type is None) or (
        prev_block_type != "Caption" and next_block_type != "Caption"
    ):
        # very nesssary!!!
        return False, block.bbox, block.bbox

    table_caption_bbox: List[float] = block.bbox
    if prev_block_type is not None and "Table" in prev_block.prelim_text:
        # merge previous caption
        table_caption_bbox = merge_boxes(block.bbox, prev_block.bbox)
        set_block_type(prev_block, "TableCaption")
    elif next_block_type is not None and "Table" in next_block.prelim_text:
        # merge next caption
        table_caption_bbox = merge_boxes(block.bbox, next_block.bbox)
        set_block_type(next_block, "TableCaption")
    else:
        # has caption block, but not table
        set_block_type(block, "Picture")
        return False, None, None
    return True, table_caption_bbox, block.bbox


def recognition_table(block, table_idx, debug_mode):
    table_row = []
    table_matrix = []
    line_y_start = None
    for line in block.lines:
        if line_y_start is None or abs(line_y_start - line.y_start) > 2:
            # new row, append last row to matrix
            if len(table_row) > 0:
                table_matrix.append(table_row)
                table_row = []
            line_y_start = line.y_start
        # append line to row
        table_row.append(line.prelim_text)
    # append last row
    if len(table_row) > 0:
        table_matrix.append(table_row)

    # convert table matrix to markdown
    new_text = tabulate(table_matrix, headers="firstrow", tablefmt="github")
    block.lines = [
        Line(
            bbox=block.bbox,
            spans=[
                Span(
                    bbox=block.bbox,
                    span_id=f"{table_idx}_fix_table",
                    font="Table",
                    color=0,
                    block_type="Table",
                    text=f"{new_text}",
                )
            ],
        )
    ]

    if debug_mode:
        with open("inline_table.md", "a") as file:
            file.write(f"{new_text} \n")


def recognition_table_ocr(
    doc, page_idx, block_idx, block, table_bbox, model, debug_mode
):
    # get table image
    bboxes: List[List[float]] = [table_bbox]
    table_image: io.BytesIO = get_image_bytes(doc[page_idx], table_bbox, bboxes)
    if table_image is None:
        return False

    # save table image
    if debug_mode:
        file_name = f"table_{page_idx}_{block_idx}.bmp"
        save_path = os.path.join("./", file_name)
        with open(save_path, "wb") as f:
            f.write(table_image.getvalue())

    # get result from nougat
    table_images: List[io.BytesIO] = []
    table_token_list: List[int] = []
    table_images.append(table_image)
    tokens_len = get_tokens_len(block.prelim_text, model)
    table_token_list.append(tokens_len)
    predictions: List[str] = process(table_images, table_token_list, model, 1)

    # save result
    if debug_mode:
        with open("inline_table.md", "a") as file:
            file.write(f"table_{page_idx}_{block_idx} {predictions}  \n")
    return True


def process_tables(doc: fitz.Document, pages: List[Page], model, debug_mode: bool):
    merge_target_blocks(pages, "Table")

    table_idx = 0
    for page_idx, page in enumerate(pages):
        for block_idx, block in enumerate(page.blocks):
            if block.most_common_block_type() != "Table":
                # not table block
                set_special_block_type(block, "Table", "ErrorType")
                continue

            is_success, table_caption_bbox, table_bbox = merge_table_caption(
                block_idx, block, page
            )
            if not is_success:
                continue

            recognition_table(block, table_idx, debug_mode)

            is_success = recognition_table_ocr(
                doc, page_idx, block_idx, block, table_bbox, model, True
            )
            if not is_success:
                continue

            table_idx += 1
