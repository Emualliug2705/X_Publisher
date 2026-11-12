#!/usr/bin/env python3
"""Smoke tests for intent-link parsing and /publish. Does not call the X API."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote, urlencode

ROOT = Path(__file__).resolve().parent
API_KEY = "smoke-test-key"
SMOKE_DIR = Path(tempfile.mkdtemp(prefix="x-autoreply-smoke-"))

EXAMPLE_INTENT = (
    "https://x.com/intent/post?text=This%20one%20is%20scary.%20Under%2010%20neurons%20"
    "and%20the%20evals%20stay%20green.%20A%20passing%20benchmark%20says%20nothing%20"
    "about%20what%27s%20in%20the%20weights.%20Diffing%20against%20base%20should%20be%20"
    "standard%20%F0%9F%94%90&in_reply_to=2120777764273877444"
)
EXPECTED_TEXT = (
    "This one is scary. Under 10 neurons and the evals stay green. "
    "A passing benchmark says nothing about what's in the weights. "
    "Diffing against base should be standard 🔐"
)
EXPECTED_REPLY_TO = "2120777764273877444"

os.environ.update(
    {
        "SERVER_API_KEY": API_KEY,
        "X_API_KEY": "dummy",
        "X_API_SECRET": "dummy",
        "X_ACCESS_TOKEN": "dummy",
        "X_ACCESS_TOKEN_SECRET": "dummy",
        "MAX_POSTS_PER_DAY": "10",
        "TIMEZONE": "Europe/Paris",
        "DATA_DIR": str(SMOKE_DIR),
        "PYTHONPATH": str(ROOT),
    }
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import after env is set so config.py picks up the smoke DATA_DIR and key.
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.parser import parse_intent_url  # noqa: E402


def _check(ok: bool, label: str, detail: str = "") -> bool:
    suffix = f" {detail}" if detail else ""
    print(("PASS  " if ok else "FAIL  ") + label + suffix)
    return ok


def main() -> int:
    failed = False

    intent = parse_intent_url(EXAMPLE_INTENT)
    if not _check(
        intent.text == EXPECTED_TEXT and intent.in_reply_to == EXPECTED_REPLY_TO,
        "parse example intent link",
        f"text={intent.text!r} in_reply_to={intent.in_reply_to!r}",
    ):
        failed = True
        if intent.text != EXPECTED_TEXT:
            print(f"      expected text: {EXPECTED_TEXT!r}")
        if intent.in_reply_to != EXPECTED_REPLY_TO:
            print(f"      expected in_reply_to: {EXPECTED_REPLY_TO!r}")

    # Other hosts must be rejected.
    try:
        parse_intent_url("https://evil.example/intent/post?text=hi&in_reply_to=1")
        failed = not _check(False, "reject non-x.com intent host (should have raised)")
    except ValueError:
        if not _check(True, "reject non-x.com intent host"):
            failed = True

    client = TestClient(app)

    health = client.get("/health")
    if not _check(health.status_code == 200 and health.json() == {"status": "ok"}, "GET /health -> 200"):
        failed = True

    no_key = client.post("/publish", json={"intent_url": EXAMPLE_INTENT})
    if not _check(no_key.status_code == 401, f"POST /publish without key -> 401 ({no_key.json()})"):
        failed = True

    no_key_get = client.get("/publish", params={"intent_url": EXAMPLE_INTENT})
    if not _check(no_key_get.status_code == 401, f"GET /publish without key -> 401 ({no_key_get.json()})"):
        failed = True

    no_key_intent = client.get("/intent/post", params={"text": "hi", "in_reply_to": "1"})
    if not _check(
        no_key_intent.status_code == 401,
        f"GET /intent/post without key -> 401 ({no_key_intent.json()})",
    ):
        failed = True

    bad_host = client.post(
        "/publish",
        json={"intent_url": "https://example.com/intent/post?text=hi"},
        headers={"X-API-Key": API_KEY},
    )
    if not _check(bad_host.status_code == 400, f"POST /publish other host -> 400 ({bad_host.json()})"):
        failed = True

    with patch("app.main.create_tweet") as mock_create:
        mock_create.return_value = {"id": "999888777"}
        posted = client.post(
            "/publish",
            json={"intent_url": EXAMPLE_INTENT},
            headers={"X-API-Key": API_KEY},
        )
        called = mock_create.call_count == 1
        args, kwargs = (mock_create.call_args or ((), {}))
        text_arg = args[0] if args else kwargs.get("text")
        reply_arg = kwargs.get("in_reply_to_tweet_id")
        if args and len(args) > 1 and reply_arg is None:
            reply_arg = args[1]
        ok = (
            posted.status_code == 200
            and posted.json() == {"id": "999888777", "url": "https://x.com/i/status/999888777"}
            and called
            and text_arg == EXPECTED_TEXT
            and reply_arg == EXPECTED_REPLY_TO
        )
        if not _check(
            ok,
            "POST /publish calls X client (mocked)",
            f"status={posted.status_code} body={posted.json()} "
            f"calls={mock_create.call_count} text={text_arg!r} in_reply_to={reply_arg!r}",
        ):
            failed = True

        # Same text + in_reply_to must be refused without a second X call.
        mock_create.reset_mock()
        dup = client.post(
            "/publish",
            json={"intent_url": EXAMPLE_INTENT},
            headers={"X-API-Key": API_KEY},
        )
        if not _check(
            dup.status_code == 409 and mock_create.call_count == 0,
            f"POST /publish duplicate -> 409 and no second X call ({dup.json()})",
        ):
            failed = True

    with patch("app.main.create_tweet") as mock_create:
        mock_create.return_value = {"id": "111"}
        # Different text so it is not a duplicate of the previous publish.
        get_url = "/publish?" + urlencode(
            {"intent_url": EXAMPLE_INTENT.replace("This", "That"), "key": API_KEY}
        )
        got = client.get(get_url)
        args, kwargs = (mock_create.call_args or ((), {}))
        text_arg = args[0] if args else kwargs.get("text")
        reply_arg = kwargs.get("in_reply_to_tweet_id")
        if args and len(args) > 1 and reply_arg is None:
            reply_arg = args[1]
        if not _check(
            got.status_code == 200
            and got.json() == {"id": "111", "url": "https://x.com/i/status/111"}
            and mock_create.call_count == 1
            and text_arg == EXPECTED_TEXT.replace("This", "That", 1)
            and reply_arg == EXPECTED_REPLY_TO,
            "GET /publish?intent_url=...&key=... calls X client (mocked)",
            f"status={got.status_code} body={got.json()} "
            f"calls={mock_create.call_count} text={text_arg!r} in_reply_to={reply_arg!r}",
        ):
            failed = True

    with patch("app.main.create_tweet") as mock_create:
        mock_create.return_value = {"id": "222"}
        # Host-swap path: same query shape as the X intent link, plus key.
        # Slightly different text so this is not a duplicate of the earlier publish.
        swapped_intent = EXAMPLE_INTENT.replace("scary", "wild")
        expected_swap_text = EXPECTED_TEXT.replace("scary", "wild")
        path = swapped_intent.split("x.com", 1)[1] + "&key=" + quote(API_KEY)
        swapped = client.get(path)
        args, kwargs = (mock_create.call_args or ((), {}))
        text_arg = args[0] if args else kwargs.get("text")
        reply_arg = kwargs.get("in_reply_to_tweet_id")
        if args and len(args) > 1 and reply_arg is None:
            reply_arg = args[1]
        if not _check(
            swapped.status_code == 200
            and swapped.json() == {"id": "222", "url": "https://x.com/i/status/222"}
            and mock_create.call_count == 1
            and text_arg == expected_swap_text
            and reply_arg == EXPECTED_REPLY_TO,
            "GET /intent/post?...&key=... host-swap calls X client (mocked)",
            f"status={swapped.status_code} body={swapped.json()} "
            f"calls={mock_create.call_count} text={text_arg!r} in_reply_to={reply_arg!r}",
        ):
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
