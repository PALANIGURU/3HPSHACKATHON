"""
fetch_activity.py — Step 6: Read JSON data sources, normalize timestamps,
filter to shift window [shift_start, shift_end).

Rules:
- Normalize ALL timestamps to UTC (timezone-aware datetime objects).
- Filter strictly to [shift_start, shift_end) — start inclusive, end exclusive.
- Skip unreadable/malformed files or events with logged warnings (never crash).
- Return a flat list of normalized event dicts.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# All supported data source filenames
DATA_SOURCES = ["tickets.json", "incidents.json", "chat.json"]


def _parse_utc(timestamp_str: str) -> Optional[datetime]:
    """
    Parse an ISO8601 timestamp string and return a UTC-aware datetime.
    Returns None if parsing fails (caller logs and skips the event).
    """
    if not isinstance(timestamp_str, str):
        return None
    ts = timestamp_str.strip()
    # Try multiple ISO8601 formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S+00:00",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(ts, fmt)
            if dt.tzinfo is None:
                # Assume UTC for naive timestamps
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _validate_event(event: dict, source_file: str) -> bool:
    """
    Validate required fields of an event dict.
    Logs a warning and returns False for invalid events.
    """
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
) -> list[dict]:
    """
    Fetch and normalize activity events for a shift window.

    Args:
        shift_start: UTC-aware datetime for shift start (inclusive).
        shift_end:   UTC-aware datetime for shift end (exclusive).
        data_dir:    Path to directory containing JSON source files.
                     If None, defaults to core/data/ relative to this file.
        events:      If provided, use this list directly (for scenario mode)
                     instead of reading from data_dir.

    Returns:
        List of normalized event dicts with a '_parsed_timestamp' key (datetime).
        Events are NOT yet deduplicated or sorted — that's generator.py's job.
    """
    # Ensure shift_start and shift_end are UTC-aware
    if shift_start.tzinfo is None:
        shift_start = shift_start.replace(tzinfo=timezone.utc)
    if shift_end.tzinfo is None:
        shift_end = shift_end.replace(tzinfo=timezone.utc)

    all_events = []

    if events is not None:
        # Scenario mode: events supplied directly
        raw_events = events
        source_label = "<scenario>"
        all_events.extend(
            _process_event_list(raw_events, source_label, shift_start, shift_end)
        )
    else:
        # File mode: read from data_dir
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"
        data_dir = Path(data_dir)

        for source_file in DATA_SOURCES:
            file_path = data_dir / source_file
            if not file_path.exists():
                logger.warning("Data source file not found, skipping: %s", file_path)
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Failed to parse JSON from %s: %s — skipping file.", file_path, exc
                )
                continue
            except OSError as exc:
                logger.warning(
                    "Cannot read file %s: %s — skipping file.", file_path, exc
                )
                continue

            if not isinstance(raw, list):
                logger.warning(
                    "Expected a JSON array in %s, got %s — skipping.",
                    file_path,
                    type(raw).__name__,
                )
                continue

            all_events.extend(
                _process_event_list(raw, str(file_path), shift_start, shift_end)
            )

    return all_events


def _process_event_list(
    raw_events: list,
    source_label: str,
    shift_start: datetime,
    shift_end: datetime,
) -> list[dict]:
    """
    Validate, parse timestamps, and filter events to the shift window.
    Skips malformed events with logged warnings.
    """
    result = []
    for event in raw_events:
        if not isinstance(event, dict):
            logger.warning(
                "Skipping non-dict entry in %s: %r", source_label, event
            )
            continue

        if not _validate_event(event, source_label):
            continue

        parsed_ts = _parse_utc(event["timestamp"])
        if parsed_ts is None:
            logger.warning(
                "Skipping event with malformed timestamp in %s: record_id=%s, "
                "timestamp=%r",
                source_label,
                event.get("record_id", "<unknown>"),
                event.get("timestamp"),
            )
            continue

        # Filter: [shift_start, shift_end)
        if not (shift_start <= parsed_ts < shift_end):
            continue

        normalized = dict(event)
        normalized["_parsed_timestamp"] = parsed_ts
        result.append(normalized)

    return result
