"""
progress_stream.py — Server-Sent Events (SSE) endpoint for real-time
report generation progress.

Endpoint: POST /api/generate-report/stream/
Uses Django's StreamingHttpResponse to push progress events to the frontend
as the report is generated step by step.

SSE event format:
  data: {"step": "fetch", "status": "running", "message": "...", "pct": 20}
"""

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request

from .fetch_activity import fetch_activity
from .generator import generate_sections, summarize_sections
from .publisher import render_docx

logger = logging.getLogger(__name__)

SCENARIOS_DIR = Path(__file__).parent / "scenarios"
VALID_SCENARIOS = {"quiet", "busy", "messy"}

# Progress steps definition
STEPS = [
    {"id": "validate",  "label": "Validating parameters",      "pct": 8},
    {"id": "fetch",     "label": "Fetching activity data",      "pct": 30},
    {"id": "dedup",     "label": "Deduplicating events",        "pct": 52},
    {"id": "section",   "label": "Applying sectioning rules",   "pct": 68},
    {"id": "render",    "label": "Rendering .docx report",      "pct": 85},
    {"id": "finalise",  "label": "Finalising and packaging",    "pct": 100},
]


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


def _parse_utc_stream(value: str, field_name: str) -> datetime:
    """Parse ISO8601 datetime to UTC-aware datetime."""
    for fmt in [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ]:
        try:
            dt = datetime.strptime(value.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(
        f"'{field_name}' has invalid datetime format: {value!r}. "
        "Use ISO8601 e.g. '2024-01-15T07:00:00Z'."
    )


def _generate_stream(body: dict):
    """
    Generator function that yields SSE events as each step completes.
    Final event contains the base64-encoded .docx for download.
    """
    import base64

    def emit(step_id: str, status: str, message: str, pct: int, extra: dict = None):
        payload = {
            "step": step_id,
            "status": status,   # running | done | error
            "message": message,
            "pct": pct,
            "ts": datetime.now(tz=timezone.utc).strftime("%H:%M:%S"),
        }
        if extra:
            payload.update(extra)
        return _sse(payload)

    # ── Step 1: Validate ─────────────────────────────────────────────────────
    yield emit("validate", "running", "Checking shift window parameters...", 5)
    time.sleep(0.3)

    try:
        shift_start_raw = body.get("shift_start", "")
        shift_end_raw = body.get("shift_end", "")
        scenario = (body.get("scenario") or "").strip().lower() or None

        shift_start = _parse_utc_stream(shift_start_raw, "shift_start") if shift_start_raw else None
        shift_end   = _parse_utc_stream(shift_end_raw,   "shift_end")   if shift_end_raw   else None

        # Load scenario defaults if shift times not given
        if scenario:
            if scenario not in VALID_SCENARIOS:
                yield emit("validate", "error",
                           f"Unknown scenario '{scenario}'. Valid: quiet, busy, messy", 0)
                return
            sc_path = SCENARIOS_DIR / f"{scenario}.json"
            with open(sc_path, "r", encoding="utf-8") as f:
                sc_data = json.load(f)
            if shift_start is None and "shift_start" in sc_data:
                shift_start = _parse_utc_stream(sc_data["shift_start"], "shift_start")
            if shift_end is None and "shift_end" in sc_data:
                shift_end = _parse_utc_stream(sc_data["shift_end"], "shift_end")
            raw_events = sc_data.get("events", [])
        else:
            raw_events = None

        if not shift_start or not shift_end:
            yield emit("validate", "error",
                       "shift_start and shift_end are required", 0)
            return
        if shift_start >= shift_end:
            yield emit("validate", "error",
                       "shift_start must be before shift_end", 0)
            return

    except Exception as exc:
        yield emit("validate", "error", f"Validation error: {exc}", 0)
        return

    window_label = (
        f"{shift_start.strftime('%Y-%m-%d %H:%M')} UTC → "
        f"{shift_end.strftime('%H:%M')} UTC"
    )
    yield emit("validate", "done",
               f"Window confirmed: {window_label}", 8)
    time.sleep(0.2)

    # ── Step 2: Fetch activity ────────────────────────────────────────────────
    yield emit("fetch", "running",
               f"Reading {'scenario: ' + scenario if scenario else 'data sources'}...", 15)
    time.sleep(0.4)

    try:
        if raw_events is not None:
            events = fetch_activity(shift_start, shift_end, events=raw_events)
        else:
            events = fetch_activity(shift_start, shift_end)
    except Exception as exc:
        yield emit("fetch", "error", f"Fetch failed: {exc}", 15)
        return

    yield emit("fetch", "done",
               f"Fetched {len(events)} events in window", 30)
    time.sleep(0.25)

    # ── Step 3: Dedup ─────────────────────────────────────────────────────────
    yield emit("dedup", "running",
               f"Deduplicating {len(events)} events by (source, record_id)...", 42)
    time.sleep(0.35)

    try:
        sections = generate_sections(events)
        summary  = summarize_sections(sections)
    except Exception as exc:
        yield emit("dedup", "error", f"Dedup failed: {exc}", 42)
        return

    unique_count = summary["total_items"]
    yield emit("dedup", "done",
               f"Collapsed to {unique_count} unique records", 52)
    time.sleep(0.2)

    # ── Step 4: Sectioning ────────────────────────────────────────────────────
    yield emit("section", "running", "Classifying into 4 report sections...", 60)
    time.sleep(0.3)

    counts = summary["counts"]
    section_summary = (
        f"Completed: {counts['completed']}  |  "
        f"In Progress: {counts['in_progress']}  |  "
        f"Blockers: {counts['blockers']}  |  "
        f"Watch-list: {counts['watch_list']}"
    )
    yield emit("section", "done", section_summary, 68,
               extra={"counts": counts})
    time.sleep(0.2)

    # ── Step 5: Render .docx ──────────────────────────────────────────────────
    yield emit("render", "running", "Generating .docx with python-docx...", 75)
    time.sleep(0.3)

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".docx", delete=False, prefix="shift_report_"
        ) as tmp:
            tmp_path = tmp.name

        render_docx(
            sections=sections,
            output_path=tmp_path,
            shift_start=shift_start,
            shift_end=shift_end,
        )
    except Exception as exc:
        yield emit("render", "error", f"Export failed: {exc}", 75)
        return

    yield emit("render", "done", "Document rendered successfully", 85)
    time.sleep(0.2)

    # ── Step 6: Finalise ──────────────────────────────────────────────────────
    yield emit("finalise", "running", "Encoding and packaging report...", 92)
    time.sleep(0.3)

    try:
        with open(tmp_path, "rb") as f:
            file_bytes = f.read()
        file_b64 = base64.b64encode(file_bytes).decode("utf-8")
        os.unlink(tmp_path)
    except Exception as exc:
        yield emit("finalise", "error", f"Packaging failed: {exc}", 92)
        return

    filename = (
        f"shift_report_{shift_start.strftime('%Y%m%d_%H%M')}"
        f"_{shift_end.strftime('%H%M')}.docx"
    )

    yield emit("finalise", "done",
               f"Report ready: {filename}  ({len(file_bytes) // 1024} KB, {unique_count} items)",
               100,
               extra={
                   "filename": filename,
                   "file_b64": file_b64,
                   "summary": summary,
               })


@api_view(["POST"])
def generate_report_stream(request: Request):
    """
    POST /api/generate-report/stream/
    Returns a Server-Sent Events stream with progress events.
    Final event includes base64-encoded .docx for download.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    response = StreamingHttpResponse(
        _generate_stream(body),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Access-Control-Allow-Origin"] = "*"
    return response
