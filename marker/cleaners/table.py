from marker.bbox import merge_boxes
from marker.schema import Line, Span, Block, Page
from copy import deepcopy
from tabulate import tabulate
from typing import List
import re
import textwrap


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


def create_new_tables(blocks: List[Page]):
    table_idx = 0
    dot_pattern = re.compile(r"(\s*\.\s*){4,}")
    dot_multiline_pattern = re.compile(r".*(\s*\.\s*){4,}.*", re.DOTALL)

    for page in blocks:
        for block in page.blocks:
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
