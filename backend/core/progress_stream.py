"""
progress_stream.py — SSE streaming endpoint refactored to use shared_utils.
"""

import json
import logging
import os
import tempfile
import time
import base64
from datetime import datetime, timezone

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request

from .fetch_activity import fetch_activity
from .generator import generate_sections, summarize_sections, generate_slack_summary
from .publisher import render_docx
from .shared_utils import parse_utc, validate_shift_window, load_scenario

logger = logging.getLogger(__name__)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _generate_stream(body: dict):
    def emit(step_id: str, status: str, message: str, pct: int, extra: dict = None):
        payload = {
            "step": step_id,
            "status": status,
            "message": message,
            "pct": pct,
            "ts": datetime.now(tz=timezone.utc).strftime("%H:%M:%S"),
        }
        if extra:
            payload.update(extra)
        return _sse(payload)

    # 1. Validate
    yield emit("validate", "running", "Checking shift window parameters...", 5)
    time.sleep(0.2)

    try:
        request_id = body.get("request_id")
        if request_id:
            from .approval_workflow import check_approval_status
            req_status = check_approval_status(request_id)
            if not req_status:
                yield emit("validate", "error", f"Approval request '{request_id}' not found.", 0)
                return
            if req_status.get("status") != "approved":
                yield emit("validate", "error", f"Generation blocked: Request '{request_id}' status is '{req_status.get('status')}'. Manager approval required.", 0)
                return

        scenario = (body.get("scenario") or "").strip().lower() or None
        if scenario:
            raw_events, shift_start, shift_end = load_scenario(
                scenario, body.get("shift_start"), body.get("shift_end")
            )
        else:
            raw_events = None
            shift_start = parse_utc(body.get("shift_start", ""), "shift_start")
            shift_end = parse_utc(body.get("shift_end", ""), "shift_end")
            validate_shift_window(shift_start, shift_end)
    except ValueError as exc:
        yield emit("validate", "error", str(exc), 0)
        return
    except Exception as exc:
        yield emit("validate", "error", f"Validation error: {exc}", 0)
        return

    window_label = f"{shift_start.strftime('%Y-%m-%d %H:%M')} UTC → {shift_end.strftime('%H:%M')} UTC"
    yield emit("validate", "done", f"Window confirmed: {window_label}", 8)
    time.sleep(0.15)

    # 2. Fetch
    yield emit("fetch", "running", f"Fetching data for {'scenario: ' + scenario if scenario else 'live sources'}...", 15)
    time.sleep(0.25)

    try:
        if raw_events is not None:
            events = fetch_activity(shift_start, shift_end, events=raw_events)
        else:
            events = fetch_activity(shift_start, shift_end)
    except Exception as exc:
        yield emit("fetch", "error", f"Fetch failed: {exc}", 15)
        return

    yield emit("fetch", "done", f"Fetched {len(events)} events", 30)
    time.sleep(0.15)

    # 3. Dedup
    yield emit("dedup", "running", f"Deduplicating {len(events)} events...", 42)
    time.sleep(0.25)

    try:
        sections = generate_sections(events)
        summary = summarize_sections(sections)
    except Exception as exc:
        yield emit("dedup", "error", f"Dedup failed: {exc}", 42)
        return

    yield emit("dedup", "done", f"Collapsed to {summary['total_items']} unique records", 52)
    time.sleep(0.15)

    # 4. Sectioning
    yield emit("section", "running", "Classifying into report sections...", 60)
    time.sleep(0.2)

    counts = summary["counts"]
    yield emit("section", "done", "Sections classified successfully", 68, extra={"counts": counts})
    time.sleep(0.15)

    # 5. Render
    doc_type = (body.get("format") or body.get("file_type") or "docx").strip().lower()
    yield emit("render", "running", f"Generating .{doc_type} report...", 75)
    time.sleep(0.25)

    try:
        if doc_type == "pdf":
            from .pdf_publisher import render_pdf
            ext = ".pdf"
            mime = "application/pdf"
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="shift_report_") as tmp:
                tmp_path = tmp.name
            render_pdf(sections=sections, output_path=tmp_path, shift_start=shift_start, shift_end=shift_end)
        else:
            ext = ".docx"
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False, prefix="shift_report_") as tmp:
                tmp_path = tmp.name
            render_docx(sections=sections, output_path=tmp_path, shift_start=shift_start, shift_end=shift_end)
    except Exception as exc:
        yield emit("render", "error", f"Export failed: {exc}", 75)
        return

    yield emit("render", "done", f"Document ({doc_type.upper()}) rendered successfully", 85)
    time.sleep(0.15)

    # 6. Finalise
    yield emit("finalise", "running", "Packaging report & generating Slack summary...", 92)
    time.sleep(0.2)

    try:
        with open(tmp_path, "rb") as f:
            file_bytes = f.read()
        file_b64 = base64.b64encode(file_bytes).decode("utf-8")
        os.unlink(tmp_path)

        slack_summary = generate_slack_summary(sections, shift_start, shift_end)
    except Exception as exc:
        yield emit("finalise", "error", f"Packaging failed: {exc}", 92)
        return

    filename = f"shift_report_{shift_start.strftime('%Y%m%d_%H%M')}_{shift_end.strftime('%H%M')}{ext}"
    yield emit(
        "finalise",
        "done",
        f"Report ready: {filename} ({summary['total_items']} items)",
        100,
        extra={
            "filename": filename,
            "file_b64": file_b64,
            "summary": summary,
            "slack_summary": slack_summary,
        },
    )


@api_view(["POST"])
def generate_report_stream(request: Request):
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    response = StreamingHttpResponse(_generate_stream(body), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    response["Access-Control-Allow-Origin"] = "*"
    return response
