# algocart-scraper

Render web service for Coupang scraping.

## Endpoints

- `GET /health`
- `POST /scrape`

Request body:

```json
{
  "url": "https://www.coupang.com/vp/products/..."
}
```

Optional security header:

- `X-Internal-Token: <SCRAPER_SERVICE_TOKEN>`

## Render Deploy

1. Create a **Web Service** in Render from this repository.
2. Runtime: Python.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
5. Add env var `SCRAPER_SERVICE_TOKEN`.
6. Add env var `SCRAPER_HEADLESS=1`.
7. Add env var `CHROME_BIN=/usr/bin/chromium` (if using native runtime).
8. In Render Build Command, install Chromium if needed:

```bash
apt-get update && apt-get install -y chromium chromium-driver && pip install -r requirements.txt
```

## Vercel App Integration

Set in Vercel env:

- `SCRAPER_SERVICE_URL=https://<your-render-service>.onrender.com`
- `SCRAPER_SERVICE_TOKEN=<same-token-as-render>`
