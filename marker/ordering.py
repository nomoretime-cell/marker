from copy import deepcopy
from typing import List

import torch
from transformers import LayoutLMv3ForSequenceClassification, LayoutLMv3Processor
from PIL import Image
import io
import fitz as pymupdf

from marker.schema import Page
from marker.settings import settings

processor = LayoutLMv3Processor.from_pretrained(settings.ORDERER_MODEL_NAME)


def load_ordering_model():
    model = LayoutLMv3ForSequenceClassification.from_pretrained(
        settings.ORDERER_MODEL_NAME,
        torch_dtype=settings.MODEL_DTYPE,
    ).to(settings.TORCH_DEVICE)
    model.eval()
    return model


def get_inference_data(doc_page: pymupdf.Page, inner_page: Page):
    bboxes = deepcopy([block.bbox for block in inner_page.blocks])
    words = ["."] * len(bboxes)

    pix = doc_page.get_pixmap(
        dpi=settings.LAYOUT_DPI, annots=False, clip=inner_page.bbox
    )
    png = pix.pil_tobytes(format="PNG")
    rgb_image = Image.open(io.BytesIO(png)).convert("RGB")

    page_box = inner_page.bbox
    pwidth = inner_page.width
    pheight = inner_page.height

    for box in bboxes:
        if box[0] < page_box[0]:
            box[0] = page_box[0]
        if box[1] < page_box[1]:
            box[1] = page_box[1]
        if box[2] > page_box[2]:
            box[2] = page_box[2]
        if box[3] > page_box[3]:
            box[3] = page_box[3]

        box[0] = int(box[0] / pwidth * 1000)
        box[1] = int(box[1] / pheight * 1000)
        box[2] = int(box[2] / pwidth * 1000)
        box[3] = int(box[3] / pheight * 1000)

    return rgb_image, bboxes, words


def batch_inference(rgb_images, bboxes, words, model):
    encoding = processor(
        rgb_images,
        text=words,
        boxes=bboxes,
        return_tensors="pt",
        truncation=True,
        padding="max_length",
        max_length=128,
    )

    if settings.CUDA:
        encoding["pixel_values"] = encoding["pixel_values"].to(torch.bfloat16)

    with torch.inference_mode():
        for k in ["bbox", "input_ids", "pixel_values", "attention_mask"]:
            encoding[k] = encoding[k].to(settings.TORCH_DEVICE)
        outputs = model(**encoding)
        logits = outputs.logits

    predictions = logits.argmax(-1).squeeze().tolist()
    if isinstance(predictions, int):
        predictions = [predictions]
    predictions = [model.config.id2label[p] for p in predictions]
    return predictions


def update_column_counts(doc, inner_pages, model, batch_size):
    for i in range(0, len(inner_pages), batch_size):
        page_batch = range(i, min(i + batch_size, len(inner_pages)))
        rgb_images = []
        bboxes = []
        words = []
        for pnum in page_batch:
            doc_page = doc[pnum]
            rgb_image, page_bboxes, page_words = get_inference_data(
                doc_page, inner_pages[pnum]
            )
            rgb_images.append(rgb_image)
            bboxes.append(page_bboxes)
            words.append(page_words)

        predictions = batch_inference(rgb_images, bboxes, words, model)
        for pnum, prediction in zip(page_batch, predictions):
            inner_pages[pnum].column_count = prediction


def order_blocks(
    doc: pymupdf.Document,
    inner_pages: List[Page],
    model,
    batch_size=settings.ORDERER_BATCH_SIZE,
) -> List[Page]:
    update_column_counts(doc, inner_pages, model, batch_size)

    for inner_page in inner_pages:
        if inner_page.column_count > 1:
            # Resort blocks based on position
            columns = [[] for _ in range(inner_page.column_count)]
            split_pos = inner_page.x_start + inner_page.width / inner_page.column_count

            for block in inner_page.blocks:
                for i in range(inner_page.column_count):
                    if block.x_start <= split_pos * (i + 1):
                        columns[i].append(block)
                        break

            inner_page.blocks = [block for column in columns for block in column]

    return inner_pages
