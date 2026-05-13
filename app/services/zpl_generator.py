from __future__ import annotations

import re
from app.models import (
    ParsedLabel, TextElement, FontElement, GraphicElement, BarcodeElement
)


def _escape(text: str) -> str:
    return text.replace('^', '\\^').replace('~', '\\~')


def _text_to_zpl(t: TextElement) -> str:
    char_h, char_w = (25, 20) if t.type == 1 else (18, 15)
    return f'^FO{t.x},{t.y}^A0N,{char_h},{char_w}^FD{_escape(t.text)}^FS\n'


def _font_to_zpl(f: FontElement) -> str:
    return f'^FO{f.x},{f.y}^A0N,45,40^FD{_escape(f.value)}^FS\n'


def _graphic_to_zpl(g: GraphicElement) -> str:
    thickness = max(g.height, 2)
    return f'^FO{g.x},{g.y}^GB{g.width},{thickness},{thickness}^FS\n'


def _barcode_to_zpl(b: BarcodeElement) -> str:
    bar_height = max(b.height * 3, 50)
    return f'^FO{b.x},{b.y}^BY2^BCN,{bar_height},Y,N,N^FD{_escape(b.data)}^FS\n'


def generate(label: ParsedLabel) -> str:
    parts = ['^XA\n']
    for element in label.elements:
        if isinstance(element, TextElement):
            parts.append(_text_to_zpl(element))
        elif isinstance(element, FontElement):
            parts.append(_font_to_zpl(element))
        elif isinstance(element, GraphicElement):
            parts.append(_graphic_to_zpl(element))
        elif isinstance(element, BarcodeElement):
            parts.append(_barcode_to_zpl(element))
    if label.copies > 1:
        parts.append(f'^PQ{label.copies}\n')
    parts.append('^XZ\n')
    return ''.join(parts)


def generate_all(labels: list[ParsedLabel]) -> list[str]:
    return [generate(label) for label in labels]


_PQ_RE = re.compile(r'\^PQ\d+\s*')


def strip_print_quantity(zpl: str) -> str:
    return _PQ_RE.sub('', zpl)
