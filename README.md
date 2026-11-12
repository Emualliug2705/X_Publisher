# X_Publisher

A small FastAPI server that publishes a reply (or a standalone post) on your X account. The main path is an **X intent link**: you send the server a link like `https://x.com/intent/post?text=...&in_reply_to=...`, and it publishes that text as a reply (or as a standalone post if there is no `in_reply_to`).

It calls the X API v2 with **your** developer app credentials. It does not scrape X, and it does not use anyone else's tokens. Keep `SERVER_API_KEY` and your X tokens private: anyone who can reach this server and knows the key can post as you.

X's automation rules restrict unsolicited automated replies. Accounts that reply at scale to people who have not interacted with you can be limited or suspended. Use this carefully, and prefer posting only after you have reviewed the text.

## Endpoints

| Method | Path | Auth | Input | Success |
| --- | --- | --- | --- | --- |
| `GET` | `/health` | none | — | `{"status":"ok"}` |
| `POST` | `/publish` | `X-API-Key` header or `?key=` | JSON `{"intent_url":"https://x.com/intent/post?..."}` | `{"id":"<new id>","url":"https://x.com/i/status/<id>"}` |
| `GET` | `/publish` | same | `?intent_url=<urlencoded intent link>&key=...` | same |
| `GET` | `/intent/post` (also `/intent/tweet`) | same | The same query string as the X intent link, plus `key=...` | same |
| `POST` | `/reply` | same | JSON `{"post_url":"...","text":"..."}` | same |
| `POST` | `/post` | same | JSON `{"text":"..."}` | same |

Intent links must be `https://x.com` or `https://twitter.com` `/intent/post` or `/intent/tweet` URLs (other hosts are rejected). The parser reads:

- `text` — URL-decoded, emoji-safe
- `in_reply_to` — if present, the post is published as a reply to that status id
- `url` — appended to the text
- `quote` or `attachment_url` — if it looks like a status URL or bare id, sent as a quote tweet; otherwise appended to the text

`post_url` on `POST /reply` can be an `x.com` or `twitter.com` status URL (query strings and `/photo/N` suffixes are fine) or a bare numeric status id.

Safety checks (all return a JSON `detail` message):

- Missing or wrong API key (`X-API-Key` header or `key` query parameter) → `401`
- Bad URL, empty text, or text over the 280-character **weighted** limit (emoji count as 2, URLs as 23) → `400`
- Same `text` + `in_reply_to` already published → `409`
- Daily cap reached (`MAX_POSTS_PER_DAY`, default 10) → `429`
- X API errors are passed through with the original status when possible (for example `403` reply restrictions, `429` rate limit) and X's error message in `detail`.

Every successful post is appended to `data/published.jsonl`.

## 1. Create an X developer app (Read + Write)

1. Go to [the X developer portal](https://developer.x.com/en/portal/dashboard) and sign in as the account that should publish (`@gpelluet27`).
2. Create a Project and an App if you do not already have one.
3. In the app settings, set **App permissions** to **Read and Write**. Save.
4. Open **Keys and tokens**.
5. Generate (or regenerate) the **API Key** and **API Key Secret** (also called Consumer Key / Consumer Secret).
6. Generate an **Access Token** and **Access Token Secret**. These must be created *after* you set Read and Write, otherwise they stay read-only. Regenerate them if you changed permissions later.
7. Copy the four values into your `.env` file. Do not commit that file.

### Optional: OAuth 2.0 user token

If you prefer OAuth 2.0, you can leave the four OAuth 1.0a variables unset and set `X_OAUTH2_ACCESS_TOKEN` to a **user** access token (not an app-only bearer token) that has the `tweet.write` and `tweet.read` scopes. The server will send it as `Authorization: Bearer …`. OAuth 1.0a is the default and is usually simpler for a personal app.

## 2. Configure the server

```bash
cd x-autoreply-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in real values. Never commit .env.
```

Environment variables:

| Variable | Required | Description |
| --- | --- | --- |
| `SERVER_API_KEY` | yes | Shared secret sent as the `X-API-Key` header or `key` query parameter |
| `X_API_KEY` | yes* | OAuth 1.0a API / consumer key |
| `X_API_SECRET` | yes* | OAuth 1.0a API / consumer secret |
| `X_ACCESS_TOKEN` | yes* | OAuth 1.0a user access token |
| `X_ACCESS_TOKEN_SECRET` | yes* | OAuth 1.0a user access token secret |
| `X_OAUTH2_ACCESS_TOKEN` | no | OAuth 2.0 user access token (used only if the four `X_*` values above are unset) |
| `MAX_POSTS_PER_DAY` | no | Daily publish cap, default `10` |
| `TIMEZONE` | no | Timezone for the daily cap, default `Europe/Paris` |
| `DATA_DIR` | no | Directory for `published.jsonl` and `usage.json`, default `./data` |

\* Required unless you use `X_OAUTH2_ACCESS_TOKEN` instead.

## 3. Run locally

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The process is only reachable on the machine it is running on (or your LAN) until you expose it.

### Example: publish from an intent link

Take an X compose/intent link such as:

```
https://x.com/intent/post?text=This%20one%20is%20scary.%20Under%2010%20neurons%20and%20the%20evals%20stay%20green.%20A%20passing%20benchmark%20says%20nothing%20about%20what%27s%20in%20the%20weights.%20Diffing%20against%20base%20should%20be%20standard%20%F0%9F%94%90&in_reply_to=2120777764273877444
```

That decodes to a reply to `2120777764273877444` with the text:

> This one is scary. Under 10 neurons and the evals stay green. A passing benchmark says nothing about what's in the weights. Diffing against base should be standard 🔐

**POST the intent URL**

```bash
INTENT='https://x.com/intent/post?text=This%20one%20is%20scary.%20Under%2010%20neurons%20and%20the%20evals%20stay%20green.%20A%20passing%20benchmark%20says%20nothing%20about%20what%27s%20in%20the%20weights.%20Diffing%20against%20base%20should%20be%20standard%20%F0%9F%94%90&in_reply_to=2120777764273877444'

curl -sS -X POST http://127.0.0.1:8000/publish \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SERVER_API_KEY" \
  -d "{\"intent_url\":\"$INTENT\"}"
```

**GET with the intent URL as a query parameter** (also accepts `X-API-Key`):

```bash
curl -sS -G http://127.0.0.1:8000/publish \
  --data-urlencode "intent_url=$INTENT" \
  --data-urlencode "key=$SERVER_API_KEY"
```

**Host-swap trick.** Replace `https://x.com` with your server base URL and append `&key=...`. The path and query stay the same, so the original intent link works as-is:

```
http://127.0.0.1:8000/intent/post?text=This%20one%20is%20scary.%20Under%2010%20neurons%20and%20the%20evals%20stay%20green.%20A%20passing%20benchmark%20says%20nothing%20about%20what%27s%20in%20the%20weights.%20Diffing%20against%20base%20should%20be%20standard%20%F0%9F%94%90&in_reply_to=2120777764273877444&key=$SERVER_API_KEY
```

After you deploy, that becomes `https://YOUR_SERVER/intent/post?text=...&in_reply_to=...&key=...`. Opening that link publishes immediately. Putting the key in the query string can leak via logs and Referer headers; prefer a header when you can, and use a long random `SERVER_API_KEY`.

A successful response looks like:

```json
{"id":"1980000000000000000","url":"https://x.com/i/status/1980000000000000000"}
```

The older `POST /reply` and `POST /post` endpoints still work if you already have the text and target id separately.

## 4. Make it reachable

Pick one:

**Quick test (temporary public URL)**

- [ngrok](https://ngrok.com/): `ngrok http 8000`
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/): `cloudflared tunnel --url http://127.0.0.1:8000`

Use the HTTPS URL they print as the base, and keep `SERVER_API_KEY` in every request.

**Deploy (always-on)**

- [Render](https://render.com/), [Railway](https://railway.app/), or [Fly.io](https://fly.io/) all work with the included `Dockerfile`.
- Set the environment variables from `.env.example` in the host's secret/env settings (do not bake them into the image).
- Give the service a persistent volume if you want the daily cap, dedupe log, and JSONL log to survive restarts; otherwise they reset when the container is recreated.
- Example: `docker build -t x-autoreply-server . && docker run --env-file .env -p 8000:8000 x-autoreply-server`

Once the server has a public HTTPS URL, use that as the host in the examples above (or swap it in place of `https://x.com` on an intent link).

## Smoke test (no real X credentials, no real API calls)

```bash
python3 smoke_test.py
```

This checks that the example intent link decodes correctly (including the 🔐 emoji), that requests without a key are rejected, and that `/publish` calls the X client with the parsed text and `in_reply_to`. The X client is mocked; it never calls `api.x.com`.
