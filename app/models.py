from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


@dataclass
class TextElement:
    x: int
    y: int
    type: int   # 1 = standard body, 0 = small/caption
    text: str


@dataclass
class FontElement:
    x: int
    y: int
    font_name: str
    value: str


@dataclass
class GraphicElement:
    x: int
    y: int
    width: int
    height: int


@dataclass
class BarcodeElement:
    x: int
    y: int
    height: int
    format: str
    data: str


LabelElement = Union[TextElement, FontElement, GraphicElement, BarcodeElement]


@dataclass
class ParsedLabel:
    elements: list = field(default_factory=list)
    copies: int = 1
    label_width_dots: int = 812   # 4" at 203 dpi
    label_height_dots: int = 406  # 2" at 203 dpi

    def add_element(self, element: LabelElement) -> None:
        self.elements.append(element)

    def is_empty(self) -> bool:
        return len(self.elements) == 0
