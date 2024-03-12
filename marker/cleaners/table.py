import io
import os

import pdfplumber
from pdfplumber import page
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


class CellRange:
    def __init__(self, cell_start: int, cell_end: int):
        self.cell_start = cell_start
        self.cell_end = cell_end

    def is_intersect(self, in_start: int, in_end: int, ratio: float = 0.0):
        real_ratio = self.intersect_ratio(in_start, in_end)
        return real_ratio > ratio

    def intersect_ratio(self, in_start: int, in_end: int):
        in_length = in_end - in_start
        intersect: bool = self.cell_start <= in_end and self.cell_end >= in_start
        if not intersect:
            return 0
        intersect_length = min(self.cell_end, in_end) - max(self.cell_start, in_start)
        return intersect_length / in_length

    def extend(self, in_start: int, in_end: int):
        self.cell_start = min(self.cell_start, in_start)
        self.cell_end = max(self.cell_end, in_end)

    def is_in(self, in_start: int, in_end: int):
        return self.cell_start <= in_start and self.cell_end >= in_end


def calculate_column(column_x_list: List[CellRange], x_start: int, x_end: int):
    for column in column_x_list:
        if column.is_intersect(x_start, x_end, 0.0):
            column.extend(x_start, x_end)
            return
    column_x_list.append(CellRange(x_start, x_end))


def calculate_row(row_y_list: List[CellRange], y_start: int, y_end: int):
    for row in row_y_list:
        if row.is_intersect(y_start, y_end, 0.8):
            row.extend(y_start, y_end)
            return
    row_y_list.append(CellRange(y_start, y_end))


def recognition_table(block: Block, table_idx: int, debug_mode):
    # get column
    column_x_list: List[CellRange] = []
    for line in block.lines:
        calculate_column(column_x_list, line.x_start, line.x_start + line.width)
    if column_x_list == []:
        return
    column_x_list.sort(key=lambda x: x.cell_start)
    column_one = column_x_list[0]

    # get row heads
    row_y_list: List[CellRange] = []
    for line in block.lines:
        if column_one.is_in(line.x_start, line.x_start + line.width):
            row_y_list.append(CellRange(line.y_start, line.y_start + line.height))
    if row_y_list == []:
        return
    row_y_list.sort(key=lambda x: x.cell_start)

    # 2. 然后判断其是否有换行（条件：后面column中的文本和该行头的重叠率）
    row_y_list: List[CellRange] = []
    for line in block.lines:
        calculate_row(row_y_list, line.y_start, line.y_start + line.height)

    merge_row_list: List[CellRange] = []
    for row in row_y_list:
        calculate_row(merge_row_list, row.cell_start, row.cell_end)

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

    table_to_markdown(table_matrix, block, table_idx, debug_mode)


def recognition_table_pdfplumber(
    pdfp_page: page.Page,
    table_bbox: List[float],
    block: Block,
    table_idx: int,
    debug_mode: bool,
):
    table_settings = {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
    }
    if debug_mode:
        pdfp_page.crop(table_bbox).to_image(resolution=300).debug_tablefinder(
            table_settings
        ).save(f"table_{table_idx}.png", quality=100)
    table = pdfp_page.crop(table_bbox).extract_tables(table_settings)
    if table == []:
        return
    table_to_markdown(table[0], block, table_idx, debug_mode)


def table_to_markdown(table: List[List[str]], block: Block, table_idx: int, debug_mode):
    # convert table matrix to markdown
    new_text = tabulate(table, headers="firstrow", tablefmt="github")
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


def process_tables(
    fname, doc: fitz.Document, pages: List[Page], model, debug_mode: bool
):
    with pdfplumber.open(fname) as pdfp:
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

                # recognition_table(block, table_idx, debug_mode)
                recognition_table_pdfplumber(
                    pdfp.pages[page_idx], table_bbox, block, table_idx, debug_mode
                )

                is_success = recognition_table_ocr(
                    doc, page_idx, block_idx, block, table_bbox, model, debug_mode
                )
                if not is_success:
                    continue

                table_idx += 1
