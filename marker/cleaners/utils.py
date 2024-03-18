import io
import os
from marker.bbox import merge_boxes
from marker.schema import Line, Span, Block, Page
from copy import deepcopy
from typing import Callable, List, TypeVar


def set_block_type(block: Block, type: str):
    for line in block.lines:
        for span in line.spans:
            span.block_type = type


def set_special_block_type(block: Block, origin_type: str, type: str):
    for line in block.lines:
        for span in line.spans:
            if span.block_type == origin_type:
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


T = TypeVar("T")


def save_debug_doc_info(
    type: str, items: list[T], processor: Callable[[T], str]
) -> list[str]:
    real_path = f"debug/doc_info/{type}.txt"
    os.makedirs(os.path.dirname(real_path), exist_ok=True)
    with open(real_path, "w", encoding="utf-8") as file:
        for item in items:
            file.write(processor(item) + "\n")


def save_debug_info(image, model_name, page_idx, block_idx=0, results=None):
    # create file path
    real_path = f"debug/{model_name}/page_{page_idx}_{block_idx}.png"
    os.makedirs(os.path.dirname(real_path), exist_ok=True)

    # save input image
    if isinstance(image, io.BytesIO):
        with open(real_path, "wb") as f:
            f.write(image.getvalue())
    else:
        image.save(real_path)

    # save output result
    if results is not None:
        image_link = (
            f"![page_{page_idx}_{block_idx}.png](page_{page_idx}_{block_idx}.png)"
        )

        with open(f"debug/{model_name}/result.md", "a") as file:
            file.write(f"source_{page_idx}_{block_idx}: \n\n")
            file.write(image_link + " \n\n")
            file.write(f"result_{page_idx}_{block_idx}: \n\n")
            for result in results:
                file.write(f"{result}  \n\n")
