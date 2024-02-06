import io
import logging
import re
import torch
from nougat.utils.dataset import ImageDataset
from nougat.postprocessing import markdown_compatible
from functools import partial
from typing import List
from PIL import Image, ImageDraw
from marker.settings import settings


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


def get_image_bytes(page, merged_block_bbox, block_bboxes):
    try:
        pix = page.get_pixmap(dpi=settings.NOUGAT_DPI, clip=merged_block_bbox)
        png = pix.pil_tobytes(format="BMP")
        png_image = Image.open(io.BytesIO(png))
        png_image = get_mask_image(png_image, merged_block_bbox, block_bboxes)
        png_image = png_image.convert("RGB")

        img_out = io.BytesIO()
        png_image.save(img_out, format="BMP")
        return img_out

    except Exception as exception:
        logging.error(exception)
        return None


def get_tokens_len(text, nougat_model):
    tokenizer = nougat_model.decoder.tokenizer
    tokens = tokenizer(text)
    return len(tokens["input_ids"])


def process(
    equation_image_list: List[io.BytesIO],
    equation_token_list: List[int],
    model,
    batch_size,
):
    if len(equation_image_list) == 0:
        return []

    predictions: List[str] = [""] * len(equation_image_list)
    dataset = ImageDataset(
        equation_image_list,
        partial(model.encoder.prepare_input, random_padding=False),
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

        model.config.max_length = max_length
        model_output = model.inference(image_tensors=sample, early_stopping=False)
        for j, output in enumerate(model_output["predictions"]):
            disclaimer = ""
            token_count = get_tokens_len(output, model)
            if token_count >= max_length - 1:
                disclaimer = "[TRUNCATED]"

            image_idx = idx * batch_size + j
            predictions[image_idx] = (
                add_latex_fences(markdown_compatible(output)) + disclaimer
            )
    return predictions


def add_latex_fences(text):
    # Replace block equations: \[ ... \] with $$...$$
    text = re.sub(r"\\\[(.*?)\\\]", r"$$\1$$\n", text)

    # Replace inline math: \( ... \) with $...$
    text = re.sub(r"\\\((.*?)\\\)", r"$\1$ ", text)

    return text
