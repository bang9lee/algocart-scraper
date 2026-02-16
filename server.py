import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="algocart-scraper", version="1.0.0")
SCRIPT_PATH = Path(__file__).parent / "scraper_uc.py"


class ScrapeRequest(BaseModel):
    url: str


def extract_first_url(text: str) -> str | None:
    direct = text.strip()
    if direct.startswith("http://") or direct.startswith("https://"):
        return direct

    match = re.search(r"https?://[^\s\"'<>]+", text)
    if not match:
        return None

    return match.group(0).rstrip(").,!?]\"")


def is_valid_coupang_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False

    if parsed.scheme != "https":
        return False

    host = (parsed.hostname or "").lower()
    return host == "coupang.com" or host.endswith(".coupang.com")


def parse_scraper_output(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]

    for line in reversed(lines):
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue

    start = stdout.find("{")
    end = stdout.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Invalid scraper output")

    payload = json.loads(stdout[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Scraper output is not an object")
    return payload


def check_internal_token(token: str | None) -> None:
    expected = os.getenv("SCRAPER_SERVICE_TOKEN", "").strip()
    if not expected:
        return
    if token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scrape")
def scrape(req: ScrapeRequest, x_internal_token: str | None = Header(default=None)) -> dict[str, Any]:
    check_internal_token(x_internal_token)

    extracted = extract_first_url(req.url)
    if not extracted or not is_valid_coupang_url(extracted):
        raise HTTPException(status_code=400, detail="Valid Coupang URL required")

    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), extracted],
            capture_output=True,
            text=True,
            timeout=50,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Scraper timeout")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scraper launch failed: {exc}")

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    if result.returncode != 0 and not stdout.strip():
        raise HTTPException(status_code=500, detail=f"Scraper failed: {stderr[:300]}")

    try:
        payload = parse_scraper_output(stdout)
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid scraper output")

    if isinstance(payload.get("error"), str) and payload["error"]:
        raise HTTPException(status_code=422, detail=payload["error"])

    title = payload.get("title") if isinstance(payload.get("title"), str) else ""
    image = payload.get("image") if isinstance(payload.get("image"), str) else ""

    if title.strip().lower() == "access denied":
        raise HTTPException(status_code=422, detail="Access Denied (blocked by Coupang)")

    raw_price = payload.get("price")
    if isinstance(raw_price, (int, float)):
        price = int(raw_price)
    elif isinstance(raw_price, str):
        nums = re.sub(r"[^\d]", "", raw_price)
        price = int(nums) if nums else 0
    else:
        price = 0

    if price <= 0:
        raise HTTPException(status_code=422, detail="Failed to extract valid price")

    return {
        "title": title,
        "price": price,
        "image": image,
        "source": "render-scraper",
    }
