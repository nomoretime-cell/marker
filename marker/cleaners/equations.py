from copy import deepcopy
from typing import List, Tuple
from nougat import NougatModel
from nougat.utils.checkpoint import get_checkpoint
from marker.analyzer.spans import SpanType, SpansAnalyzer
from marker.bbox import is_in_same_line, merge_boxes
from marker.cleaners.nougat import get_image_bytes, get_tokens_len, process
from marker.cleaners.utils import save_debug_info
from marker.debug.data import dump_nougat_debug_data
from marker.settings import settings
from marker.schema import Page, Span, Line, Block, BlockType
from nougat.utils.device import move_to_device
import os
import io
import fitz
import logging

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
                if j >= 0:
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
                if i <= len(page.blocks) - 1:
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
    doc: fitz.Document,
    pages: List[Page],
    pages_types: List[List[BlockType]],
    spans_analyzer: SpansAnalyzer,
    model,
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
        regions, region_lens = get_page_equation_regions(page, pages_types[pnum], model)
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
        doc_page = doc[page_idx]
        for index, equation_region_index in enumerate(page_equation_region_index):
            # foreach equation region in one page
            #   "equation_region_index" is a list of block indices
            equation_bboxes, merged_equation_bbox = get_bbox(
                pages[page_idx], equation_region_index
            )
            equation_image: io.BytesIO = get_image_bytes(
                doc_page, merged_equation_bbox, equation_bboxes
            )

            doc_equation_images.append(equation_image)
            doc_merged_equation_bbox.append(merged_equation_bbox)

    # 3. Make batched predictions
    predictions: List[str] = process(
        doc_equation_images, flat_equation_region_lens, model, batch_size
    )

    # save result
    if debug_mode:
        for idx, image in enumerate(doc_equation_images):
            save_debug_info(image, "equations", page_idx, idx, [predictions[idx]])

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
            model,
        )
        converted_spans.extend(converted_span)
        pages[page_idx].blocks = new_page_blocks
        page_start += len(page_equation_region_list)
        successful_ocr += success_count
        unsuccessful_ocr += fail_count

    # If debug mode is on, dump out conversions for comparison
    dump_nougat_debug_data(doc, doc_equation_images, converted_spans)

    for page_idx, page in enumerate(pages):
        if page_idx == 0:
            continue
        replace_block_equations(page_idx, page, doc, spans_analyzer, model, debug_mode)

    return pages, {
        "successful_ocr": successful_ocr,
        "unsuccessful_ocr": unsuccessful_ocr,
        "equations": eq_count,
    }


def if_contain_equation_v1(line: Line) -> bool:
    contain_formula = False
    # LibertineMathMI_italic_serifed_proportional
    # CMSY10_italic_serifed_proportional
    for span in line.spans:
        if span.block_type == "Text" and (
            "Math".lower() in span.font.lower() or "CMSY10".lower() in span.font.lower()
        ):
            contain_formula = True
            break
    return contain_formula


def if_contain_equation_v2(line: Line) -> bool:
    contain_formula = False
    size_set: set = set()
    flags_set: set = set()
    block_type: str = ""
    for span in line.spans:
        # condition1: math font
        if span.block_type == "Text" and (
            "Math".lower() in span.font.lower() or "CMSY10".lower() in span.font.lower()
        ):
            contain_formula = True
            break
        # condition2: diff size and diff flags
        size_set.add(span.size)
        flags_set.add(span.flags)
        block_type = span.block_type
    if block_type == "Text" and len(size_set) > 1 and len(flags_set) > 1:
        contain_formula = True
    return contain_formula


def if_contain_equation_v3(line: Line, spans_analyzer: SpansAnalyzer) -> bool:
    contain_formula = False
    for span in line.spans:
        if span.block_type == "Text" and (
            span.font != spans_analyzer.get_most_font_type(SpanType.Text)
        ):
            contain_formula = True
            break
    return contain_formula


def replace_inline_equations(
    pnum: int,
    page: Page,
    doc: fitz.Document,
    spans_analyzer: SpansAnalyzer,
    nougat_model,
    debug_mode: bool = False,
):
    for block_idx, block in enumerate(page.blocks):
        for line_index, line in enumerate(block.lines):
            # check if line contain inline equation
            if if_contain_equation_v2(line):
                line_bboxes: List[List[float]] = []
                merged_line_bbox: List[float] = None

                # get prev & next line's bbox
                prev_bbox: List[float] = None
                next_bbox: List[float] = None
                if (line_index - 1) >= 0 and (line_index - 1) <= (len(block.lines) - 1):
                    prev_bbox = block.lines[line_index - 1].bbox
                if (line_index + 1) >= 0 and (line_index + 1) <= (len(block.lines) - 1):
                    next_bbox = block.lines[line_index + 1].bbox
                current_bbox = block.lines[line_index].bbox

                # resized line bbox
                x1 = current_bbox[0] - 5
                y1 = (
                    current_bbox[1]
                    if prev_bbox is None or current_bbox[1] > prev_bbox[3]
                    else (current_bbox[1] + ((prev_bbox[3] - current_bbox[1]) / 2)) + 1
                )
                x2 = current_bbox[2] + 5
                y2 = (
                    current_bbox[3]
                    if next_bbox is None or next_bbox[1] > current_bbox[3]
                    else (next_bbox[1] + ((current_bbox[3] - next_bbox[1]) / 2)) - 1
                )
                merged_line_bbox = [x1, y1, x2, y2]
                line_bboxes.append(merged_line_bbox)

                # get line image
                equation_images: List[io.BytesIO] = []
                equation_token_list: List[int] = []
                equation_image: io.BytesIO = get_image_bytes(
                    doc[pnum], merged_line_bbox, line_bboxes
                )
                if equation_image is None:
                    continue

                # get result from nougat
                equation_images.append(equation_image)
                tokens_len = get_tokens_len(line.prelim_text, nougat_model)
                equation_token_list.append(tokens_len)
                predictions: List[str] = process(
                    equation_images, equation_token_list, nougat_model, 1
                )

                # replace line's text
                block.lines[line_index].spans = [
                    Span(
                        text=predictions[0],
                        bbox=line.bbox,
                        span_id=f"{pnum}_{block_idx}_Inline_Latex",
                        font="Inline_Latex",
                        color=0,
                        block_type="Text",
                    )
                ]


def replace_block_equations(
    pnum: int,
    page: Page,
    doc: fitz.Document,
    spans_analyzer: SpansAnalyzer,
    nougat_model,
    debug_mode: bool = False,
):
    for block_idx, block in enumerate(page.blocks):
        containe_equations = False
        for line in block.lines:
            # check if line contain inline equation
            if if_contain_equation_v2(line):
                containe_equations = True
                break
        if not containe_equations:
            continue

        merged_bbox: List[float] = block.bbox
        bboxes: List[List[float]] = [merged_bbox]

        # get block image
        equation_images: List[io.BytesIO] = []
        equation_token_list: List[int] = []
        equation_image: io.BytesIO = get_image_bytes(doc[pnum], merged_bbox, bboxes)
        if equation_image is None:
            continue

        # get result from nougat
        equation_images.append(equation_image)
        tokens_len = get_tokens_len(block.prelim_text, nougat_model)
        equation_token_list.append(tokens_len)
        predictions: List[str] = process(
            equation_images, equation_token_list, nougat_model, 1
        )

        if debug_mode:
            # Save equation image
            save_debug_info(
                equation_image, "inline_equations", pnum, block_idx, predictions
            )

        # replace block's text
        page.blocks[block_idx].lines = [
            Line(
                spans=[
                    Span(
                        text=predictions[0],
                        bbox=merged_bbox,
                        span_id=f"{pnum}_{block_idx}_fixeq",
                        font="Latex",
                        color=0,
                        block_type="Formula",
                    )
                ],
                bbox=merged_bbox,
            )
        ]
