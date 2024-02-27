import io
import os
from marker.bbox import merge_boxes
from marker.cleaners.nougat import get_image_bytes, get_tokens_len, process
from marker.cleaners.utils import merge_target_blocks, set_block_type
from marker.schema import Line, Span, Block, Page
from tabulate import tabulate
from typing import List
import fitz


def replace_error_tables(block: Block):
    for line in block.lines:
        for span in line.spans:
            if span.block_type == "Table":
                span.block_type = "ErrorType"


def merge_table_blocks(pages: List[Page]):
    merge_target_blocks(pages, "Table")


def replace_tables(doc: fitz.Document, pages: List[Page], model, debug_mode: bool):
    table_idx = 0
    for page_idx, page in enumerate(pages):
        for block_idx, block in enumerate(page.blocks):
            if block.most_common_block_type() != "Table":
                # not table block
                replace_error_tables(block)
                continue

            # merge table blocks
            prev_block: Block = None
            next_block: Block = None
            if block_idx > 0:
                prev_block = page.blocks[block_idx - 1]
            if block_idx < len(page.blocks) - 1:
                next_block = page.blocks[block_idx + 1]

            prev_block_type = (
                prev_block.most_common_block_type() if prev_block else None
            )
            next_block_type = (
                next_block.most_common_block_type() if next_block else None
            )

            if (prev_block_type is None and next_block_type is None) or (
                prev_block_type != "Caption" and next_block_type != "Caption"
            ):
                set_block_type(block, "Picture")
                continue

            merged_bbox: List[float] = block.bbox

            if prev_block_type is not None and "Table" in prev_block.prelim_text:
                # merge previous caption
                merged_bbox = merge_boxes(block.bbox, prev_block.bbox)
                set_block_type(prev_block, "TableCaption")
            elif next_block_type is not None and "Table" in next_block.prelim_text:
                # merge next caption
                merged_bbox = merge_boxes(block.bbox, next_block.bbox)
                set_block_type(next_block, "TableCaption")
            else:
                set_block_type(block, "Picture")
                continue

            # parse table
            table_row = []
            table_arrays = []
            line_y_start = None
            for line in block.lines:
                if line_y_start is None or abs(line_y_start - line.y_start) > 2:
                    if len(table_row) > 0:
                        table_arrays.append(table_row)
                        table_row = []
                    line_y_start = line.y_start
                table_row.append(line.prelim_text)
            if len(table_row) > 0:
                table_arrays.append(table_row)

            new_text = tabulate(table_arrays, headers="firstrow", tablefmt="github")
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
            table_idx += 1

            if debug_mode:
                with open("inline_table.md", "a") as file:
                    file.write(f"{new_text} \n")

            # get table image
            bboxes: List[List[float]] = [merged_bbox]
            table_image: io.BytesIO = get_image_bytes(
                doc[page_idx], merged_bbox, bboxes
            )
            if table_image is None:
                continue

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
