"""
shared_utils.py — Shared helpers used by views.py, progress_stream.py,
and management commands. Extracted to avoid copy-paste bugs.

Provides:
  - parse_utc(value, field_name) -> datetime
  - load_scenario(scenario_name) -> (events, shift_start, shift_end)
  - validate_shift_window(shift_start, shift_end)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
VALID_SCENARIOS = frozenset({"quiet", "busy", "messy"})


def parse_utc(value: str, field_name: str = "datetime") -> datetime:
    """
    Parse an ISO8601 datetime string into a UTC-aware datetime.
    Raises ValueError with a helpful message if parsing fails.
    """
    if not value or not isinstance(value, str):
        raise ValueError(
            f"'{field_name}' is required and must be a string. "
            "Use ISO8601 format, e.g. '2024-01-15T07:00:00Z'."
        )
    value = value.strip()
    for fmt in [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",  # naive — assumed UTC
    ]:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(
        f"'{field_name}' has an unrecognised datetime format: {value!r}. "
        "Use ISO8601, e.g. '2024-01-15T07:00:00Z'."
    )


def validate_shift_window(
    shift_start: datetime, shift_end: datetime, raise_exc=True
) -> Optional[str]:
    """
    Validate that shift_start < shift_end.
    Returns None on success, or an error message string.
    Raises ValueError if raise_exc=True and window is invalid.
    """
    if shift_start >= shift_end:
        msg = "shift_start must be strictly before shift_end."
        if raise_exc:
            raise ValueError(msg)
        return msg
    return None


def load_scenario(
    scenario_name: str,
    override_start: Optional[str] = None,
    override_end: Optional[str] = None,
) -> Tuple[list, datetime, datetime]:
    """
    Load a named test scenario and return (events, shift_start, shift_end).

    Args:
        scenario_name:  One of 'quiet', 'busy', 'messy'.
        override_start: Optional ISO8601 string to override the scenario's shift_start.
        override_end:   Optional ISO8601 string to override the scenario's shift_end.

    Returns:
        (events, shift_start, shift_end)

    Raises:
        ValueError: If scenario not found or shift window not resolvable.
    """
    if scenario_name not in VALID_SCENARIOS:
        raise ValueError(
            f"Unknown scenario '{scenario_name}'. Valid: {sorted(VALID_SCENARIOS)}"
        )
    scenario_path = SCENARIOS_DIR / f"{scenario_name}.json"
    if not scenario_path.exists():
        raise ValueError(f"Scenario file not found: {scenario_path}")

    try:
        with open(scenario_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to load scenario '{scenario_name}': {exc}") from exc

    raw_events = data.get("events", [])

    start_raw = override_start or data.get("shift_start")
    end_raw   = override_end   or data.get("shift_end")

    if not start_raw or not end_raw:
        raise ValueError(
            f"Scenario '{scenario_name}' has no shift_start/shift_end "
            "and none were provided."
        )

    shift_start = parse_utc(start_raw, "shift_start")
    shift_end   = parse_utc(end_raw,   "shift_end")
    validate_shift_window(shift_start, shift_end)

    # Normalize parsed timestamps on scenario events
    events = []
    for ev in raw_events:
        if isinstance(ev, dict) and "timestamp" in ev:
            norm = dict(ev)
            try:
                norm["_parsed_timestamp"] = parse_utc(ev["timestamp"])
                events.append(norm)
            except ValueError:
                pass

    return events, shift_start, shift_end
