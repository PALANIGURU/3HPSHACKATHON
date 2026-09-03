"""
tests.py — Comprehensive Test Suite for 3HPS Shift Handover Report Generator.

Covers:
- Reproducibility (2x runs yield identical item counts and section assignments)
- Deduplication correctness (N events collapse to 1 line per record_id)
- Boundary filtering (shift_start INCLUSIVE, shift_end EXCLUSIVE)
- Sectioning logic mapping
- Hostile input handling (malformed timestamp, missing source file)
- HTTP timeout / unreachable remote source simulation
- DRF API endpoint smoke test
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from core.fetch_activity import fetch_activity, _process_event_list
from core.generator import generate_sections, summarize_sections, _classify_status
from core.publisher import render_docx
from core.http_source import fetch_http_source
from core.shared_utils import parse_utc, validate_shift_window, load_scenario


class ReproducibilityAndDedupTests(TestCase):
    """Protects 10-mark Reproducibility and 15-mark Grounding requirement."""

    def setUp(self):
        self.shift_start = datetime(2024, 1, 15, 7, 0, 0, tzinfo=timezone.utc)
        self.shift_end = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_scenario_reproducibility_busy(self):
        """Verify that running scenario 'busy' twice yields identical item counts and section breakdowns."""
        events1, start1, end1 = load_scenario("busy")
        fetched1 = fetch_activity(start1, end1, events=events1)
        sections1 = generate_sections(fetched1)
        summary1 = summarize_sections(sections1)

        events2, start2, end2 = load_scenario("busy")
        fetched2 = fetch_activity(start2, end2, events=events2)
        sections2 = generate_sections(fetched2)
        summary2 = summarize_sections(sections2)

        self.assertEqual(summary1["total_items"], summary2["total_items"])
        self.assertEqual(summary1["counts"], summary2["counts"])
        self.assertEqual(sections1, sections2)

    def test_scenario_reproducibility_messy(self):
        """Verify messy scenario reproducibility twice."""
        events1, start1, end1 = load_scenario("messy")
        fetched1 = fetch_activity(start1, end1, events=events1)
        sections1 = generate_sections(fetched1)

        events2, start2, end2 = load_scenario("messy")
        fetched2 = fetch_activity(start2, end2, events=events2)
        sections2 = generate_sections(fetched2)

        self.assertEqual(sections1, sections2)

    def test_deduplication_collapses_to_latest_state(self):
        """Verify duplicate updates to the same (source, record_id) collapse to 1 line with latest status."""
        raw_events = [
            {
                "source": "tickets",
                "record_id": "TKT-DEDUP-1",
                "timestamp": "2024-01-15T08:00:00Z",
                "summary": "Initial report",
                "status": "open",
            },
            {
                "source": "tickets",
                "record_id": "TKT-DEDUP-1",
                "timestamp": "2024-01-15T09:00:00Z",
                "summary": "Intermediate investigation",
                "status": "in_progress",
            },
            {
                "source": "tickets",
                "record_id": "TKT-DEDUP-1",
                "timestamp": "2024-01-15T10:00:00Z",
                "summary": "Fix applied and verified",
                "status": "resolved",
            },
        ]
        events = fetch_activity(self.shift_start, self.shift_end, events=raw_events)
        sections = generate_sections(events)

        # Final state is 'resolved' -> must land in 'completed' section only
        self.assertEqual(len(sections["completed"]), 1)
        self.assertEqual(len(sections["in_progress"]), 0)
        self.assertEqual(sections["completed"][0]["record_id"], "TKT-DEDUP-1")
        self.assertEqual(sections["completed"][0]["summary"], "Fix applied and verified")
        self.assertEqual(sections["completed"][0]["status"], "resolved")


class GroundingAndBoundaryTests(TestCase):
    """Grounding & strict boundary tests [shift_start, shift_end)."""

    def setUp(self):
        self.shift_start = datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        self.shift_end = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_boundary_shift_start_inclusive(self):
        """Event exactly at shift_start (08:00:00Z) MUST be included."""
        events_raw = [
            {
                "source": "tickets",
                "record_id": "TKT-BOUND-1",
                "timestamp": "2024-01-15T08:00:00Z",
                "summary": "Event right at shift start boundary",
                "status": "open",
            }
        ]
        fetched = fetch_activity(self.shift_start, self.shift_end, events=events_raw)
        self.assertEqual(len(fetched), 1)
        self.assertEqual(fetched[0]["record_id"], "TKT-BOUND-1")

    def test_boundary_shift_end_exclusive(self):
        """Event exactly at shift_end (12:00:00Z) MUST be excluded."""
        events_raw = [
            {
                "source": "tickets",
                "record_id": "TKT-BOUND-2",
                "timestamp": "2024-01-15T12:00:00Z",
                "summary": "Event right at shift end boundary",
                "status": "open",
            }
        ]
        fetched = fetch_activity(self.shift_start, self.shift_end, events=events_raw)
        self.assertEqual(len(fetched), 0)

    def test_section_status_classification(self):
        """Verify status mapping to section rules."""
        self.assertEqual(_classify_status("resolved"), "completed")
        self.assertEqual(_classify_status("closed"), "completed")
        self.assertEqual(_classify_status("open"), "in_progress")
        self.assertEqual(_classify_status("investigating"), "in_progress")
        self.assertEqual(_classify_status("blocked"), "blockers")
        self.assertEqual(_classify_status("critical"), "blockers")
        self.assertEqual(_classify_status("monitoring"), "watch_list")
        self.assertEqual(_classify_status("watch"), "watch_list")


class HostileInputAndTimeoutTests(TestCase):
    """Hostile input and HTTP timeout / unreachable remote source tests."""

    def setUp(self):
        self.shift_start = datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
        self.shift_end = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_malformed_timestamp_skips_without_crashing(self):
        """Verify events with bad timestamps are logged and skipped without throwing an exception."""
        raw_events = [
            {
                "source": "tickets",
                "record_id": "BAD-TS-1",
                "timestamp": "invalid-date-string",
                "summary": "Broken timestamp",
                "status": "open",
            },
            {
                "source": "tickets",
                "record_id": "GOOD-1",
                "timestamp": "2024-01-15T09:00:00Z",
                "summary": "Valid timestamp",
                "status": "open",
            },
        ]
        fetched = fetch_activity(self.shift_start, self.shift_end, events=raw_events)
        self.assertEqual(len(fetched), 1)
        self.assertEqual(fetched[0]["record_id"], "GOOD-1")

    def test_missing_source_file_handled_gracefully(self):
        """Verify missing source file logs warning and doesn't crash."""
        with patch("builtins.open", side_effect=FileNotFoundError("File missing")):
            fetched = fetch_activity(self.shift_start, self.shift_end)
            self.assertEqual(len(fetched), 0)

    def test_http_source_unreachable_api_timeout_simulation(self):
        """Simulate HTTP source timeout / unreachable server."""
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection timed out")):
            result = fetch_http_source("http://unreachable.example.com/api", timeout=1)
            self.assertEqual(result, [])  # Must return empty list, not raise exception


class DRFAPIEndpointTests(TestCase):
    """DRF Endpoint tests."""

    def setUp(self):
        self.client = APIClient()

    def test_generate_report_api_success(self):
        """Verify POST /api/generate-report/ returns 200 and a valid .docx attachment."""
        url = reverse("generate-report")
        payload = {
            "scenario": "quiet",
            "shift_start": "2024-01-15T06:00:00Z",
            "shift_end": "2024-01-15T07:30:00Z",
        }
        response = self.client.post(url, data=payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        content_bytes = b"".join(response.streaming_content)
        self.assertTrue(len(content_bytes) > 1000)

    def test_generate_report_api_slack_format(self):
        """Verify POST /api/generate-report/ with format='slack' returns text summary."""
        url = reverse("generate-report")
        payload = {
            "scenario": "quiet",
            "format": "slack",
        }
        response = self.client.post(url, data=payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("SHIFT HANDOVER SUMMARY", response.content.decode("utf-8"))

    def test_generate_report_api_invalid_window_returns_400(self):
        """Verify invalid shift window returns 400 Bad Request."""
        url = reverse("generate-report")
        payload = {
            "shift_start": "2024-01-15T12:00:00Z",
            "shift_end": "2024-01-15T07:00:00Z",
        }
        response = self.client.post(url, data=payload, format="json")
        self.assertEqual(response.status_code, 400)
