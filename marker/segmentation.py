import logging
from typing import List

from transformers import LayoutLMv3ForTokenClassification

from marker.bbox import unnormalize_box
from transformers.models.layoutlmv3.image_processing_layoutlmv3 import normalize_box
import io
from PIL import Image
from transformers import LayoutLMv3Processor
import numpy as np
from marker.settings import settings
from marker.schema import Page, BlockType
import torch
from math import isclose
import fitz
from PIL import ImageDraw, ImageFont

# Otherwise some images can be truncated
Image.MAX_IMAGE_PIXELS = None

processor = LayoutLMv3Processor.from_pretrained(
    settings.LAYOUT_MODEL_NAME, apply_ocr=False
)

CHUNK_KEYS = ["input_ids", "attention_mask", "bbox", "offset_mapping"]
NO_CHUNK_KEYS = ["pixel_values"]


def load_segment_model():
    model = LayoutLMv3ForTokenClassification.from_pretrained(
        settings.LAYOUT_MODEL_NAME,
        torch_dtype=settings.MODEL_DTYPE,
    ).to(settings.TORCH_DEVICE)

    model.config.id2label = {
        0: "Caption",
        1: "Footnote",
        2: "Formula",
        3: "List-item",
        4: "Page-footer",
        5: "Page-header",
        6: "Picture",
        7: "Section-header",
        8: "Table",
        9: "Text",
        10: "Title",
    }

    model.config.label2id = {v: k for k, v in model.config.id2label.items()}
    return model


def get_page_image(mupdf_page: fitz.Page, inner_page: Page):
    # 1pt = 1/72 inch (pt可以理解成物理尺寸)
    # image width = inch width * dpi
    # image height = inch height * dpi

    # inner_page.bbox = [0.0, 0.0, 612.0, 792.0]  612 is 612pt, 792 is 792pt
    # image width(816) = 612pt/72(pt/inch) * 96 dpi
    # image height(1056) = 792pt/72(pt/inch) * 96 dpi

    # pt 也被用来表述 字体大小，页面元素，行间距，行高等
    # dpi（Dots Per Inch）的值在数字图像上下文指的是 像素，否则是 打印点
    # 图像的大小取决于 dpi

    pixmap = mupdf_page.get_pixmap(
        dpi=settings.LAYOUT_DPI, annots=False, clip=inner_page.bbox
    )
    png_image = Image.open(io.BytesIO(pixmap.pil_tobytes(format="PNG")))
    image = png_image.convert("RGB")
    image_width, image_height = image.size

    page_pt_box = inner_page.bbox
    page_pt_width = inner_page.width
    page_pt_height = inner_page.height

    assert isclose(
        image_width / page_pt_width, image_height / page_pt_height, abs_tol=2e-2
    )

    return image, page_pt_box, page_pt_width, page_pt_height


def get_line_info(inner_page, page_pt_box):
    line_pt_box_vector = []
    line_text_vector = []
    lines = inner_page.get_all_lines()
    for line in lines:
        # Bounding boxes sometimes overflow
        if line.bbox[0] < page_pt_box[0]:
            line.bbox[0] = page_pt_box[0]
        if line.bbox[1] < page_pt_box[1]:
            line.bbox[1] = page_pt_box[1]
        if line.bbox[2] > page_pt_box[2]:
            line.bbox[2] = page_pt_box[2]
        if line.bbox[3] > page_pt_box[3]:
            line.bbox[3] = page_pt_box[3]

        # Handle case when boxes are 0 or less width or height
        if line.bbox[2] <= line.bbox[0]:
            logging.error("Zero width box found, cannot convert properly")
            raise ValueError
        if line.bbox[3] <= line.bbox[1]:
            logging.error("Zero height box found, cannot convert properly")
            raise ValueError
        line_pt_box_vector.append(line.bbox)
        line_text_vector.append(line.prelim_text)
    return line_pt_box_vector, line_text_vector


def get_page_encoding(page: fitz.Page, inner_page: Page):
    if len(inner_page.get_all_lines()) == 0:
        return [], []

    image, page_pt_box, page_pt_width, page_pt_height = get_page_image(page, inner_page)
    line_pt_box_vector, line_text_vector = get_line_info(inner_page, page_pt_box)

    # Normalize boxes for model (scale to 1000x1000)
    line_pt_box_vector = [
        normalize_box(line_box, page_pt_width, page_pt_height)
        for line_box in line_pt_box_vector
    ]
    for line_box in line_pt_box_vector:
        # Verify that boxes are all valid
        assert len(line_box) == 4
        assert (max(line_box)) <= 1000
        assert (min(line_box)) >= 0

    encoding = processor(
        image,
        text=line_text_vector,
        boxes=line_pt_box_vector,
        return_offsets_mapping=True,
        truncation=True,
        return_tensors="pt",
        stride=settings.LAYOUT_CHUNK_OVERLAP,
        padding="max_length",
        max_length=settings.LAYOUT_MODEL_MAX,
        return_overflowing_tokens=True,
    )

    bbox = list(encoding["bbox"])
    input_ids = list(encoding["input_ids"])
    attention_mask = list(encoding["attention_mask"])
    pixel_values = list(encoding["pixel_values"])
    offset_mapping = encoding.pop("offset_mapping")

    assert (
        len(bbox)
        == len(input_ids)
        == len(attention_mask)
        == len(pixel_values)
        == len(offset_mapping)
    )

    list_encoding = []
    for i in range(len(bbox)):
        list_encoding.append(
            {
                "bbox": bbox[i],
                "input_ids": input_ids[i],
                "attention_mask": attention_mask[i],
                "pixel_values": pixel_values[i],
                "offset_mapping": offset_mapping[i],
            }
        )

    metadata = {
        "original_bbox": line_pt_box_vector,
        "pwidth": page_pt_width,
        "pheight": page_pt_height,
    }
    return image, list_encoding, metadata


def get_provisional_boxes(pred, box, is_subword, start_idx=0):
    prov_predictions = [pred_ for idx, pred_ in enumerate(pred) if not is_subword[idx]][
        start_idx:
    ]
    prov_boxes = [box_ for idx, box_ in enumerate(box) if not is_subword[idx]][
        start_idx:
    ]
    return prov_predictions, prov_boxes


def get_features(doc, pages: List[Page]):
    encodings = []
    pages_metadata = []
    pages_sample = []
    images = []
    for i in range(len(pages)):
        image, encoding, other_data = get_page_encoding(doc[i], pages[i])
        encodings.extend(encoding)
        pages_metadata.append(other_data)
        pages_sample.append(len(encoding))
        images.append(image)
    return images, encodings, pages_metadata, pages_sample


def predict_block_types(encodings, segment_model, batch_size):
    all_predictions = []
    for i in range(0, len(encodings), batch_size):
        batch_start = i
        batch_end = min(i + batch_size, len(encodings))
        batch = encodings[batch_start:batch_end]

        model_in = {}
        for k in ["bbox", "input_ids", "attention_mask", "pixel_values"]:
            model_in[k] = torch.stack([b[k] for b in batch]).to(settings.TORCH_DEVICE)

        if settings.CUDA:
            model_in["pixel_values"] = model_in["pixel_values"].to(torch.bfloat16)

        with torch.inference_mode():
            outputs = segment_model(**model_in)
            logits = outputs.logits

        predictions = logits.argmax(-1).squeeze().tolist()
        if len(predictions) == settings.LAYOUT_MODEL_MAX:
            predictions = [predictions]
        all_predictions.extend(predictions)
    return all_predictions


def match_predictions_to_boxes(
    encodings, pages_metadata, pages_sample, segment_model, predictions
) -> List[List[BlockType]]:
    assert len(encodings) == len(predictions) == sum(pages_sample)
    assert len(pages_metadata) == len(pages_sample)

    page_start = 0
    pages_types = []
    for pnum, page_sample in enumerate(pages_sample):
        # Page has no blocks
        if page_sample == 0:
            pages_types.append([])
            continue

        page_metadata = pages_metadata[pnum]
        page_end = min(page_start + page_sample, len(predictions))
        page_predictions = predictions[page_start:page_end]
        page_encodings = encodings[page_start:page_end]
        
        encoding_boxes = [e["bbox"] for e in page_encodings]
        encoding_offset_mapping = [e["offset_mapping"] for e in page_encodings]
        metadata_pwidth = page_metadata["pwidth"]
        metadata_pheight = page_metadata["pheight"]
        metadata_original_bbox = page_metadata["original_bbox"]

        for i in range(len(encoding_boxes)):
            assert len(encoding_boxes[i]) == len(page_predictions[i])

        predicted_block_types = []
        for i, (pred, box, mapped) in enumerate(
            zip(page_predictions, encoding_boxes, encoding_offset_mapping)
        ):
            box = box.tolist()
            is_subword = np.array(mapped)[:, 0] != 0
            overlap_adjust = 0
            if i > 0:
                overlap_adjust = (
                    1
                    + settings.LAYOUT_CHUNK_OVERLAP
                    - sum(is_subword[: 1 + settings.LAYOUT_CHUNK_OVERLAP])
                )

            prov_predictions, prov_boxes = get_provisional_boxes(
                pred, box, is_subword, overlap_adjust
            )

            for prov_box, prov_prediction in zip(prov_boxes, prov_predictions):
                if prov_box == [0, 0, 0, 0]:
                    continue
                block_type = BlockType(
                    block_type=segment_model.config.id2label[prov_prediction],
                    bbox=prov_box,
                )

                # Sometimes blocks will cross chunks, unclear why
                if (
                    len(predicted_block_types) == 0
                    or prov_box != predicted_block_types[-1].bbox
                ):
                    predicted_block_types.append(block_type)

        # Align bboxes
        # This will search both lists to find matching bboxes
        # This will align both sets of bboxes by index
        # If there are duplicate bboxes, it may result in issues
        page_types = []
        for i in range(len(metadata_original_bbox)):
            unnorm_box = unnormalize_box(metadata_original_bbox[i], metadata_pwidth, metadata_pheight)
            appended = False
            for j in range(len(predicted_block_types)):
                if metadata_original_bbox[i] == predicted_block_types[j].bbox:
                    predicted_block_types[j].bbox = unnorm_box
                    page_types.append(predicted_block_types[j])
                    appended = True
                    break
            if not appended:
                page_types.append(BlockType(block_type="Text", bbox=unnorm_box))
        pages_types.append(page_types)
        page_start += page_sample
    return pages_types


def save_image(pages, images, pages_types):
    for i, (image, page_types) in enumerate(zip(images, pages_types)):
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        image_width, image_height = images[i].size
        ratio = image_height / pages[i].height
        for block_type in page_types:
            label = block_type.block_type
            bbox = block_type.bbox
            draw.rectangle(
                (
                    (bbox[0] * ratio, bbox[1] * ratio),
                    (bbox[2] * ratio, bbox[3] * ratio),
                ),
                outline="red",
                width=2,
            )
            draw.text((bbox[0] * ratio, bbox[1] * ratio), label, fill="red", font=font)

        image_save_path = f"segmentation_image_page_{i}.png"
        image.save(image_save_path)
        print(f"Saved: {image_save_path}")


def get_pages_types(
    doc,
    pages: List[Page],
    segment_model,
    batch_size=settings.LAYOUT_BATCH_SIZE,
    debug_mode=False,
) -> List[List[BlockType]]:
    images, encodings, pages_metadata, pages_sample = get_features(doc, pages)
    predictions = predict_block_types(encodings, segment_model, batch_size)
    pages_types = match_predictions_to_boxes(
        encodings, pages_metadata, pages_sample, segment_model, predictions
    )
    assert len(pages_types) == len(pages)
    if debug_mode:
        save_image(pages, images, pages_types)
    return pages_types
