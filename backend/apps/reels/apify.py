"""Apify client for the Instagram reel scraper.

The actor is pay-per-event: we are billed per reel *returned*. Two consequences
shape this module:

  * Every run carries `maxTotalChargeUsd`. The actor terminates gracefully at
    the cap and we are never charged past it, which makes a runaway run
    structurally impossible rather than merely unlikely.
  * We run async and poll rather than using run-sync-get-dataset-items, because
    the sync endpoint returns items only — and we need the run's *actual*
    reported usage to keep the ledger honest (see costs.reconcile).
"""

import logging
import time
from datetime import datetime, timezone as dt_timezone

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

API = "https://api.apify.com/v2"
# Terminal run statuses — anything else means "still going".
DONE = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class ApifyError(RuntimeError):
    pass


def _actor_path(actor: str) -> str:
    """Apify addresses actors as `owner~name` in URLs, not `owner/name`."""
    return actor.replace("/", "~")


def is_configured() -> bool:
    return bool(settings.APIFY_TOKEN)


def run_reel_scraper(
    usernames: list[str],
    results_limit: int,
    max_total_charge_usd: float,
    timeout_s: int = 600,
) -> tuple[list[dict], str, float]:
    """Scrape the newest `results_limit` reels for each username.

    Returns (items, apify_run_id, cost_usd). Raises ApifyError on anything that
    isn't a clean finish — callers record that on the ReelFetchRun rather than
    letting it escape.
    """
    if not is_configured():
        raise ApifyError("APIFY_TOKEN is not set")
    if not usernames:
        return [], "", 0.0

    actor = _actor_path(settings.APIFY_REEL_ACTOR)
    payload = {"username": usernames, "resultsLimit": results_limit}
    try:
        res = requests.post(
            f"{API}/acts/{actor}/runs",
            params={
                "token": settings.APIFY_TOKEN,
                # The hard per-run ceiling. Apify stops charging past it.
                "maxTotalChargeUsd": round(max_total_charge_usd, 4),
            },
            json=payload,
            timeout=30,
        )
        res.raise_for_status()
        run = res.json()["data"]
    except Exception as exc:  # noqa: BLE001 — surfaced on the ReelFetchRun row
        raise ApifyError(f"could not start actor: {exc}") from exc

    run_id = run["id"]
    run = _wait_for_run(run_id, timeout_s)
    status = run.get("status")
    cost = float(run.get("usageTotalUsd") or 0)

    if status != "SUCCEEDED":
        raise ApifyError(f"run {run_id} finished as {status}")

    items = _dataset_items(run.get("defaultDatasetId", ""))
    return items, run_id, cost


def _wait_for_run(run_id: str, timeout_s: int) -> dict:
    """Poll the run until it reaches a terminal status. Backs off from 2s to
    15s so a slow run doesn't mean hundreds of requests."""
    deadline = time.monotonic() + timeout_s
    delay = 2.0
    while True:
        try:
            res = requests.get(
                f"{API}/actor-runs/{run_id}",
                params={"token": settings.APIFY_TOKEN},
                timeout=30,
            )
            res.raise_for_status()
            run = res.json()["data"]
        except Exception as exc:  # noqa: BLE001
            raise ApifyError(f"could not read run {run_id}: {exc}") from exc

        if run.get("status") in DONE:
            return run
        if time.monotonic() > deadline:
            raise ApifyError(f"run {run_id} still {run.get('status')} after {timeout_s}s")
        time.sleep(delay)
        delay = min(delay * 1.5, 15.0)


def _dataset_items(dataset_id: str) -> list[dict]:
    if not dataset_id:
        return []
    try:
        res = requests.get(
            f"{API}/datasets/{dataset_id}/items",
            params={"token": settings.APIFY_TOKEN, "clean": "true", "format": "json"},
            timeout=120,
        )
        res.raise_for_status()
        return res.json() or []
    except Exception as exc:  # noqa: BLE001
        raise ApifyError(f"could not read dataset {dataset_id}: {exc}") from exc


def account_usage_usd() -> float | None:
    """This month's spend as Apify itself reports it, for the Costs page's
    reconciliation panel. None when unavailable — a missing number is shown as
    "unknown", never as zero."""
    if not is_configured():
        return None
    try:
        res = requests.get(
            f"{API}/users/me/usage/monthly",
            params={"token": settings.APIFY_TOKEN},
            timeout=20,
        )
        res.raise_for_status()
        data = res.json().get("data") or {}
    except Exception:  # noqa: BLE001 — reconciliation is best-effort
        logger.warning("Apify usage lookup failed", exc_info=True)
        return None
    total = data.get("totalUsageCreditsUsdAfterVolumeDiscount")
    if total is None:
        total = data.get("totalUsageCreditsUsd")
    return float(total) if total is not None else None


# --- Normalising the actor's output ------------------------------------------


def parse_timestamp(raw) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=dt_timezone.utc)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def normalise_item(item: dict) -> dict | None:
    """Map one actor result onto our Reel fields. Returns None for anything
    without a shortcode — we can't dedupe it, so we won't store it."""
    key = item.get("shortCode") or item.get("shortcode") or item.get("code")
    if not key:
        return None
    return {
        "key": str(key),
        "url": item.get("url") or f"https://www.instagram.com/reel/{key}/",
        "caption": item.get("caption") or "",
        "hashtags": item.get("hashtags") or [],
        "video_url": item.get("videoUrl") or "",
        "poster_url": item.get("displayUrl") or "",
        "duration_seconds": item.get("videoDuration"),
        "view_count": int(item.get("videoViewCount") or item.get("videoPlayCount") or 0),
        "like_count": int(item.get("likesCount") or 0),
        "comment_count": int(item.get("commentsCount") or 0),
        "posted_at": parse_timestamp(item.get("timestamp")),
        "owner_username": (item.get("ownerUsername") or "").lstrip("@").lower(),
    }
