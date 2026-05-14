"""
Automated API tests derived from ShelfLabelConverter-py.postman_collection.json.

Each test corresponds to one numbered Postman request:
  1. List Templates
  2. Convert BIN → ZPL (file upload)
  3. Convert BIN → ZPL (raw text/plain body)
  4. Preview Label 0 as PNG (file upload)
  5. Preview Label 1 as PNG (file upload)
  6. Validate Label against Sale Transaction
"""
from unittest.mock import patch

from tests.conftest import RAW_BIN_TEXT

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16  # minimal fake PNG bytes


# ── 1. List Templates ──────────────────────────────────────────────────────────

def test_list_templates(client):
    """GET /api/labels/templates — returns all stored label type templates."""
    response = client.get("/api/labels/templates")

    assert response.status_code == 200
    body = response.json()
    assert "templates" in body
    templates = body["templates"]
    assert isinstance(templates, list)
    assert len(templates) >= 1

    label_types = {t["label_type"] for t in templates}
    expected = {"STANDARD_SEL", "MARKDOWN_LABEL", "CLEARANCE_LABEL", "SYSTEM_LABEL"}
    assert expected.issubset(label_types), f"Missing templates: {expected - label_types}"


# ── 2. Convert BIN → ZPL + Auto-Detect Type (file upload) ─────────────────────

def test_convert_bin_file_upload(client, bin_bytes):
    """POST /api/labels/convert — multipart file upload."""
    response = client.post(
        "/api/labels/convert",
        files={"file": ("shelfitem.bin", bin_bytes, "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["labelCount"] >= 1
    assert isinstance(body["zplLabels"], list)
    assert len(body["zplLabels"]) == body["labelCount"]
    assert isinstance(body["detectedTypes"], list)
    assert len(body["detectedTypes"]) == body["labelCount"]
    assert "converted successfully" in body["message"]

    # First label should be a product label (STANDARD_SEL)
    assert body["detectedTypes"][0] == "STANDARD_SEL"


# ── 3. Convert BIN → ZPL + Auto-Detect Type (raw text/plain body) ─────────────

def test_convert_raw_text_body(client):
    """POST /api/labels/convert — raw text/plain body (no file upload)."""
    response = client.post(
        "/api/labels/convert",
        content=RAW_BIN_TEXT.encode(),
        headers={"Content-Type": "text/plain"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["labelCount"] == 2
    assert len(body["zplLabels"]) == 2
    assert body["detectedTypes"][0] == "STANDARD_SEL"
    assert body["detectedTypes"][1] == "SYSTEM_LABEL"

    # ZPL for the product label must include the price and item name
    zpl_0 = body["zplLabels"][0]
    assert "8.99" in zpl_0
    assert "Just For Men" in zpl_0 or "JUST FOR MEN" in zpl_0.upper()


# ── 4. Preview Label 0 as PNG (product label) ─────────────────────────────────

def test_preview_label_0_file_upload(client, bin_bytes):
    """POST /api/labels/preview/0 — returns PNG for label index 0."""
    with patch("app.services.labelary.render_to_png", return_value=FAKE_PNG):
        response = client.post(
            "/api/labels/preview/0",
            files={"file": ("shelfitem.bin", bin_bytes, "application/octet-stream")},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 0


# ── 5. Preview Label 1 as PNG (system label) ──────────────────────────────────

def test_preview_label_1_file_upload(client, bin_bytes):
    """POST /api/labels/preview/1 — returns PNG for label index 1."""
    with patch("app.services.labelary.render_to_png", return_value=FAKE_PNG):
        response = client.post(
            "/api/labels/preview/1",
            files={"file": ("shelfitem.bin", bin_bytes, "application/octet-stream")},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 0


def test_preview_index_out_of_range(client, bin_bytes):
    """POST /api/labels/preview/99 — returns 404 for a non-existent label index."""
    with patch("app.services.labelary.render_to_png", return_value=FAKE_PNG):
        response = client.post(
            "/api/labels/preview/99",
            files={"file": ("shelfitem.bin", bin_bytes, "application/octet-stream")},
        )

    assert response.status_code == 404


# ── 6. Validate Label against Sale Transaction ────────────────────────────────

def test_validate_label_standard(client, bin_bytes):
    """POST /api/labels/validate — validates label against sale transaction data."""
    response = client.post(
        "/api/labels/validate",
        data={
            "item_name": "Just For Men",
            "item_price": "8.99",
            "item_description": "hair colorant",
            "item_category": "STANDARD",
        },
        files={"file": ("shelfitem.bin", bin_bytes, "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert "overall_valid" in body
    assert "label_count" in body
    assert "results" in body
    assert body["label_count"] >= 1

    # Product label at index 0 should pass all checks
    product_result = next(r for r in body["results"] if r["label_index"] == 0)
    assert product_result["valid"] is True
    assert product_result["checks"]["item_name"]["found"] is True
    assert product_result["checks"]["item_price"]["found"] is True


def test_validate_label_system_label_skipped(client, bin_bytes):
    """System labels (END OF BATCH) must be skipped during validation."""
    response = client.post(
        "/api/labels/validate",
        data={
            "item_name": "Just For Men",
            "item_price": "8.99",
            "item_description": "hair colorant",
            "item_category": "STANDARD",
        },
        files={"file": ("shelfitem.bin", bin_bytes, "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    system_results = [r for r in body["results"] if r.get("skipped")]
    assert len(system_results) >= 1
    assert all(r["valid"] for r in system_results)


def test_validate_label_unknown_category(client, bin_bytes):
    """POST /api/labels/validate with an unknown item_category returns valid=False."""
    response = client.post(
        "/api/labels/validate",
        data={
            "item_name": "Just For Men",
            "item_price": "8.99",
            "item_description": "",
            "item_category": "UNKNOWN_CATEGORY_XYZ",
        },
        files={"file": ("shelfitem.bin", bin_bytes, "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["overall_valid"] is False
