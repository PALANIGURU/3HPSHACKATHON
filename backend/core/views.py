"""
views.py — DRF API endpoints for shift handover report generation and Slack text export.
"""

import json
import logging
import tempfile
from pathlib import Path

from django.http import FileResponse, JsonResponse, HttpResponse
from rest_framework.decorators import api_view
from rest_framework.request import Request

from .fetch_activity import fetch_activity
from .generator import generate_sections, summarize_sections, generate_slack_summary
from .publisher import render_docx
from .shared_utils import parse_utc, validate_shift_window, load_scenario

logger = logging.getLogger(__name__)


@api_view(["POST"])
def generate_report(request: Request):
    """
    POST /api/generate-report/
    Accepts shift_start, shift_end, optional scenario, and optional format ('docx' or 'slack').
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    scenario = (body.get("scenario") or "").strip().lower() or None
    export_format = (body.get("format") or "docx").strip().lower()

    try:
        if scenario:
            raw_events, shift_start, shift_end = load_scenario(
                scenario, body.get("shift_start"), body.get("shift_end")
            )
            events = fetch_activity(shift_start, shift_end, events=raw_events)
        else:
            shift_start = parse_utc(body.get("shift_start", ""), "shift_start")
            shift_end = parse_utc(body.get("shift_end", ""), "shift_end")
            validate_shift_window(shift_start, shift_end)
            events = fetch_activity(shift_start, shift_end)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Error during fetch_activity: %s", exc)
        return JsonResponse({"error": f"Failed to fetch activity data: {exc}"}, status=500)

    try:
        sections = generate_sections(events)
        summary = summarize_sections(sections)
    except Exception as exc:
        logger.exception("Error during generate_sections: %s", exc)
        return JsonResponse({"error": f"Failed to generate report sections: {exc}"}, status=500)

    # Return Slack Markdown text export if requested
    if export_format == "slack":
        slack_txt = generate_slack_summary(sections, shift_start, shift_end)
        response = HttpResponse(slack_txt, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="slack_handover_summary.txt"'
        return response

    # Render .docx report
    try:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False, prefix="shift_report_") as tmp:
            tmp_path = tmp.name

        render_docx(
            sections=sections,
            output_path=tmp_path,
            shift_start=shift_start,
            shift_end=shift_end,
        )
    except RuntimeError as exc:
        logger.error("render_docx failed: %s", exc)
        return JsonResponse({"error": str(exc)}, status=500)
    except Exception as exc:
        logger.exception("Unexpected error in render_docx: %s", exc)
        return JsonResponse({"error": f"Unexpected export failure: {exc}"}, status=500)

    filename = f"shift_report_{shift_start.strftime('%Y%m%d_%H%M')}_{shift_end.strftime('%H%M')}.docx"
    try:
        response = FileResponse(
            open(tmp_path, "rb"),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Report-Items"] = str(summary["total_items"])
        response["X-Report-Counts"] = json.dumps(summary["counts"])
        return response
    except Exception as exc:
        logger.error("Failed to stream report file: %s", exc)
        return JsonResponse({"error": f"Failed to deliver report: {exc}"}, status=500)


@api_view(["GET"])
def health_check(request: Request):
    return JsonResponse({"status": "ok", "service": "3HPS Shift Handover API"})
