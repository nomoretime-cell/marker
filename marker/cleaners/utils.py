from marker.bbox import merge_boxes
from marker.schema import Line, Span, Block, Page
from copy import deepcopy
from typing import List


def set_block_type(block: Block, type: str):
    for line in block.lines:
        for span in line.spans:
            span.block_type = type


def merge_target_blocks(pages: List[Page], block_type: str):
    target_lines = []
    target_bbox = None
    for page in pages:
        new_page_blocks = []
        for block in page.blocks:
            # other block
            if block.most_common_block_type() != block_type:
                if len(target_lines) > 0:
                    # merge last target block
                    target_block = Block(
                        lines=deepcopy(target_lines), pnum=page.pnum, bbox=target_bbox
                    )
                    new_page_blocks.append(target_block)
                    # clear target block
                    target_lines = []
                    target_bbox = None

                # merge other block
                new_page_blocks.append(block)
                continue

            # merge target block
            target_lines.extend(block.lines)
            if target_bbox is None:
                # init target bbox
                target_bbox = block.bbox
            else:
                # merge target bbox
                target_bbox = merge_boxes(target_bbox, block.bbox)

        if len(target_lines) > 0:
            # merge last target block
            target_block = Block(
                lines=deepcopy(target_lines), pnum=page.pnum, bbox=target_bbox
            )
            new_page_blocks.append(target_block)
            # clear target block
            target_lines = []
            target_bbox = None

        # update new page blocks
        page.blocks = new_page_blocks
