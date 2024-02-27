import io
import os
from typing import List
from marker.bbox import merge_boxes
from marker.cleaners.nougat import get_image_bytes
from marker.cleaners.utils import merge_target_blocks, set_block_type
from marker.schema import Block, Page
import fitz


def merge_picture_blocks(pages: List[Page]):
    merge_target_blocks(pages, "Picture")


def extend_picture_blocks(doc: fitz.Document, pages: List[Page], debug_mode: bool):
    for page_idx, page in enumerate(pages):
        for block_idx, block in enumerate(page.blocks):
            if block.most_common_block_type() != "Picture":
                continue

            # merge picture blocks
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

            merged_bbox: List[float] = block.bbox

            if prev_block_type is not None and "Figure" in prev_block.prelim_text:
                # merge previous caption
                merged_bbox = merge_boxes(block.bbox, prev_block.bbox)
                set_block_type(prev_block, "Caption")
            elif next_block_type is not None and "Figure" in next_block.prelim_text:
                # merge next caption
                merged_bbox = merge_boxes(block.bbox, next_block.bbox)
                set_block_type(next_block, "Caption")
            else:
                set_block_type(block, "Picture")
                continue

            # get picture image
            bboxes: List[List[float]] = [merged_bbox]
            table_image: io.BytesIO = get_image_bytes(
                doc[page_idx], merged_bbox, bboxes
            )
            if table_image is None:
                continue

            # save picture image
            if debug_mode:
                file_name = f"picture_{page_idx}_{block_idx}.bmp"
                save_path = os.path.join("./", file_name)
                with open(save_path, "wb") as f:
                    f.write(table_image.getvalue())
