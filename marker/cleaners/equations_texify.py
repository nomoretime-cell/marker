import io
from typing import List
from texify.inference import batch_inference
from texify.model.model import load_model
from texify.model.processor import load_processor
from marker.cleaners.equations import get_mask_image

from marker.settings import settings

from PIL import Image
import logging


class TexifyModel:
    def __init__(self):
        self.processor = load_processor(checkpoint=settings.TEXIFY_MODEL_NAME)
        self.model = self.load_model()

    def load_model(self):
        model = load_model(
            checkpoint=settings.TEXIFY_MODEL_NAME,
            device=settings.TORCH_DEVICE,
            dtype=settings.TEXIFY_DTYPE,
        )

        return model

    def get_equation_image(self, page, merged_block_bbox, block_bboxes):
        try:
            pix = page.get_pixmap(dpi=settings.NOUGAT_DPI, clip=merged_block_bbox)
            png = pix.pil_tobytes(format="BMP")
            png_image = Image.open(io.BytesIO(png))
            png_image = get_mask_image(png_image, merged_block_bbox, block_bboxes)
            png_image = png_image.convert("RGB")

            return png_image

        except Exception as exception:
            logging.error(exception)
            return None

    def save_image(self, image, path):
        image.save(path, format="BMP")

    def get_tokens_len(self, text):
        tokenizer = self.processor.tokenizer
        tokens = tokenizer(text)
        return len(tokens["input_ids"])

    def process(
        self,
        equation_image_list: List[io.BytesIO],
        equation_token_list: List[int],
        model,
        batch_size,
    ):
        if len(equation_image_list) == 0:
            return []
        predictions = [""] * len(equation_image_list)
        for i in range(0, len(equation_image_list), batch_size):
            # Dynamically set max length to save inference time
            min_idx = i
            max_idx = min(min_idx + batch_size, len(equation_image_list))
            max_length = max(equation_token_list[min_idx:max_idx])
            max_length = min(max_length, settings.TEXIFY_MODEL_MAX)
            max_length += settings.TEXIFY_TOKEN_BUFFER

            model_output = batch_inference(
                equation_image_list[min_idx:max_idx],
                model,
                self.processor,
                max_tokens=max_length,
            )

            for j, output in enumerate(model_output):
                token_count = self.get_tokens_len(output, model)
                if token_count >= max_length - 1:
                    output = ""

                image_idx = i + j
                predictions[image_idx] = output
        return predictions
