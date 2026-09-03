"""
http_source.py — Module for fetching activity events from HTTP endpoints with timeout & unreachable handling.
"""
import json
import logging
from typing import List, Dict, Any, Optional

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

logger = logging.getLogger(__name__)

def fetch_http_source(url: str, timeout: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch activity events from a remote HTTP JSON endpoint.
    Gracefully catches timeouts, network errors, and non-200 responses without crashing.
    """
    logger.info("Fetching remote activity from %s (timeout=%ds)...", url, timeout)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "3HPS-ShiftHandover/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                logger.warning("HTTP source %s returned status %d — skipping.", url, resp.status)
                return []
            data = resp.read().decode("utf-8")
            events = json.loads(data)
            if isinstance(events, list):
                return events
            logger.warning("HTTP source %s did not return a JSON array — skipping.", url)
            return []
    except urllib.error.HTTPError as exc:
        logger.warning("HTTP error fetching %s: %s — skipping.", url, exc)
    except urllib.error.URLError as exc:
        logger.warning("URL/Timeout error fetching %s: %s — skipping.", url, exc)
    except Exception as exc:
        logger.warning("Unexpected error fetching HTTP source %s: %s — skipping.", url, exc)
    return []
