import io
from copy import deepcopy
from functools import partial
from typing import List, Tuple

import torch
from nougat import NougatModel
from nougat.postprocessing import markdown_compatible
from nougat.utils.checkpoint import get_checkpoint
import re
from PIL import Image, ImageDraw
from nougat.utils.dataset import ImageDataset

from marker.bbox import is_in_same_line, merge_boxes
from marker.debug.data import dump_nougat_debug_data
from marker.settings import settings
from marker.schema import Page, Span, Line, Block, BlockType
from nougat.utils.device import move_to_device
import os

os.environ["TOKENIZERS_PARALLELISM"] = "false"


def load_nougat_model():
    ckpt = get_checkpoint(
        settings.NOUGAT_MODEL_NAME, model_tag=settings.NOUGAT_MODEL_TAG, download=False
    )
    nougat_model = NougatModel.from_pretrained(ckpt)
    if settings.TORCH_DEVICE != "cpu":
        move_to_device(nougat_model, bf16=settings.CUDA, cuda=settings.CUDA)
    nougat_model.eval()
    return nougat_model


def get_mask_image(png_image, bbox: List[float], selected_bboxes: List[List[float]]):
    mask = Image.new("L", png_image.size, 0)  # 'L' mode for grayscale
    draw = ImageDraw.Draw(mask)
    bbox_x = bbox[0]
    bbox_y = bbox[1]
    bbox_height = bbox[3] - bbox[1]
    bbox_width = bbox[2] - bbox[0]

    for box in selected_bboxes:
        # Fit the box to the selected region
        new_box = (
            box[0] - bbox_x,
            box[1] - bbox_y,
            box[2] - bbox_x,
            box[3] - bbox_y,
        )
        # Fit mask to image bounds versus the pdf bounds
        resized = (
            new_box[0] / bbox_width * png_image.size[0],
            new_box[1] / bbox_height * png_image.size[1],
            new_box[2] / bbox_width * png_image.size[0],
            new_box[3] / bbox_height * png_image.size[1],
        )
        draw.rectangle(resized, fill=255)

    result = Image.composite(
        png_image, Image.new("RGBA", png_image.size, "white"), mask
    )
    return result


def get_equation_image(page, merged_block_bbox, block_bboxes):
    pix = page.get_pixmap(dpi=settings.NOUGAT_DPI, clip=merged_block_bbox)
    png = pix.pil_tobytes(format="BMP")
    png_image = Image.open(io.BytesIO(png))
    png_image = get_mask_image(png_image, merged_block_bbox, block_bboxes)
    png_image = png_image.convert("RGB")

    img_out = io.BytesIO()
    png_image.save(img_out, format="BMP")
    return img_out


def get_tokens_len(text, nougat_model):
    tokenizer = nougat_model.decoder.tokenizer
    tokens = tokenizer(text)
    return len(tokens["input_ids"])


def get_page_equation_regions(page: Page, page_types: List[BlockType], nougat_model):
    i = 0
    equation_blocks_index_set = set()
    equation_blocks_index_list: List[List[int]] = []
    tokens_len_list: List[int] = []

    # get all equation lines
    equation_lines_bbox: List[List[float]] = [
        b.bbox for b in page_types if b.block_type == "Formula"
    ]
    if len(equation_lines_bbox) == 0:
        # current page do not contain equation
        return [], []

    # current page contain equation
    while i < len(page.blocks):
        # current block object
        block_obj = page.blocks[i]
        # check if the block contains an equation
        if not block_obj.contains_equation(equation_lines_bbox):
            i += 1
            continue

        # cache first equation
        equation_blocks: List[Tuple[int, Block]] = [(i, block_obj)]
        equation_block_text = block_obj.prelim_text

        # Merge surrounding blocks
        if i > 0:
            # Merge previous blocks
            j = i - 1
            prev_block = page.blocks[j]
            prev_bbox = prev_block.bbox
            while (
                (
                    is_in_same_line(prev_bbox, block_obj.bbox)
                    or prev_block.contains_equation(equation_lines_bbox)
                )
                and j >= 0
                and j not in equation_blocks_index_set
            ):
                # block_bbox = merge_boxes(prev_bbox, block_bbox)

                # check if tokens is overwhelm
                prelim_block_text = prev_block.prelim_text + " " + equation_block_text
                if (
                    get_tokens_len(prelim_block_text, nougat_model)
                    >= settings.NOUGAT_MODEL_MAX
                ):
                    break

                equation_block_text = prelim_block_text
                equation_blocks.append((j, prev_block))
                j -= 1
                prev_block = page.blocks[j]
                prev_bbox = prev_block.bbox

        if i < len(page.blocks) - 1:
            # Merge subsequent blocks
            i = i + 1
            next_block = page.blocks[i]
            next_bbox = next_block.bbox
            while (
                is_in_same_line(block_obj.bbox, next_bbox)
                or next_block.contains_equation(equation_lines_bbox)
                or len(equation_blocks) <= 3
            ) and i <= len(page.blocks) - 1:
                # block_bbox = merge_boxes(block_bbox, next_bbox)

                # check if tokens is overwhelm
                prelim_block_text = equation_block_text + " " + next_block.prelim_text
                if (
                    get_tokens_len(prelim_block_text, nougat_model)
                    >= settings.NOUGAT_MODEL_MAX
                ):
                    break

                equation_block_text = prelim_block_text
                equation_blocks.append((i, next_block))
                i += 1
                next_block = page.blocks[i]
                next_bbox = next_block.bbox

        tokens_len = get_tokens_len(equation_block_text, nougat_model)
        equation_blocks_index = sorted(([sb[0] for sb in equation_blocks]))
        if tokens_len < settings.NOUGAT_MODEL_MAX:
            # Get indices of all blocks to merge
            equation_blocks_index_list.append(equation_blocks_index)
            tokens_len_list.append(tokens_len)
            equation_blocks_index_set.update(equation_blocks_index)
        else:
            # Reset i to the original value
            i = equation_blocks[0][0]

        i += 1

    return equation_blocks_index_list, tokens_len_list


def get_bbox(page: Page, region: List[int]):
    block_bboxes: List[List[float]] = []
    merged_block_bbox: List[float] = None
    for idx in region:
        block = page.blocks[idx]
        bbox = block.bbox
        if merged_block_bbox is None:
            merged_block_bbox = bbox
        else:
            merged_block_bbox = merge_boxes(merged_block_bbox, bbox)
        block_bboxes.append(bbox)
    return block_bboxes, merged_block_bbox


def add_latex_fences(text):
    # Replace block equations: \[ ... \] with $$...$$
    text = re.sub(r"\\\[(.*?)\\\]", r"$$\1$$\n", text)

    # Replace inline math: \( ... \) with $...$
    text = re.sub(r"\\\((.*?)\\\)", r"$\1$ ", text)

    return text


def process(
    equation_image_list: List[io.BytesIO],
    equation_token_list: List[int],
    nougat_model,
    batch_size,
):
    if len(equation_image_list) == 0:
        return []

    predictions: List[str] = [""] * len(equation_image_list)
    dataset = ImageDataset(
        equation_image_list,
        partial(nougat_model.encoder.prepare_input, random_padding=False),
    )

    dataloader = torch.utils.data.DataLoader(
        dataset,
        batch_size=batch_size,
        pin_memory=True,
        shuffle=False,
    )

    for idx, sample in enumerate(dataloader):
        # Dynamically set max length to save inference time
        min_idx = idx * batch_size
        max_idx = min(min_idx + batch_size, len(equation_image_list))
        max_length = max(equation_token_list[min_idx:max_idx])
        max_length = min(max_length, settings.NOUGAT_MODEL_MAX)
        max_length += settings.NOUGAT_TOKEN_BUFFER

        nougat_model.config.max_length = max_length
        model_output = nougat_model.inference(
            image_tensors=sample, early_stopping=False
        )
        for j, output in enumerate(model_output["predictions"]):
            disclaimer = ""
            token_count = get_tokens_len(output, nougat_model)
            if token_count >= max_length - 1:
                disclaimer = "[TRUNCATED]"

            image_idx = idx * batch_size + j
            predictions[image_idx] = (
                add_latex_fences(markdown_compatible(output)) + disclaimer
            )
    return predictions


def replace_blocks(
    page: Page,
    merged_equation_boxes: List[List[float]],
    equation_region_list: List[List[int]],
    predictions: List[str],
    pnum: int,
    nougat_model,
):
    region_idx: int = 0
    block_idx: int = 0
    success_count: int = 0
    fail_count: int = 0
    replaced_blocks: List[Block] = []
    converted_spans: List[Span] = []
    while block_idx < len(page.blocks):
        block = page.blocks[block_idx]
        if (
            region_idx >= len(equation_region_list)
            or block_idx < equation_region_list[region_idx][0]
        ):
            replaced_blocks.append(block)
            block_idx += 1
            continue

        orig_block_text = " ".join(
            [
                page.blocks[b_idx].prelim_text
                for b_idx in equation_region_list[region_idx]
            ]
        )
        current_region_prediction = predictions[region_idx]
        conditions = [
            len(current_region_prediction) > 0,
            # not any(
            #     [word in current_region_prediction for word in settings.NOUGAT_HALLUCINATION_WORDS]
            # ),
            get_tokens_len(current_region_prediction, nougat_model)
            < settings.NOUGAT_MODEL_MAX,  # Make sure we didn't run to the token max
            len(current_region_prediction) > len(orig_block_text) * 0.8,
            len(current_region_prediction.strip()) > 0,
        ]

        block_idx = equation_region_list[region_idx][-1] + 1
        if not all(conditions):
            fail_count += 1
            converted_spans.append(None)
            for i in equation_region_list[region_idx]:
                replaced_blocks.append(page.blocks[i])
        else:
            success_count += 1
            line = Line(
                spans=[
                    Span(
                        text=current_region_prediction,
                        bbox=merged_equation_boxes[region_idx],
                        span_id=f"{pnum}_{block_idx}_fixeq",
                        font="Latex",
                        color=0,
                        block_type="Formula",
                    )
                ],
                bbox=merged_equation_boxes[region_idx],
            )
            converted_spans.append(deepcopy(line.spans[0]))
            replaced_blocks.append(
                Block(
                    lines=[line],
                    bbox=merged_equation_boxes[region_idx],
                    pnum=pnum,
                )
            )
        region_idx += 1
    return replaced_blocks, success_count, fail_count, converted_spans


def replace_equations(
    doc,
    pages: List[Page],
    pages_types: List[List[BlockType]],
    nougat_model,
    batch_size=settings.NOUGAT_BATCH_SIZE,
    debug_mode: bool = False,
) -> (List[Page], dict):
    unsuccessful_ocr = 0
    successful_ocr = 0

    # 1. Find potential equation regions, and length of text in each region
    doc_equation_region_list: List[List[List[int]]] = []
    doc_equation_region_lens: List[List[int]] = []
    for pnum, page in enumerate(pages):
        regions: List[List[int]] = []
        region_lens: List[int] = []
        regions, region_lens = get_page_equation_regions(
            page, pages_types[pnum], nougat_model
        )
        doc_equation_region_list.append(regions)
        doc_equation_region_lens.append(region_lens)

    eq_count = sum([len(x) for x in doc_equation_region_list])

    # 2. Get images for each region
    flat_equation_region_lens: List[int] = [
        item for sublist in doc_equation_region_lens for item in sublist
    ]
    doc_equation_images: List[io.BytesIO] = []
    doc_merged_equation_bbox: List[List[float]] = []
    for page_idx, page_equation_region_index in enumerate(doc_equation_region_list):
        page_obj = doc[page_idx]
        for index, equation_region_index in enumerate(page_equation_region_index):
            # foreach equation region in one page
            #   "equation_region_index" is a list of block indices
            equation_bboxes, merged_equation_bbox = get_bbox(
                pages[page_idx], equation_region_index
            )
            equation_image: io.BytesIO = get_equation_image(
                page_obj, merged_equation_bbox, equation_bboxes
            )

            if debug_mode:
                # Save equation image
                file_name = f"equation_{page_idx}_{index}.bmp"
                save_path = os.path.join("./", file_name)
                with open(save_path, "wb") as f:
                    f.write(equation_image.getvalue())

            doc_equation_images.append(equation_image)
            doc_merged_equation_bbox.append(merged_equation_bbox)

    # 3. Make batched predictions
    predictions: List[str] = process(
        doc_equation_images, flat_equation_region_lens, nougat_model, batch_size
    )

    # 4. Replace blocks with predictions
    page_start = 0
    converted_spans = []
    for page_idx, page_equation_region_list in enumerate(doc_equation_region_list):
        # get predictions for current page
        page_predictions: List[str] = predictions[
            page_start : page_start + len(page_equation_region_list)
        ]
        # get boxes for current page
        page_merged_equation_bbox: List[List[float]] = doc_merged_equation_bbox[
            page_start : page_start + len(page_equation_region_list)
        ]
        (
            new_page_blocks,
            success_count,
            fail_count,
            converted_span,
        ) = replace_blocks(
            pages[page_idx],
            page_merged_equation_bbox,
            page_equation_region_list,
            page_predictions,
            page_idx,
            nougat_model,
        )
        converted_spans.extend(converted_span)
        pages[page_idx].blocks = new_page_blocks
        page_start += len(page_equation_region_list)
        successful_ocr += success_count
        unsuccessful_ocr += fail_count

    # If debug mode is on, dump out conversions for comparison
    dump_nougat_debug_data(doc, doc_equation_images, converted_spans)

    return pages, {
        "successful_ocr": successful_ocr,
        "unsuccessful_ocr": unsuccessful_ocr,
        "equations": eq_count,
    }
