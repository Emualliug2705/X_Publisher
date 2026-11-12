import hmac

from fastapi import Header, HTTPException, Query

from app.config import SERVER_API_KEY


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    key: str | None = Query(default=None, description="Alternative to the X-API-Key header"),
) -> None:
    if not SERVER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="SERVER_API_KEY is not configured on the server.",
        )
    provided = x_api_key or key
    if not provided or not hmac.compare_digest(provided, SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Missing or invalid API key.")
