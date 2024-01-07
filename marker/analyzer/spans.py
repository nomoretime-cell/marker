
from enum import Enum
from typing import List, Dict, Optional

from marker.schema import Span

class SpanType(Enum):
        Caption = "Caption"
        Footnote = "Footnote"
        Formula = "Formula"
        ListItem = "List-item"
        PageFooter = "Page-footer"
        PageHeader = "Page-header"
        Picture = "Picture"
        SectionHeader = "Section-header"
        Table = "Table"
        Text = "Text"
        Title = "Title"

class FontSize:
    def __init__(self, font_size: int, spans_size: Optional[int] = 0):
        self.font_size = font_size
        self.spans_size = spans_size
    
    def update_spans_size(self, spans_size: int):
        self.spans_size = spans_size
    def inc_spans_size(self):
        self.spans_size += 1
        
        
class SpansAnalyzer:
    def __init__(self, spans: List[Span]):
        # 场景需求
        # 1. 获取正文字体大小，解析正文中公式
        # 2. section-header类型识别错误
        # 3. footnote类型识别错误
        # 修复类型识别错误过程：(1)获取出现span类型频率低的字体，(2)结合上下文字体

        # 字体类型 + 字体大小 -> 所有 span
        # key = type + size, value = all span
        self.typeSize2spans : Dict[str, List[Span]] = {}
        # 字体类型 -> 所有 字体大小 可能
        # key = type, value = FontSize(包含 font_size 和 spans_size)
        self.type2fontSize : Dict[str, List[FontSize]] = {}
        
        for span in spans:
            type_size_key = span.block_type + "_" + str(span.size)
            if type_size_key not in self.typeSize2spans:
                self.typeSize2spans[type_size_key] = []
            self.typeSize2spans[type_size_key].append(span)
        
        for type_size, spans in self.typeSize2spans.items():
            type = type_size.split("_")[0]
            font_size = int(type_size.split("_")[1])
            if type not in self.type2fontSize:
                self.type2fontSize[type] = []
            self.type2fontSize[type].append(FontSize(font_size, len(spans)))
        
        # 对List[FontSize]按照spans_size字段降序排序
        for font_sizes in self.type2fontSize.values():
            font_sizes.sort(key=lambda x: x.spans_size, reverse=True)
            
        pass