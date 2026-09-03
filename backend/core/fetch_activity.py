"""
fetch_activity.py — Step 6: Read JSON & HTTP data sources, normalize timestamps,
filter to shift window [shift_start, shift_end), and integrate carry-forward snapshots.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from .http_source import fetch_http_source

logger = logging.getLogger(__name__)


def _parse_utc(timestamp_str: str) -> Optional[datetime]:
    if not isinstance(timestamp_str, str):
        return None
    ts = timestamp_str.strip()
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S+00:00",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(ts, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _validate_event(event: dict, source_file: str) -> bool:
    required = ["source", "record_id", "timestamp", "summary", "status"]
    for field in required:
        if field not in event:
            logger.warning(
                "Skipping event in %s: missing required field '%s'. Event: %s",
                source_file,
                field,
                event,
            )
            return False
    return True


def fetch_activity(
    shift_start: datetime,
    shift_end: datetime,
    data_dir: Optional[str] = None,
    events: Optional[list] = None,
    include_snapshot: bool = True,
) -> list[dict]:
    if shift_start.tzinfo is None:
        shift_start = shift_start.replace(tzinfo=timezone.utc)
    if shift_end.tzinfo is None:
        shift_end = shift_end.replace(tzinfo=timezone.utc)

    all_events = []

    if events is not None:
        all_events.extend(
            _process_event_list(events, "<scenario>", shift_start, shift_end)
        )
    else:
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"
        data_dir = Path(data_dir)

        # Load sources config
        sources_cfg = data_dir / "sources.json"
        sources_list = []
        if sources_cfg.exists():
            try:
                with open(sources_cfg, "r", encoding="utf-8") as f:
                    sources_list = json.load(f).get("sources", [])
            except Exception as exc:
                logger.warning("Failed to load sources.json: %s. Falling back to default files.", exc)

        if not sources_list:
            sources_list = [
                {"id": "tickets", "type": "file", "path": str(data_dir / "tickets.json"), "enabled": True},
                {"id": "incidents", "type": "file", "path": str(data_dir / "incidents.json"), "enabled": True},
                {"id": "chat", "type": "file", "path": str(data_dir / "chat.json"), "enabled": True},
            ]

        for src in sources_list:
            if not src.get("enabled", True):
                continue
            
            src_type = src.get("type", "file")
            if src_type == "file":
                fpath = Path(src.get("path", ""))
                if not fpath.is_absolute():
                    fpath = data_dir.parent / fpath if (data_dir.parent / fpath).exists() else data_dir / fpath.name
                
                if not fpath.exists():
                    logger.warning("Data source file not found: %s", fpath)
                    continue

                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    if isinstance(raw, list):
                        all_events.extend(_process_event_list(raw, str(fpath), shift_start, shift_end))
                except Exception as exc:
                    logger.warning("Failed reading file %s: %s — skipping.", fpath, exc)

            elif src_type == "http":
                url = src.get("url", "")
                timeout = src.get("timeout_seconds", 5)
                raw = fetch_http_source(url, timeout=timeout)
                if raw:
                    all_events.extend(_process_event_list(raw, url, shift_start, shift_end))

    # Incorporate previous shift carry-forward snapshot (stretch feature)
    # Filtered to items prior to shift_end AND within 24 hours prior to shift_start to prevent indefinite resurfacing
    if include_snapshot and events is None:
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"
        snapshot_path = Path(data_dir) / "previous_shift_snapshot.json"
        if snapshot_path.exists():
            try:
                from datetime import timedelta
                snapshot_floor = shift_start - timedelta(hours=24)
                with open(snapshot_path, "r", encoding="utf-8") as f:
                    snap_raw = json.load(f)
                if isinstance(snap_raw, list):
                    for item in snap_raw:
                        if isinstance(item, dict) and _validate_event(item, str(snapshot_path)):
                            parsed_ts = _parse_utc(item["timestamp"])
                            if parsed_ts and snapshot_floor <= parsed_ts < shift_end:
                                norm = dict(item)
                                norm["_parsed_timestamp"] = parsed_ts
                                norm["_still_open"] = True
                                all_events.append(norm)
            except Exception as exc:
                logger.warning("Failed reading previous shift snapshot: %s", exc)

    return all_events


def _process_event_list(
    raw_events: list,
    source_label: str,
    shift_start: datetime,
    shift_end: datetime,
) -> list[dict]:
    result = []
    for event in raw_events:
        if not isinstance(event, dict):
            logger.warning("Skipping non-dict entry in %s: %r", source_label, event)
            continue

        if not _validate_event(event, source_label):
            continue

        parsed_ts = _parse_utc(event["timestamp"])
        if parsed_ts is None:
            logger.warning(
                "Skipping event with malformed timestamp in %s: record_id=%s, timestamp=%r",
                source_label,
                event.get("record_id", "<unknown>"),
                event.get("timestamp"),
            )
            continue

        # Strict boundary filtering: [shift_start, shift_end)
        # shift_start is INCLUSIVE (>=), shift_end is EXCLUSIVE (<)
        if not (shift_start <= parsed_ts < shift_end):
            continue

        normalized = dict(event)
        normalized["_parsed_timestamp"] = parsed_ts
        result.append(normalized)

    return result
