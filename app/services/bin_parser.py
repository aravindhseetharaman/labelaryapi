from __future__ import annotations

import re
from app.models import (
    ParsedLabel, TextElement, FontElement, GraphicElement, BarcodeElement
)

# T type (x1,y1,x2,y2) width height mode  →  graphic box / line
_GRAPHIC_RE = re.compile(r'^T\s+(\d+)\s+\(([^)]+)\)\s+(\d+)\s+(\d+)\s*.*$')

# T type x y text
_TEXT_RE = re.compile(r'^T\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)$')

# ULTRA_FONT fontName (params) x y value
_FONT_RE = re.compile(r'^ULTRA_FONT\s+(\S+)\s+\([^)]+\)\s+(\d+)\s+(\d+)\s+(.+)$')

# B format x y height data
_BARCODE_RE = re.compile(r'^B\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)$')

# ! offset w h copies
_LABEL_HEADER_RE = re.compile(r'^!\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$')

# P copies
_PRINT_COUNT_RE = re.compile(r'^P\s+(\d+)$')


def parse(content: str) -> list[ParsedLabel]:
    labels: list[ParsedLabel] = []
    current = ParsedLabel()

    for raw_line in content.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.upper() == 'END':
            if not current.is_empty():
                labels.append(current)
            current = ParsedLabel()
            continue

        if line.startswith('!'):
            m = _LABEL_HEADER_RE.match(line)
            if m:
                current.label_width_dots = int(m.group(3))
                current.label_height_dots = int(m.group(4))
            continue

        if line.startswith('P '):
            m = _PRINT_COUNT_RE.match(line)
            if m:
                current.copies = int(m.group(1))
            continue

        if line.startswith('V ') or line.startswith('J '):
            continue

        if line.startswith('ULTRA_FONT'):
            m = _FONT_RE.match(line)
            if m:
                font_name = m.group(1)
                x = int(m.group(2))
                y = int(m.group(3))
                value = m.group(4).strip()
                current.add_element(FontElement(x=x, y=y, font_name=font_name, value=value))
            continue

        if line.startswith('T '):
            gm = _GRAPHIC_RE.match(line)
            if gm:
                w = int(gm.group(3))
                h = max(int(gm.group(4)), 2)
                current.add_element(GraphicElement(x=0, y=0, width=w, height=h))
            else:
                tm = _TEXT_RE.match(line)
                if tm:
                    type_ = int(tm.group(1))
                    x = int(tm.group(2))
                    y = int(tm.group(3))
                    text = tm.group(4).strip()
                    current.add_element(TextElement(x=x, y=y, type=type_, text=text))
            continue

        if line.startswith('B '):
            m = _BARCODE_RE.match(line)
            if m:
                fmt = m.group(1)
                x = int(m.group(2))
                y = int(m.group(3))
                height = int(m.group(4))
                data = m.group(5).strip()
                current.add_element(BarcodeElement(x=x, y=y, height=height, format=fmt, data=data))

    # capture any label not terminated by END
    if not current.is_empty():
        labels.append(current)

    return labels
