from __future__ import annotations

import json
import pathlib

from app.models import ParsedLabel, FontElement, BarcodeElement, TextElement

_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / 'templates'

_templates: dict[str, dict] = {}


def _load_all() -> None:
    for path in _TEMPLATES_DIR.glob('*.json'):
        data = json.loads(path.read_text())
        _templates[data['label_type']] = data


_load_all()


def get_all_templates() -> list[dict]:
    return list(_templates.values())


def get_template_by_category(category: str) -> dict | None:
    upper = category.strip().upper()
    for tmpl in _templates.values():
        if upper in [c.upper() for c in tmpl['categories']]:
            return tmpl
    return None


def validate_label(
    zpl: str,
    item_name: str,
    item_price: str,
    item_description: str,
    item_category: str,
) -> dict:
    template = get_template_by_category(item_category)

    if template is None:
        return {
            'valid': False,
            'label_type': None,
            'error': f"No template found for category '{item_category}'. "
                     f"Available categories: {_all_categories()}",
            'checks': {},
        }

    zpl_upper = zpl.upper()
    checks = {}

    # Check required fields appear in ZPL
    checks['item_name'] = {
        'expected': item_name,
        'found': item_name.upper() in zpl_upper,
    }
    checks['item_price'] = {
        'expected': item_price,
        'found': item_price in zpl,
    }
    if item_description:
        checks['item_description'] = {
            'expected': item_description,
            'found': item_description.upper() in zpl_upper,
        }

    # Check label-type text markers (at least one must appear for typed labels)
    markers = template.get('text_markers', [])
    if markers:
        marker_found = any(m.upper() in zpl_upper for m in markers)
        checks['label_type_marker'] = {
            'expected': f"one of {markers}",
            'found': marker_found,
        }

    all_passed = all(c['found'] for c in checks.values())

    return {
        'valid': all_passed,
        'label_type': template['display_name'],
        'template_used': template['label_type'],
        'checks': checks,
    }


_CLEARANCE_MARKERS = {'CLEARANCE', 'FINAL SALE', 'FINAL'}
_MARKDOWN_MARKERS  = {'WAS', 'NOW', 'SAVE', 'REDUCED', 'MARKDOWN'}


def detect_label_type(label: ParsedLabel) -> str:
    has_price   = any(isinstance(e, FontElement) for e in label.elements)
    has_barcode = any(isinstance(e, BarcodeElement) for e in label.elements)
    texts = {
        e.text.upper()
        for e in label.elements
        if isinstance(e, TextElement)
    }
    all_text = ' '.join(texts)

    if any(m in all_text for m in _CLEARANCE_MARKERS):
        return 'CLEARANCE_LABEL'
    if any(m in all_text for m in _MARKDOWN_MARKERS):
        return 'MARKDOWN_LABEL'
    if has_price and has_barcode:
        return 'STANDARD_SEL'
    return 'SYSTEM_LABEL'


def _all_categories() -> list[str]:
    cats = []
    for tmpl in _templates.values():
        cats.extend(tmpl['categories'])
    return cats
