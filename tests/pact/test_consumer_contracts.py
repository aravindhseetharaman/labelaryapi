"""
Consumer contract tests — ShelfLabelClient → ShelfLabelAPI.

Each test defines what the consumer (a client app) expects from the provider
(the FastAPI service), then pactman records those interactions as a pact file
in pacts/ShelfLabelClient-ShelfLabelAPI.json.
"""
import pytest
import requests
from pactman import Consumer, Provider, EachLike, Like

PACT_DIR = "pacts"
CONSUMER = "ShelfLabelClient"
PROVIDER = "ShelfLabelAPI"

RAW_BIN = (
    "ULTRA_FONT C84 (8,0,0) 520 15 8.99\n"
    "T 1 520 84 Just For Men\n"
    "T 1 520 106 hair colorant\n"
    "B F5-(3:6) 520 228 31 210600008993\n"
    "END\n"
)


@pytest.fixture(scope="module")
def pact():
    return Consumer(CONSUMER).has_pact_with(
        Provider(PROVIDER),
        pact_dir=PACT_DIR,
        version="2.0.0",
    )


# ── 1. List Templates ──────────────────────────────────────────────────────────

def test_list_templates_contract(pact):
    """Consumer expects the full set of label templates."""
    pact.given("label templates exist").upon_receiving(
        "a GET request for all label templates"
    ).with_request(
        method="GET",
        path="/api/labels/templates",
    ).will_respond_with(
        200,
        headers={"Content-Type": "application/json"},
        body={
            "templates": EachLike(
                {
                    "label_type": Like("STANDARD_SEL"),
                    "display_name": Like("Standard Shelf Edge Label"),
                    "categories": EachLike("STANDARD"),
                }
            )
        },
    )

    with pact:
        resp = requests.get(f"{pact.uri}/api/labels/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert len(data["templates"]) >= 1


# ── 2. Convert BIN → ZPL via form content field ───────────────────────────────

def test_convert_form_content_contract(pact):
    """Consumer posts BIN content as a form field and expects ZPL + detection results."""
    pact.given("the API accepts BIN content via form field").upon_receiving(
        "a POST request to convert BIN content (form field) to ZPL"
    ).with_request(
        method="POST",
        path="/api/labels/convert",
    ).will_respond_with(
        200,
        headers={"Content-Type": "application/json"},
        body={
            "labelCount": Like(1),
            "zplLabels": EachLike("^XA^FO^XZ"),
            "detectedTypes": EachLike("STANDARD_SEL"),
            "message": Like("1 label(s) converted successfully"),
        },
    )

    with pact:
        resp = requests.post(
            f"{pact.uri}/api/labels/convert",
            data={"content": RAW_BIN},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["labelCount"] >= 1
        assert isinstance(body["zplLabels"], list)


# ── 3. Validate label — valid product ─────────────────────────────────────────

def test_validate_label_valid_contract(pact):
    """Consumer expects overall_valid=True when transaction data matches label."""
    pact.given("a standard product label can be validated").upon_receiving(
        "a POST request to validate a standard product label"
    ).with_request(
        method="POST",
        path="/api/labels/validate",
    ).will_respond_with(
        200,
        headers={"Content-Type": "application/json"},
        body={
            "overall_valid": Like(True),
            "label_count": Like(1),
            "results": EachLike(
                {
                    "label_index": Like(0),
                    "valid": Like(True),
                    "checks": Like({}),
                }
            ),
        },
    )

    with pact:
        resp = requests.post(
            f"{pact.uri}/api/labels/validate",
            data={
                "item_name": "Test Item",
                "item_price": "9.99",
                "item_category": "STANDARD",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_valid" in data
        assert "label_count" in data


# ── 4. Validate label — unknown category ──────────────────────────────────────

def test_validate_label_unknown_category_contract(pact):
    """Consumer expects overall_valid=False for an unrecognised category."""
    pact.given("an unknown item category is submitted").upon_receiving(
        "a POST request to validate with an unknown category"
    ).with_request(
        method="POST",
        path="/api/labels/validate",
    ).will_respond_with(
        200,
        headers={"Content-Type": "application/json"},
        body={
            "overall_valid": Like(False),
            "label_count": Like(1),
            "results": EachLike(
                {
                    "label_index": Like(0),
                    "valid": Like(False),
                    "checks": Like({}),
                }
            ),
        },
    )

    with pact:
        resp = requests.post(
            f"{pact.uri}/api/labels/validate",
            data={
                "item_name": "Test Item",
                "item_price": "9.99",
                "item_category": "UNKNOWN_XYZ",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_valid"] is False
