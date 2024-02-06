import io
import os
from marker.bbox import merge_boxes
from marker.cleaners.nougat import get_image_bytes, get_tokens_len, process
from marker.schema import Line, Span, Block, Page
from copy import deepcopy
from tabulate import tabulate
from typing import List
import re
import textwrap
import fitz


def merge_table_blocks(pages: List[Page]):
    table_lines = []
    table_bbox = None
    for page in pages:
        new_page_blocks = []
        pnum = page.pnum
        for block in page.blocks:
            # other block
            if block.most_common_block_type() != "Table":
                if len(table_lines) > 0:
                    # merge last table block
                    table_block = Block(
                        lines=deepcopy(table_lines), pnum=pnum, bbox=table_bbox
                    )
                    new_page_blocks.append(table_block)
                    table_lines = []
                    table_bbox = None

                # merge other block
                new_page_blocks.append(block)
                continue

            # table block
            table_lines.extend(block.lines)
            if table_bbox is None:
                # init table bbox
                table_bbox = block.bbox
            else:
                # merge table bbox
                table_bbox = merge_boxes(table_bbox, block.bbox)

        if len(table_lines) > 0:
            # merge last table block
            table_block = Block(lines=deepcopy(table_lines), pnum=pnum, bbox=table_bbox)
            new_page_blocks.append(table_block)
            table_lines = []
            table_bbox = None

        # update new page blocks
        page.blocks = new_page_blocks


def replace_tables(doc: fitz.Document, pages: List[Page], model, debug_mode: bool):
    for page_idx, page in enumerate(pages):
        for block_idx, block in enumerate(page.blocks):
            if block.most_common_block_type() != "Table":
                # not table block
                continue

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
                # do not contain caption
                continue

            merged_bbox: List[float] = block.bbox

            if prev_block_type is not None and "Table" in prev_block.prelim_text:
                # merge previous caption
                merged_bbox = merge_boxes(block.bbox, prev_block.bbox)
                pass
            elif next_block_type is not None and "Table" in next_block.prelim_text:
                # merge next caption
                merged_bbox = merge_boxes(block.bbox, next_block_type.bbox)
                pass
            else:
                # do not contain table caption
                continue

            bboxes: List[List[float]] = [merged_bbox]
            table_image: io.BytesIO = get_image_bytes(
                doc[page_idx], merged_bbox, bboxes
            )
            if table_image is None:
                continue

            # get result from nougat
            table_images: List[io.BytesIO] = []
            table_token_list: List[int] = []
            table_images.append(table_image)
            tokens_len = get_tokens_len(block.prelim_text, model)
            table_token_list.append(tokens_len)
            predictions: List[str] = process(table_images, table_token_list, model, 1)

            if debug_mode:
                # Save equation image
                file_name = f"table_{page_idx}_{block_idx}.bmp"
                save_path = os.path.join("./", file_name)
                with open(save_path, "wb") as f:
                    f.write(table_image.getvalue())
                with open("inline_table.md", "a") as file:
                    file.write(f"table_{page_idx}_{block_idx} {predictions}  \n")


def create_new_tables(pages: List[Page]):
    table_idx = 0
    dot_pattern = re.compile(r"(\s*\.\s*){4,}")
    dot_multiline_pattern = re.compile(r".*(\s*\.\s*){4,}.*", re.DOTALL)

    for page in pages:
        for block_idx, block in enumerate(page.blocks):
            if block.most_common_block_type() != "Table" or len(block.lines) < 3:
                continue

            table_rows = []
            y_coord = None
            row = []
            for line in block.lines:
                for span in line.spans:
                    if y_coord != span.y_start:
                        if len(row) > 0:
                            table_rows.append(row)
                            row = []
                        y_coord = span.y_start

                    text = span.text
                    if dot_multiline_pattern.match(text):
                        text = dot_pattern.sub(" ", text)
                    row.append(text)
            if len(row) > 0:
                table_rows.append(row)

            # Don't render tables if they will be too large
            if (
                max([len("".join(r)) for r in table_rows]) > 300
                or len(table_rows[0]) > 8
                or len(table_rows[0]) < 2
            ):
                continue

            new_text = tabulate(table_rows, headers="firstrow", tablefmt="github")
            new_span = Span(
                bbox=block.bbox,
                span_id=f"{table_idx}_fix_table",
                font="Table",
                color=0,
                block_type="Table",
                text=new_text,
            )
            new_line = Line(bbox=block.bbox, spans=[new_span])
            block.lines = [new_line]
            table_idx += 1
    return table_idx
