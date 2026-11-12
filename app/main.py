from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import require_api_key
from app.config import MAX_TEXT_LENGTH
from app.parser import Intent, intent_from_params, parse_intent_url, parse_status_id
from app.safety import (
    check_daily_cap,
    increment_daily_count,
    is_duplicate,
    log_publication,
    weighted_length,
)
from app.x_api import XAPIError, create_tweet

app = FastAPI(
    title="X Auto-Reply Server",
    description=(
        "Publish a standalone X post or a reply from an intent link, post URL, "
        "or raw text, using your own developer app credentials."
    ),
    version="1.1.0",
)


class ReplyRequest(BaseModel):
    post_url: str = Field(..., description="x.com/twitter.com status URL, or a bare numeric status id")
    text: str = Field(..., description="Reply text, max 280 weighted characters")


class PostRequest(BaseModel):
    text: str = Field(..., description="Post text, max 280 weighted characters")


class PublishRequest(BaseModel):
    intent_url: str = Field(..., description="x.com or twitter.com /intent/post or /intent/tweet URL")


def _validate_text(text: str) -> str:
    if text is None or not text.strip():
        raise HTTPException(status_code=400, detail="text is required and cannot be empty.")
    text = text.strip()
    length = weighted_length(text)
    if length > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=(
                f"text exceeds the {MAX_TEXT_LENGTH}-character weighted limit "
                f"({length} weighted characters; emoji count as 2, URLs as 23)."
            ),
        )
    return text


def _publish(text: str, in_reply_to: str | None, quote_tweet_id: str | None = None) -> dict:
    text = _validate_text(text)
    try:
        check_daily_cap()
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    if is_duplicate(text, in_reply_to):
        raise HTTPException(
            status_code=409,
            detail="Already published this exact text for this in_reply_to target.",
        )

    try:
        data = create_tweet(
            text,
            in_reply_to_tweet_id=in_reply_to,
            quote_tweet_id=quote_tweet_id,
        )
    except XAPIError as exc:
        status = exc.status_code if 400 <= exc.status_code < 600 else 502
        raise HTTPException(status_code=status, detail=exc.message) from exc

    post_id = str(data["id"])
    url = f"https://x.com/i/status/{post_id}"
    increment_daily_count()
    log_publication(
        {
            "type": "reply" if in_reply_to else "post",
            "in_reply_to": in_reply_to,
            "quote_tweet_id": quote_tweet_id,
            "text": text,
            "post_id": post_id,
            "url": url,
        }
    )
    return {"id": post_id, "url": url}


def _publish_intent(intent: Intent) -> dict:
    return _publish(intent.text, intent.in_reply_to, intent.quote_tweet_id)


def _parse_intent_url(intent_url: str) -> Intent:
    try:
        return parse_intent_url(intent_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/reply", dependencies=[Depends(require_api_key)])
def reply(body: ReplyRequest) -> dict:
    try:
        status_id = parse_status_id(body.post_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _publish(body.text, in_reply_to=status_id)


@app.post("/post", dependencies=[Depends(require_api_key)])
def post(body: PostRequest) -> dict:
    return _publish(body.text, in_reply_to=None)


@app.post("/publish", dependencies=[Depends(require_api_key)])
def publish_post(body: PublishRequest) -> dict:
    return _publish_intent(_parse_intent_url(body.intent_url))


@app.get("/publish", dependencies=[Depends(require_api_key)])
def publish_get(intent_url: str) -> dict:
    return _publish_intent(_parse_intent_url(intent_url))


@app.get("/intent/post", dependencies=[Depends(require_api_key)])
@app.get("/intent/tweet", dependencies=[Depends(require_api_key)])
def publish_intent_path(request: Request) -> dict:
    params = request.query_params
    try:
        intent = intent_from_params(params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _publish_intent(intent)
