import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

# x.com / twitter.com status URLs, including /i/status, /i/web/status, /photo/N, query strings.
_STATUS_URL_RE = re.compile(
    r"(?:https?://)?(?:(?:www|mobile|www\.mobile)\.)?(?:twitter|x)\.com/"
    r"(?:[^/\s]+/status(?:es)?|i/web/status|i/status)/(\d+)",
    re.IGNORECASE,
)
_BARE_ID_RE = re.compile(r"^\d+$")

_ALLOWED_HOSTS = frozenset(
    {
        "x.com",
        "www.x.com",
        "mobile.x.com",
        "www.mobile.x.com",
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
        "www.mobile.twitter.com",
    }
)
_INTENT_PATHS = frozenset({"/intent/post", "/intent/tweet"})

@dataclass(frozen=True)
class Intent:
    text: str
    in_reply_to: str | None = None
    quote_tweet_id: str | None = None


def parse_status_id(value: str) -> str:
    """Extract a tweet/status id from an x.com or twitter.com URL, or a bare numeric id."""
    if value is None or not str(value).strip():
        raise ValueError("post_url is required")
    value = str(value).strip()
    if _BARE_ID_RE.fullmatch(value):
        return value
    match = _STATUS_URL_RE.search(value)
    if match:
        return match.group(1)
    raise ValueError(
        "Could not parse a status id. Pass an x.com or twitter.com status URL, "
        "or a bare numeric id."
    )


def _first(params: Mapping[str, Any], name: str) -> str:
    if hasattr(params, "getlist"):
        values = params.getlist(name)
        if values:
            return str(values[0])
        return ""
    value = params.get(name)
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return "" if value is None else str(value)


def intent_from_params(params: Mapping[str, Any]) -> Intent:
    """Build an Intent from query parameters (text, in_reply_to, url, quote, attachment_url)."""
    text = _first(params, "text")
    extra_url = _first(params, "url").strip()
    if extra_url:
        text = f"{text} {extra_url}".strip() if text.strip() else extra_url

    in_reply_to = _first(params, "in_reply_to").strip() or None
    if in_reply_to and not _BARE_ID_RE.fullmatch(in_reply_to):
        raise ValueError("in_reply_to must be a numeric status id.")

    quote_raw = (_first(params, "quote") or _first(params, "attachment_url")).strip() or None
    quote_tweet_id = None
    if quote_raw:
        try:
            quote_tweet_id = parse_status_id(quote_raw)
        except ValueError:
            if quote_raw not in text:
                text = f"{text} {quote_raw}".strip()

    text = text.strip()
    if not text:
        raise ValueError("intent link has no text (and no url to append).")
    return Intent(text=text, in_reply_to=in_reply_to, quote_tweet_id=quote_tweet_id)


def parse_intent_url(value: str) -> Intent:
    """Parse an x.com or twitter.com /intent/post or /intent/tweet URL.

    Other hosts are rejected. `text` is URL-decoded (emoji-safe), `in_reply_to`
    becomes a reply target, `url` is appended to the text, and `quote` /
    `attachment_url` are treated as a quote-tweet id when they look like a
    status URL or bare id.
    """
    if value is None or not str(value).strip():
        raise ValueError("intent_url is required")
    raw = str(value).strip()
    parsed = urlparse(raw)
    if not parsed.scheme:
        parsed = urlparse("https://" + raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http(s) x.com and twitter.com intent links are accepted.")

    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise ValueError("Only x.com and twitter.com intent links are accepted.")

    path = (parsed.path or "").rstrip("/") or "/"
    if path.lower() not in _INTENT_PATHS:
        raise ValueError("URL must be an /intent/post or /intent/tweet link.")

    return intent_from_params(parse_qs(parsed.query, keep_blank_values=False))
