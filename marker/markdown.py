from marker.schema import MergedLine, MergedBlock, FullyMergedBlock, Page
import re
from typing import List
from enum import Enum


class IsContinuation(Enum):
    TRUE = 1
    FALSE = 2
    NONE = 3


def surround_text(s, char_to_insert):
    leading_whitespace = re.match(r"^(\s*)", s).group(1)
    trailing_whitespace = re.search(r"(\s*)$", s).group(1)
    stripped_string = s.strip()
    modified_string = char_to_insert + stripped_string + char_to_insert
    final_string = leading_whitespace + modified_string + trailing_whitespace
    return final_string


def merge_spans(blocks):
    merged_blocks = []
    for page in blocks:
        page_blocks = []
        for blocknum, block in enumerate(page.blocks):
            block_lines = []
            block_types = []
            for linenum, line in enumerate(block.lines):
                line_text = ""
                if len(line.spans) == 0:
                    continue
                fonts = []
                for i, span in enumerate(line.spans):
                    font = span.font.lower()
                    next_font = None
                    next_idx = 1
                    while len(line.spans) > i + next_idx:
                        next_span = line.spans[i + next_idx]
                        next_font = next_span.font.lower()
                        next_idx += 1
                        if len(next_span.text.strip()) > 2:
                            break

                    fonts.append(font)
                    block_types.append(span.block_type)
                    span_text = span.text

                    # Don't bold or italicize very short sequences
                    # Avoid bolding first and last sequence so lines can be joined properly
                    if len(span_text) > 3 and 0 < i < len(line.spans) - 1:
                        if "ital" in font and (
                            not next_font or "ital" not in next_font
                        ):
                            span_text = surround_text(span_text, "*")
                        elif "bold" in font and (
                            not next_font or "bold" not in next_font
                        ):
                            span_text = surround_text(span_text, "**")
                    line_text += span_text
                block_lines.append(
                    MergedLine(text=line_text, fonts=fonts, bbox=line.bbox)
                )
            if len(block_lines) > 0:
                page_blocks.append(
                    MergedBlock(
                        lines=block_lines,
                        pnum=block.pnum,
                        bbox=block.bbox,
                        block_types=block_types,
                    )
                )
        merged_blocks.append(page_blocks)

    return merged_blocks


def block_surround(text, block_type):
    if block_type == "Section-header":
        if not text.startswith("#"):
            text = "\n## " + text.strip().title() + "\n"
    elif block_type == "Title":
        if not text.startswith("#"):
            text = "# " + text.strip().title() + "\n"
    elif block_type == "Table":
        text = "\n" + text + "\n"
    elif block_type == "List-item":
        pass
    elif block_type == "Code":
        text = "\n" + text + "\n"
    return text


def line_separator(
    prev_line_text: str,
    new_line_text: str,
    block_type: str,
    is_continuation: IsContinuation,
):
    lowercase_letters: str = "a-zà-öø-ÿа-яşćăâđêôơưþðæøå"

    # 以任意数量的字符（除换行符外）开始，后跟小写字母范围中的一个字符，然后是短横线（减号）字符，最后是零个或一个空白字符，并且行结尾
    # "a-"：匹配成功，因为以小写字母 "a" 结尾，并以短横线结尾。
    # "b -"：匹配成功，因为以小写字母 "b" 结尾，并以空格和短横线结尾。
    # "c\n-"：匹配成功，因为以小写字母 "c" 结尾，并以换行符和短横线结尾（由于使用了 re.DOTALL 标志）。
    # "xyz"：匹配失败，因为没有以短横线结尾。
    # "def -\n"：匹配失败，因为以空格和短横线结尾，并以换行符结尾，\s?$ 部分不匹配换行符。
    hyphen_front_pattern = re.compile(rf".*[{lowercase_letters}][-]\s?$", re.DOTALL)

    # 以小写字母范围中的任意一个字符开头的字符串。
    # "a"：匹配成功，因为以小写字母 "a" 开头。
    # "b"：匹配成功，因为以小写字母 "b" 开头。
    # "x"：匹配成功，因为以小写字母 "x" 开头。
    # "A"：匹配失败，因为以大写字母 "A" 开头，而模式只匹配小写字母范围中的字符。
    # "123"：匹配失败，因为以数字开头，而不是小写字母。
    hyphen_rear_pattern = re.compile(rf"^[{lowercase_letters}]")

    number_head_pattern = re.compile(r"^\s?[0-9]", re.DOTALL)

    prev_line_text = prev_line_text.rstrip()
    new_line_text = new_line_text.lstrip()

    if (
        prev_line_text
        and hyphen_front_pattern.match(prev_line_text)
        and hyphen_rear_pattern.match(new_line_text)
    ):
        prev_line_text = re.split(r"[-—]\s?$", prev_line_text)[0]
        return prev_line_text.rstrip() + new_line_text.lstrip()
    elif block_type in ["Title", "Section-header"]:
        if number_head_pattern.match(new_line_text):
            return prev_line_text + "\n\n## " + new_line_text
        elif not number_head_pattern.match(new_line_text):
            return prev_line_text.rstrip() + " " + new_line_text.lstrip()
    elif block_type == "List-item" and number_head_pattern.match(new_line_text):
        return prev_line_text + "\n\n" + new_line_text
    elif is_continuation != IsContinuation.NONE:
        if is_continuation == IsContinuation.TRUE:
            return prev_line_text.rstrip() + " " + new_line_text.lstrip()
        elif is_continuation == IsContinuation.FALSE:
            return prev_line_text + "\n\n" + new_line_text
    # 是否换行不取决于是否以 paragraph_end_pattern 结尾，而是：缩进；行间隔增大
    else:
        return prev_line_text + " " + new_line_text


def line_separator_old(
    prev_line_text: str,
    new_line_text: str,
    block_type: str,
    is_continuation: IsContinuation,
):
    lowercase_letters: str = "a-zà-öø-ÿа-яşćăâđêôơưþðæøå"
    uppercase_letters: str = "A-ZÀ-ÖØ-ßА-ЯŞĆĂÂĐÊÔƠƯÞÐÆØÅ"

    # 以任意数量的字符（除换行符外）开始，后跟小写字母范围中的一个字符或逗号，然后是零个或一个空白字符，并且行结尾。
    # "abc "：匹配成功，因为以小写字母 "c" 结尾，并以空白字符结尾。
    # "def,"：匹配成功，因为以小写字母 "f" 结尾，并以逗号结尾。
    # "xyz"：匹配失败，因为没有以小写字母或逗号结尾。
    # "abc\ndef,"：匹配失败，因为 re.DOTALL 标志使.元字符能够匹配换行符，而 \s?$ 部分不匹配换行符，导致整个模式匹配失败。
    line_front_pattern = re.compile(rf".*[{lowercase_letters},0-9]\s?$", re.DOTALL)

    # 以零个或一个空白字符开始，后跟大写字母范围或小写字母范围中的一个字符。
    # "A"：匹配成功，因为以大写字母 "A" 开头。
    # "b"：匹配成功，因为以小写字母 "b" 开头。
    # " xyz"：匹配成功，因为以空格和小写字母 "x" 开头（由于使用了 ^\s? 部分）。
    # "  Y"：匹配失败，因为以两个空格和大写字母 "Y" 开头，而 ^\s? 部分只匹配零个或一个空白字符。
    # "123"：匹配失败，因为以数字开头，而不是大写字母或小写字母。

    line_rear_pattern = re.compile(
        rf"^\s?[{uppercase_letters}{lowercase_letters}]", re.DOTALL
    )

    line_rear_pattern2 = re.compile(
        rf"^\s?[{uppercase_letters},{lowercase_letters},0-9,.*]", re.DOTALL
    )

    # 以任意数量的字符（除换行符外）开始，后跟句号、问号或感叹号中的一个字符，然后是零个或一个空白字符，并且行结尾。
    # "Hello world."：匹配成功，因为以句号结尾。
    # "What's your name?"：匹配成功，因为以问号结尾。
    # "It's raining!"：匹配成功，因为以感叹号结尾。
    # "The cat is black."：匹配成功，因为以句号结尾。
    # "Hello"：匹配失败，因为没有以句号、问号或感叹号结尾。
    # "Hello\n"：匹配失败，因为以换行符结尾，而 \s?$ 部分不匹配换行符。
    paragraph_end_pattern = re.compile(r".*[.?!]\s?$", re.DOTALL)

    # 用于匹配以大写字母开头的字符串行
    # "Hello, world!"：匹配成功，因为行以大写字母开头。
    # " This is a test"：匹配成功，因为行以一个空白字符开头。
    # "123ABC"：匹配失败，因为行不以大写字母开头。
    # "a sentence."：匹配失败，因为行不以大写字母开头。
    uppercase_head_pattern = re.compile(rf"^\s?[{uppercase_letters}]", re.DOTALL)

    # 用于匹配以两个或更多个空白字符开头，并且后面紧跟着一个大写字母的字符串行
    # "Hello, world!"：匹配失败，因为行开头没有两个以上空白字符。
    # " A"：匹配成功，因为行以两个空白字符开头，后面紧跟着一个大写字母。
    # " ABC"：匹配成功，因为行以四个空白字符开头，后面紧跟着一个大写字母。
    uppercase_indent_head_pattern = re.compile(
        rf"^\s{2,}[{uppercase_letters}]", re.DOTALL
    )

    # 用于匹配不以大写字母开头的字符串行
    # "Hello, world!"：匹配失败，因为行以大写字母开头。
    # " this is a test"：匹配成功，因为行以一个空白字符开头，后面紧跟着一个小写字母。
    # "123abc"：匹配成功，因为行以数字开头。
    # "a sentence."：匹配成功，因为行以小写字母开头。
    not_uppercase_head_pattern = re.compile(rf"^\s?[^{uppercase_letters}]", re.DOTALL)

    if (
        line_front_pattern.match(prev_line_text)
        and line_rear_pattern.match(new_line_text)
        and block_type == "Text"
    ):
        return prev_line_text.rstrip() + " " + new_line_text.lstrip()
    elif (
        block_type == "Text"
        and paragraph_end_pattern.match(prev_line_text)
        and uppercase_indent_head_pattern.match(new_line_text)
    ):
        return prev_line_text + "\n\n" + new_line_text
    elif block_type == "Text" and paragraph_end_pattern.match(prev_line_text):
        return prev_line_text.rstrip() + " " + new_line_text.lstrip()
    elif block_type == "Formula":
        return prev_line_text + " " + new_line_text
    elif (
        block_type == "Text"
        and paragraph_end_pattern.match(prev_line_text)
        and not_uppercase_head_pattern.match(new_line_text)
    ) or (
        block_type == "Text"
        and paragraph_end_pattern.match(prev_line_text)
        and uppercase_head_pattern.match(new_line_text)
    ):
        return prev_line_text.rstrip() + " " + new_line_text.lstrip()


def block_separator(line1, line2, block_type1, block_type2):
    sep = "\n"
    if block_type1 == "Text":
        sep = "\n\n"

    return sep + line2


def merge_lines(blocks, page_blocks: List[Page]):
    text_blocks = []
    prev_type = None
    prev_line = None
    prev_line_gap = -1
    block_text = ""
    block_type = ""
    for page in blocks:
        is_newpage: bool = True
        for block in page:
            block_type = block.most_common_block_type()
            if block_type != prev_type and prev_type:
                text_blocks.append(
                    FullyMergedBlock(
                        text=block_surround(block_text, prev_type), block_type=prev_type
                    )
                )
                block_text = ""

            prev_type = block_type
            # Join lines in the block together properly
            for i, line in enumerate(block.lines):
                if line.text.strip() == "":
                    continue
                # TODO: 多页时 "\n" 由 Code 部分引入
                # line.text = line.text.replace("\n", "")

                if_update_prev_line: bool = True
                if prev_line:
                    # Get gap with previous line
                    line_gap = abs(line.bbox[3] - prev_line.bbox[3])
                    line_indent = line.bbox[0] - prev_line.bbox[0]

                    if line_gap <= 5:
                        # In same line -> IsContinuation.TRUE
                        is_continuation: IsContinuation = IsContinuation.TRUE
                        if_update_prev_line = False
                    elif line_indent > 10:  # TODO 多栏时，这个问题还需要再考虑下
                        # This line indent is bigger than Prev line 10 -> IsContinuation.FALSE
                        is_continuation: IsContinuation = IsContinuation.FALSE
                    elif prev_line_gap != -1:
                        # In different line
                        if line_gap > (prev_line_gap + 10) and not is_newpage:
                            # Gap is bigger than previous -> IsContinuation.FALSE
                            is_continuation: IsContinuation = IsContinuation.FALSE
                        else:
                            # Gap is equal or smaller than previous -> [Not sure]
                            is_continuation: IsContinuation = IsContinuation.NONE
                    else:
                        # prev_line_gap == -1 -> [Not sure]
                        is_continuation: IsContinuation = IsContinuation.NONE
                    if if_update_prev_line:
                        prev_line_gap = line_gap
                else:
                    # prev_line is NONE -> [Not sure]
                    is_continuation: IsContinuation = IsContinuation.NONE

                # Append text
                if block_text:
                    block_text = line_separator(
                        block_text, line.text, block_type, is_continuation
                    )
                else:
                    block_text = line.text

                # Reset var
                if if_update_prev_line:
                    prev_line = line
                if is_newpage:
                    is_newpage = False

    # Append the final block
    text_blocks.append(
        FullyMergedBlock(
            text=block_surround(block_text, prev_type), block_type=block_type
        )
    )
    return text_blocks


def if_paper(text_blocks) -> (bool, int, bool, int):
    containAbstract: bool = False
    indexAbstract: int = -1
    containRef: bool = False
    indexRef: int = -1
    for index, block in enumerate(text_blocks):
        if (
            (
                "Abstract".lower() in block.text.lower()
                or "Highlights".lower() in block.text.lower()
            )
            and block.block_type == "Section-header"
            and not containAbstract
        ):
            containAbstract = True
            indexAbstract = index
        if (
            "References".lower() in block.text.lower()
            and block.block_type == "Section-header"
            and not containRef
        ):
            containRef = True
            indexRef = index
    return containAbstract, indexAbstract, containRef, indexRef


def get_full_text(text_blocks):
    full_text = ""
    prev_block = None

    containAbstract, indexAbstract, containRef, indexRef = if_paper(text_blocks)

    for index, block in enumerate(text_blocks):
        if prev_block:
            if containAbstract and containRef:
                if index >= indexAbstract and index < indexRef:
                    full_text += block_separator(
                        prev_block.text,
                        block.text,
                        prev_block.block_type,
                        block.block_type,
                    )
            else:
                full_text += block_separator(
                    prev_block.text, block.text, prev_block.block_type, block.block_type
                )
        else:
            full_text += block.text
        prev_block = block
    return full_text
