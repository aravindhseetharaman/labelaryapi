"""
Provider verification tests — ShelfLabelAPI.

Reads every pact file from pacts/ and replays each interaction against a
live FastAPI test server. Per-state request data is injected so form-body
endpoints receive the required fields, mirroring how a real consumer call
would look.
"""
import json
import pathlib
import threading
import time
from unittest.mock import patch

import pytest
import requests
import uvicorn

from app.main import app

PACT_DIR = pathlib.Path("pacts")
SAMPLES_DIR = pathlib.Path("samples")
PROVIDER_HOST = "localhost"
PROVIDER_PORT = 8765
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

RAW_BIN = (
    "ULTRA_FONT C84 (8,0,0) 520 15 8.99\n"
    "T 1 520 84 Just For Men\n"
    "T 1 520 106 hair colorant\n"
    "B F5-(3:6) 520 228 31 210600008993\n"
    "END\n"
)

# Provider-state → request data map.
# Each entry is the kwargs to pass to requests.request() for that interaction.
_STATE_EXTRA: dict[str, dict] = {
    "the API accepts BIN content via form field": {
        "data": {"content": RAW_BIN},
    },
    "a standard product label can be validated": {
        "files": {
            "file": (
                "shelfitem.bin",
                (SAMPLES_DIR / "shelfitem.bin").read_bytes(),
                "application/octet-stream",
            )
        },
        "data": {
            "item_name": "Just For Men",
            "item_price": "8.99",
            "item_category": "STANDARD",
            "item_description": "hair colorant",
        },
    },
    "an unknown item category is submitted": {
        "files": {
            "file": (
                "shelfitem.bin",
                (SAMPLES_DIR / "shelfitem.bin").read_bytes(),
                "application/octet-stream",
            )
        },
        "data": {
            "item_name": "Test Item",
            "item_price": "9.99",
            "item_category": "UNKNOWN_XYZ",
            "item_description": "",
        },
    },
}


# ── Provider server fixture ────────────────────────────────────────────────────

class _UvicornThread:
    def __init__(self):
        config = uvicorn.Config(
            app, host=PROVIDER_HOST, port=PROVIDER_PORT, log_level="error"
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()
        for _ in range(50):
            time.sleep(0.1)
            if self.server.started:
                return
        raise RuntimeError("Provider server failed to start")

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


@pytest.fixture(scope="module")
def provider_url():
    srv = _UvicornThread()
    with patch("app.services.labelary.render_to_png", return_value=FAKE_PNG):
        srv.start()
        yield f"http://{PROVIDER_HOST}:{PROVIDER_PORT}"
        srv.stop()


# ── Pact matching helpers ─────────────────────────────────────────────────────

def _apply_rules(data, spec, rules: dict, path: str = "$.body") -> list[str]:
    """Return a list of mismatch messages (empty = all matched)."""
    errors: list[str] = []

    if isinstance(spec, dict) and isinstance(data, dict):
        for key, val in spec.items():
            child_path = f"{path}.{key}"
            rule_key = child_path
            rule = rules.get(rule_key)
            if rule and rule.get("match") == "type":
                if not isinstance(data.get(key), type(val)):
                    errors.append(
                        f"{child_path}: type mismatch — "
                        f"expected {type(val).__name__}, got {type(data.get(key)).__name__}"
                    )
            elif key in data:
                errors.extend(_apply_rules(data[key], val, rules, child_path))
            else:
                # EachLike min:1 means key must be present
                min_rule = rules.get(child_path, {}).get("min")
                if min_rule is not None:
                    errors.append(f"{child_path}: key missing (min={min_rule})")
    elif isinstance(spec, list) and isinstance(data, list):
        min_rule = rules.get(path, {}).get("min")
        if min_rule and len(data) < min_rule:
            errors.append(f"{path}: list length {len(data)} < min {min_rule}")
        if spec and data:
            errors.extend(_apply_rules(data[0], spec[0], rules, f"{path}[*]"))

    return errors


def _verify_response(description: str, resp: requests.Response, expected: dict) -> None:
    expected_status = expected.get("status", 200)
    assert resp.status_code == expected_status, (
        f"[{description}] Status mismatch: expected {expected_status}, "
        f"got {resp.status_code}\nBody: {resp.text[:400]}"
    )

    expected_body = expected.get("body")
    if not expected_body:
        return

    content_type = resp.headers.get("content-type", "")
    if "application/json" not in content_type:
        return

    actual = resp.json()
    rules = expected.get("matchingRules", {})

    if rules:
        errors = _apply_rules(actual, expected_body, rules)
        assert not errors, (
            f"[{description}] Response body matching failures:\n"
            + "\n".join(f"  • {e}" for e in errors)
        )
    else:
        for key in expected_body:
            assert key in actual, f"[{description}] Missing key '{key}' in response"


# ── Replay helper ─────────────────────────────────────────────────────────────

def _replay_interaction(interaction: dict, base_url: str) -> None:
    description = interaction.get("description", "unknown")
    provider_state = interaction.get("providerState", "")
    req = interaction.get("request", {})
    expected = interaction.get("response", {})

    method = req.get("method", "GET").upper()
    path = req.get("path", "/")
    req_headers = req.get("headers", {})
    pact_body = req.get("body")

    url = f"{base_url}{path}"

    # Start with any pact-file-specified body
    kwargs: dict = {"headers": req_headers}
    if pact_body is not None:
        if isinstance(pact_body, dict):
            kwargs["data"] = pact_body
        elif isinstance(pact_body, str):
            kwargs["data"] = pact_body.encode()

    # Overlay provider-state specific data (form fields + files)
    state_extra = _STATE_EXTRA.get(provider_state, {})
    if state_extra:
        kwargs.update(state_extra)
        # Remove explicit Content-Type so requests sets multipart/form boundary
        kwargs["headers"] = {
            k: v for k, v in kwargs["headers"].items()
            if k.lower() != "content-type"
        }

    resp = requests.request(method, url, **kwargs)
    _verify_response(description, resp, expected)


# ── Parametrised provider tests ───────────────────────────────────────────────

def _collect_pact_interactions():
    params = []
    if not PACT_DIR.exists():
        return params
    for pact_file in sorted(PACT_DIR.glob("*.json")):
        data = json.loads(pact_file.read_text())
        consumer = data.get("consumer", {}).get("name", "?")
        provider = data.get("provider", {}).get("name", "?")
        for ia in data.get("interactions", []):
            label = f"{consumer}→{provider}: {ia.get('description', '?')}"
            params.append(pytest.param(ia, id=label))
    return params


@pytest.mark.parametrize("interaction", _collect_pact_interactions())
def test_provider_satisfies_contract(interaction, provider_url):
    """Provider must satisfy every interaction defined in the consumer pact files."""
    _replay_interaction(interaction, provider_url)
