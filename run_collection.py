#!/usr/bin/env python3
"""
run_collection.py — Postman v2.1 collection runner.

Usage:
    python run_collection.py [collection.json] [--base-url http://localhost:8081]

Reads a Postman collection JSON, resolves {{variables}}, and executes every
request in order, printing a pass/fail summary.

Supports:
  - GET / POST / PUT / DELETE / PATCH
  - formdata bodies (file and text fields)
  - raw bodies (text/plain, application/json, …)
  - collection-level and environment-level variable substitution
"""

import argparse
import json
import mimetypes
import pathlib
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_COLLECTION = "ShelfLabelConverter-py.postman_collection.json"
DEFAULT_TIMEOUT = 30


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Result:
    name: str
    status_code: Optional[int] = None
    passed: bool = False
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    response_snippet: str = ""


# ── Variable resolution ───────────────────────────────────────────────────────

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def resolve(text: str, variables: dict[str, str]) -> str:
    return _VAR_RE.sub(lambda m: variables.get(m.group(1), m.group(0)), text)


def build_url(url_obj, variables: dict[str, str]) -> str:
    if isinstance(url_obj, str):
        return resolve(url_obj, variables)
    raw = url_obj.get("raw", "")
    return resolve(raw, variables)


# ── Body builders ─────────────────────────────────────────────────────────────

def build_formdata(
    formdata: list[dict],
    variables: dict[str, str],
    base_dir: pathlib.Path,
) -> tuple[dict, list]:
    """Returns (data_fields, files_list) for httpx multipart."""
    data: dict[str, str] = {}
    files: list[tuple] = []

    for item in formdata:
        if item.get("disabled"):
            continue
        key = item["key"]
        if item.get("type") == "file":
            src = resolve(item.get("src", ""), variables)
            file_path = base_dir / src
            if not file_path.exists():
                raise FileNotFoundError(f"Upload file not found: {file_path}")
            mime, _ = mimetypes.guess_type(str(file_path))
            mime = mime or "application/octet-stream"
            files.append((key, (file_path.name, file_path.read_bytes(), mime)))
        else:
            data[key] = resolve(item.get("value", ""), variables)

    return data, files


def build_raw_body(body_obj: dict, variables: dict[str, str]) -> tuple[bytes, str]:
    """Returns (raw_bytes, content_type)."""
    raw_text = resolve(body_obj.get("raw", ""), variables)
    lang = body_obj.get("options", {}).get("raw", {}).get("language", "text")
    content_type_map = {
        "json": "application/json",
        "text": "text/plain",
        "html": "text/html",
        "xml": "application/xml",
    }
    content_type = content_type_map.get(lang, "text/plain")
    return raw_text.encode(), content_type


# ── Request executor ──────────────────────────────────────────────────────────

def execute_request(
    item: dict,
    variables: dict[str, str],
    base_dir: pathlib.Path,
    client: httpx.Client,
) -> Result:
    name = item.get("name", "(unnamed)")
    req = item.get("request", {})
    method = req.get("method", "GET").upper()
    url = build_url(req.get("url", ""), variables)

    # Collect explicit headers
    headers: dict[str, str] = {}
    for h in req.get("header", []):
        if not h.get("disabled"):
            headers[resolve(h["key"], variables)] = resolve(h["value"], variables)

    body_obj = req.get("body", {})
    mode = body_obj.get("mode") if body_obj else None

    kwargs: dict = {"headers": headers}

    try:
        if mode == "formdata":
            data, files = build_formdata(body_obj.get("formdata", []), variables, base_dir)
            kwargs["data"] = data
            if files:
                kwargs["files"] = files
        elif mode == "raw":
            raw_bytes, ct = build_raw_body(body_obj, variables)
            kwargs["content"] = raw_bytes
            headers.setdefault("Content-Type", ct)
        elif mode == "urlencoded":
            kwargs["data"] = {
                resolve(f["key"], variables): resolve(f["value"], variables)
                for f in body_obj.get("urlencoded", [])
                if not f.get("disabled")
            }

        t0 = time.perf_counter()
        response = client.request(method, url, **kwargs)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Build a short snippet of the response for display
        ct = response.headers.get("content-type", "")
        if "image" in ct or "octet" in ct:
            snippet = f"<binary {len(response.content)} bytes>"
        else:
            text = response.text[:200]
            snippet = text + ("…" if len(response.text) > 200 else "")

        return Result(
            name=name,
            status_code=response.status_code,
            passed=response.status_code < 400,
            elapsed_ms=elapsed_ms,
            response_snippet=snippet,
        )

    except Exception as exc:
        return Result(name=name, passed=False, error=str(exc))


# ── Collection walker ─────────────────────────────────────────────────────────

def iter_items(items: list[dict]):
    """Yield leaf request items, recursing into folders."""
    for item in items:
        if "item" in item:
            yield from iter_items(item["item"])
        elif "request" in item:
            yield item


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Postman v2.1 collection")
    parser.add_argument("collection", nargs="?", default=DEFAULT_COLLECTION)
    parser.add_argument("--base-url", default=None, help="Override the baseUrl variable")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--var", action="append", default=[], metavar="KEY=VALUE",
                        help="Override a collection variable (repeatable)")
    args = parser.parse_args()

    collection_path = pathlib.Path(args.collection)
    if not collection_path.exists():
        print(f"ERROR: collection file not found: {collection_path}")
        return 1

    base_dir = collection_path.parent
    collection = json.loads(collection_path.read_text())

    # Build variable table from collection-level variables
    variables: dict[str, str] = {
        v["key"]: v.get("value", "")
        for v in collection.get("variable", [])
    }

    # Apply --base-url override
    if args.base_url:
        variables["baseUrl"] = args.base_url

    # Apply --var overrides
    for kv in args.var:
        k, _, v = kv.partition("=")
        variables[k.strip()] = v.strip()

    info = collection.get("info", {})
    print(f"\n{'='*60}")
    print(f"Collection : {info.get('name', collection_path.name)}")
    print(f"Base URL   : {variables.get('baseUrl', '(not set)')}")
    print(f"{'='*60}\n")

    results: list[Result] = []
    items = list(iter_items(collection.get("item", [])))

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        for i, item in enumerate(items, 1):
            req_method = item.get("request", {}).get("method", "GET")
            req_url_raw = item.get("request", {}).get("url", {})
            req_url = build_url(req_url_raw, variables)
            print(f"[{i}/{len(items)}] {item.get('name', '?')}")
            print(f"         {req_method} {req_url}")

            result = execute_request(item, variables, base_dir, client)
            results.append(result)

            status_str = str(result.status_code) if result.status_code else "ERR"
            icon = "✓" if result.passed else "✗"
            timing = f"{result.elapsed_ms:.0f}ms" if result.elapsed_ms else ""

            if result.error:
                print(f"         {icon} ERROR: {result.error}\n")
            else:
                print(f"         {icon} {status_str}  {timing}")
                print(f"         {result.response_snippet}\n")

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    print(f"{'='*60}")
    print(f"Results: {passed}/{len(results)} passed", end="")
    if failed:
        print(f"  ({failed} failed)")
        for r in results:
            if not r.passed:
                err = r.error or f"HTTP {r.status_code}"
                print(f"  ✗ {r.name}: {err}")
    else:
        print(" — all passed!")
    print(f"{'='*60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
