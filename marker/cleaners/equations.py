import io
from copy import deepcopy
from functools import partial
from typing import List

import torch
from nougat import NougatModel
from nougat.postprocessing import markdown_compatible
from nougat.utils.checkpoint import get_checkpoint
import re
from PIL import Image, ImageDraw
from nougat.utils.dataset import ImageDataset

from marker.bbox import should_merge_blocks, merge_boxes
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


def mask_bbox(png_image, bbox, selected_bboxes):
    mask = Image.new("L", png_image.size, 0)  # 'L' mode for grayscale
    draw = ImageDraw.Draw(mask)
    first_x = bbox[0]
    first_y = bbox[1]
    bbox_height = bbox[3] - bbox[1]
    bbox_width = bbox[2] - bbox[0]

    for box in selected_bboxes:
        # Fit the box to the selected region
        new_box = (
            box[0] - first_x,
            box[1] - first_y,
            box[2] - first_x,
            box[3] - first_y,
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


def get_nougat_image(page, merged_block_bboxes, block_bboxes):
    pix = page.get_pixmap(dpi=settings.NOUGAT_DPI, clip=merged_block_bboxes)
    png = pix.pil_tobytes(format="BMP")
    png_image = Image.open(io.BytesIO(png))
    png_image = mask_bbox(png_image, merged_block_bboxes, block_bboxes)
    png_image = png_image.convert("RGB")

    img_out = io.BytesIO()
    png_image.save(img_out, format="BMP")
    return img_out


def replace_latex_fences(text):
    # Replace block equations: \[ ... \] with $$...$$
    text = re.sub(r"\\\[(.*?)\\\]", r"$$\1$$\n", text)

    # Replace inline math: \( ... \) with $...$
    text = re.sub(r"\\\((.*?)\\\)", r"$\1$ ", text)

    return text


def get_nougat_text_batched(images, reformat_region_lens, nougat_model, batch_size):
    if len(images) == 0:
        return []

    predictions = [""] * len(images)

    dataset = ImageDataset(
        images,
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
        max_idx = min(min_idx + batch_size, len(images))
        max_length = max(reformat_region_lens[min_idx:max_idx])
        max_length = min(max_length, settings.NOUGAT_MODEL_MAX)
        max_length += settings.NOUGAT_TOKEN_BUFFER

        nougat_model.config.max_length = max_length
        model_output = nougat_model.inference(
            image_tensors=sample, early_stopping=False
        )
        for j, output in enumerate(model_output["predictions"]):
            disclaimer = ""
            token_count = get_total_nougat_tokens(output, nougat_model)
            if token_count >= max_length - 1:
                disclaimer = "[TRUNCATED]"

            image_idx = idx * batch_size + j
            predictions[image_idx] = (
                replace_latex_fences(markdown_compatible(output)) + disclaimer
            )
    return predictions


def get_total_nougat_tokens(text, nougat_model):
    tokenizer = nougat_model.decoder.tokenizer
    tokens = tokenizer(text)
    return len(tokens["input_ids"])


def find_page_equation_regions(page: Page, page_types: List[BlockType], nougat_model):
    i = 0
    reformatted_blocks = set()
    reformat_regions = []
    block_lens = []

    equation_lines = [b.bbox for b in page_types if b.block_type == "Formula"]
    if len(equation_lines) == 0:
        return [], []

    while i < len(page.blocks):
        block_obj = page.blocks[i]
        block_text = block_obj.prelim_text
        block_bbox = block_obj.bbox
        # Check if the block contains an equation
        if not block_obj.contains_equation(equation_lines):
            i += 1
            continue

        # contains equation
        selected_blocks = [(i, block_obj)]
        if i > 0:
            # Find previous blocks to merge
            j = i - 1
            prev_block_obj = page.blocks[j]
            prev_block_bbox = prev_block_obj.bbox
            while (
                (
                    should_merge_blocks(prev_block_bbox, block_bbox)
                    or prev_block_obj.contains_equation(equation_lines)
                )
                and j >= 0
                and j not in reformatted_blocks
            ):
                block_bbox = merge_boxes(prev_block_bbox, block_bbox)
                prev_block_obj = page.blocks[j]
                prev_block_bbox = prev_block_obj.bbox
                prelim_block_text = prev_block_obj.prelim_text + " " + block_text
                if (
                    get_total_nougat_tokens(prelim_block_text, nougat_model)
                    >= settings.NOUGAT_MODEL_MAX
                ):
                    break

                block_text = prelim_block_text
                selected_blocks.append((j, prev_block_obj))
                j -= 1

        if i < len(page.blocks) - 1:
            # Merge subsequent boxes
            next_block = page.blocks[i + 1]
            next_bbox = next_block.bbox
            while (
                should_merge_blocks(block_bbox, next_bbox)
                or next_block.contains_equation(equation_lines)
                or len(selected_blocks) <= 3
            ) and i + 1 < len(page.blocks):
                block_bbox = merge_boxes(block_bbox, next_bbox)
                prelim_block_text = block_text + " " + next_block.prelim_text
                if (
                    get_total_nougat_tokens(prelim_block_text, nougat_model)
                    >= settings.NOUGAT_MODEL_MAX
                ):
                    break

                block_text = prelim_block_text
                i += 1
                selected_blocks.append((i, next_block))
                if i + 1 < len(page.blocks):
                    next_block = page.blocks[i + 1]
                    next_bbox = next_block.bbox

        total_tokens = get_total_nougat_tokens(block_text, nougat_model)
        ordered_blocks = sorted(([sb[0] for sb in selected_blocks]))
        if total_tokens < settings.NOUGAT_MODEL_MAX:
            # Get indices of all blocks to merge
            reformat_regions.append(ordered_blocks)
            block_lens.append(total_tokens)
            reformatted_blocks.update(ordered_blocks)
        else:
            # Reset i to the original value
            i = selected_blocks[0][0]

        i += 1

    return reformat_regions, block_lens


def get_bboxes_for_region(page, region):
    block_bboxes = []
    merged_block_bboxes = None
    for idx in region:
        block = page.blocks[idx]
        bbox = block.bbox
        if merged_block_bboxes is None:
            merged_block_bboxes = bbox
        else:
            merged_block_bboxes = merge_boxes(merged_block_bboxes, bbox)
        block_bboxes.append(bbox)
    return block_bboxes, merged_block_bboxes


def replace_blocks_with_nougat_predictions(
    page_blocks: Page, merged_boxes, reformat_regions, predictions, pnum, nougat_model
):
    new_blocks = []
    converted_spans = []
    current_region = 0
    idx = 0
    success_count = 0
    fail_count = 0
    while idx < len(page_blocks.blocks):
        block = page_blocks.blocks[idx]
        if (
            current_region >= len(reformat_regions)
            or idx < reformat_regions[current_region][0]
        ):
            new_blocks.append(block)
            idx += 1
            continue

        orig_block_text = " ".join(
            [
                page_blocks.blocks[i].prelim_text
                for i in reformat_regions[current_region]
            ]
        )
        nougat_text = predictions[current_region]
        conditions = [
            len(nougat_text) > 0,
            # not any(
            #     [word in nougat_text for word in settings.NOUGAT_HALLUCINATION_WORDS]
            # ),
            get_total_nougat_tokens(nougat_text, nougat_model)
            < settings.NOUGAT_MODEL_MAX,  # Make sure we didn't run to the token max
            len(nougat_text) > len(orig_block_text) * 0.8,
            len(nougat_text.strip()) > 0,
        ]

        idx = reformat_regions[current_region][-1] + 1
        if not all(conditions):
            fail_count += 1
            converted_spans.append(None)
            for i in reformat_regions[current_region]:
                new_blocks.append(page_blocks.blocks[i])
        else:
            success_count += 1
            block_line = Line(
                spans=[
                    Span(
                        text=nougat_text,
                        bbox=merged_boxes[current_region],
                        span_id=f"{pnum}_{idx}_fixeq",
                        font="Latex",
                        color=0,
                        block_type="Formula",
                    )
                ],
                bbox=merged_boxes[current_region],
            )
            converted_spans.append(deepcopy(block_line.spans[0]))
            new_blocks.append(
                Block(lines=[block_line], bbox=merged_boxes[current_region], pnum=pnum)
            )
        current_region += 1
    return new_blocks, success_count, fail_count, converted_spans


def replace_equations(
    doc,
    pages: List[Page],
    pages_types: List[List[BlockType]],
    nougat_model,
    batch_size=settings.NOUGAT_BATCH_SIZE,
) -> (List[Page], dict):
    unsuccessful_ocr = 0
    successful_ocr = 0

    # Find potential equation regions, and length of text in each region
    reformat_regions = []
    reformat_region_lens = []
    for pnum, page in enumerate(pages):
        regions, region_lens = find_page_equation_regions(
            page, pages_types[pnum], nougat_model
        )
        reformat_regions.append(regions)
        reformat_region_lens.append(region_lens)

    eq_count = sum([len(x) for x in reformat_regions])

    # Get images for each region
    flat_reformat_region_lens = [
        item for sublist in reformat_region_lens for item in sublist
    ]
    images = []
    merged_boxes = []
    for page_idx, reformat_regions_page in enumerate(reformat_regions):
        page_obj = doc[page_idx]
        for index, reformat_region in enumerate(reformat_regions_page):
            block_bboxes, merged_block_bboxes = get_bboxes_for_region(
                pages[page_idx], reformat_region
            )
            png_image = get_nougat_image(page_obj, merged_block_bboxes, block_bboxes)

            # Save equation image
            file_name = f"equation_{page_idx}_{index}.bmp"
            save_path = os.path.join("./", file_name)
            with open(save_path, "wb") as f:
                f.write(png_image.getvalue())

            images.append(png_image)
            merged_boxes.append(merged_block_bboxes)

    # Make batched predictions
    predictions = get_nougat_text_batched(
        images, flat_reformat_region_lens, nougat_model, batch_size
    )

    # Replace blocks with predictions
    page_start = 0
    converted_spans = []
    for page_idx, reformat_regions_page in enumerate(reformat_regions):
        page_predictions = predictions[
            page_start : page_start + len(reformat_regions_page)
        ]
        page_boxes = merged_boxes[page_start : page_start + len(reformat_regions_page)]
        (
            new_page_blocks,
            success_count,
            fail_count,
            converted_span,
        ) = replace_blocks_with_nougat_predictions(
            pages[page_idx],
            page_boxes,
            reformat_regions_page,
            page_predictions,
            page_idx,
            nougat_model,
        )
        converted_spans.extend(converted_span)
        pages[page_idx].blocks = new_page_blocks
        page_start += len(reformat_regions_page)
        successful_ocr += success_count
        unsuccessful_ocr += fail_count

    # If debug mode is on, dump out conversions for comparison
    dump_nougat_debug_data(doc, images, converted_spans)

    return pages, {
        "successful_ocr": successful_ocr,
        "unsuccessful_ocr": unsuccessful_ocr,
        "equations": eq_count,
    }
