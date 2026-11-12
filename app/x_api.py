from typing import Any

import requests
from requests_oauthlib import OAuth1Session

from app.config import (
    X_ACCESS_TOKEN,
    X_ACCESS_TOKEN_SECRET,
    X_API_KEY,
    X_API_SECRET,
    X_OAUTH2_ACCESS_TOKEN,
    has_oauth1,
    has_oauth2,
)

TWEETS_URL = "https://api.x.com/2/tweets"


class XAPIError(Exception):
    def __init__(self, status_code: int, message: str, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.body = body


def _extract_error_message(status_code: int, body: Any) -> str:
    if isinstance(body, dict):
        if body.get("detail"):
            return str(body["detail"])
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            parts = []
            for err in errors:
                if isinstance(err, dict):
                    parts.append(str(err.get("message") or err.get("detail") or err))
                else:
                    parts.append(str(err))
            if parts:
                return "; ".join(parts)
        if body.get("title"):
            return str(body["title"])
    if isinstance(body, str) and body.strip():
        return body.strip()
    if status_code == 429:
        return "X API rate limit exceeded (429)."
    if status_code == 403:
        return "X API forbidden (403). The post may restrict replies, or the app lacks write access."
    if status_code == 401:
        return "X API unauthorized (401). Check your developer app credentials and permissions."
    return f"X API request failed with status {status_code}."


def _session() -> requests.Session:
    if has_oauth1():
        return OAuth1Session(
            client_key=X_API_KEY,
            client_secret=X_API_SECRET,
            resource_owner_key=X_ACCESS_TOKEN,
            resource_owner_secret=X_ACCESS_TOKEN_SECRET,
        )
    if has_oauth2():
        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {X_OAUTH2_ACCESS_TOKEN}"
        return session
    raise XAPIError(
        503,
        "X credentials are not configured. Set X_API_KEY, X_API_SECRET, "
        "X_ACCESS_TOKEN and X_ACCESS_TOKEN_SECRET (OAuth 1.0a), or X_OAUTH2_ACCESS_TOKEN.",
    )


def create_tweet(
    text: str,
    in_reply_to_tweet_id: str | None = None,
    quote_tweet_id: str | None = None,
) -> dict:
    payload: dict[str, Any] = {"text": text}
    if in_reply_to_tweet_id:
        payload["reply"] = {"in_reply_to_tweet_id": str(in_reply_to_tweet_id)}
    if quote_tweet_id:
        payload["quote_tweet_id"] = str(quote_tweet_id)

    try:
        response = _session().post(TWEETS_URL, json=payload, timeout=30)
    except requests.RequestException as exc:
        raise XAPIError(502, f"Could not reach the X API: {exc}") from exc

    body: Any
    try:
        body = response.json()
    except ValueError:
        body = response.text

    if not response.ok:
        raise XAPIError(response.status_code, _extract_error_message(response.status_code, body), body)

    data = body.get("data") if isinstance(body, dict) else None
    if not data or not data.get("id"):
        raise XAPIError(502, "X API returned an unexpected response (missing post id).", body)
    return data
