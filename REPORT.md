# 3HPS Hackathon — Shift Handover Report Generator

## Project Summary

A Django + Django REST Framework backend that automatically generates structured `.docx` shift handover reports from JSON-based activity data sources. No database models are used for events — all data is read directly from JSON files.

---

## Architecture

```
backend/
├── backend/          # Django project (settings, urls, wsgi)
├── core/
│   ├── data/         # JSON mock data sources (tickets, incidents, chat)
│   ├── scenarios/    # Test scenarios (quiet, busy, messy)
│   ├── management/
│   │   └── commands/
│   │       └── generate_report.py  # CLI trigger
│   ├── fetch_activity.py   # Step 6: event reader + normalizer
│   ├── generator.py        # Step 7: sectioner + deduplicator
│   ├── publisher.py        # Step 8: .docx renderer
│   ├── views.py            # Step 9: DRF API endpoint
│   └── urls.py
└── manage.py
```

### Technology Stack
| Component | Technology |
|-----------|-----------|
| Backend framework | Django 6 + Django REST Framework |
| Event data | JSON files (no DB models for events) |
| Report export | python-docx |
| Secrets management | python-decouple (.env) |
| DB (admin only) | SQLite |

---

## Sectioning Rules

| Section | Statuses |
|---------|---------|
| **Completed** | `resolved`, `closed`, `done`, `completed`, `fixed`, `deployed` |
| **In Progress** | `open`, `in_progress`, `investigating`, `active`, `acknowledged` |
| **Blockers** | `blocked`, `escalated`, `critical`, `urgent` |
| **Watch-list** | `monitoring`, `watch`, `pending`, `deferred` |

**Dedup rule**: Group by `(source, record_id)` → sort by timestamp ascending → collapse to ONE record using final (latest) state. A ticket that opens and closes inside the window appears in **Completed** (latest state wins).

---

## API Endpoint

### POST `/api/generate-report/`

**Request:**
```json
{
  "shift_start": "2024-01-15T07:00:00Z",
  "shift_end": "2024-01-15T12:00:00Z",
  "scenario": "quiet"
}
```

**Response:** `.docx` file download with headers:
- `Content-Disposition: attachment; filename="shift_report_20240115_0700_1200.docx"`
- `X-Report-Items: 10`
- `X-Report-Counts: {"completed": 3, "in_progress": 2, "blockers": 2, "watch_list": 3}`

**Error responses:** `400` (bad params) or `500` (generation/export failure) with JSON body.

### GET `/api/health/`
Returns `{"status": "ok", "service": "3HPS Shift Handover API"}`.

---

## CLI Usage

```bash
# Using a test scenario
python manage.py generate_report --scenario busy --output report.docx

# Using explicit shift window (reads from core/data/*.json)
python manage.py generate_report \
  --shift-start "2024-01-15T07:00:00Z" \
  --shift-end   "2024-01-15T12:00:00Z" \
  --output report.docx
```

---

## Reproducibility Proof

All 3 scenarios run twice produce **identical item counts**:

| Scenario | Run 1 | Run 2 | Match? |
|----------|-------|-------|--------|
| quiet | completed=1, in_progress=0, blockers=0, watch_list=1 | completed=1, in_progress=0, blockers=0, watch_list=1 | **PASS** |
| busy | completed=3, in_progress=2, blockers=2, watch_list=3 | completed=3, in_progress=2, blockers=2, watch_list=3 | **PASS** |
| messy | completed=2, in_progress=2, blockers=0, watch_list=2 | completed=2, in_progress=2, blockers=0, watch_list=2 | **PASS** |

Reproducibility is guaranteed by:
1. Deterministic dedup: group by `(source, record_id)`, sort by timestamp, always take last
2. Deterministic output order: sections sorted by `(source, record_id)`
3. No random or time-dependent state in the generation pipeline

---

## Hostile Input Hardening

| Input | Behavior |
|-------|---------|
| Empty shift window (start == end) | CommandError: `--shift-start must be before --shift-end` |
| Reversed shift window (start > end) | CommandError: same validation |
| Malformed timestamp argument | CommandError with ISO8601 format hint |
| Malformed event timestamp in JSON | `WARNING` log + skip event, never crash |
| Unreadable/missing JSON source file | `WARNING` log + skip file, continues with remaining sources |
| Malformed JSON file | `WARNING` log + skip file, continues with remaining sources |
| Unknown status value | Falls back to `in_progress` section |

---

## Test Scenarios

| Scenario | Window | Events In | Items Out | Notes |
|----------|--------|-----------|-----------|-------|
| `quiet.json` | 06:00–07:30 | 2 | 2 | Minimal activity, empty blockers/in-progress |
| `busy.json` | 07:00–12:00 | 15 | 10 | All 4 sections populated, 5 deduped records |
| `messy.json` | 08:00–14:00 | 14 | 6 | Duplicates, out-of-order timestamps, open+close in window, 1 malformed skipped |

---

## Running the Server

```bash
cd backend
pip install -r ../requirements.txt
python manage.py migrate
python manage.py runserver

# Test the API
curl -X POST http://127.0.0.1:8000/api/generate-report/ \
  -H "Content-Type: application/json" \
  -d '{"shift_start":"2024-01-15T07:00:00Z","shift_end":"2024-01-15T12:00:00Z","scenario":"busy"}' \
  --output report.docx
```

---

## Design Decisions

1. **No DB for events** — JSON files are the single source of truth. This makes the system stateless and trivially reproducible.
2. **Latest-state dedup** — Only the most recent update per `(source, record_id)` is shown. A ticket that opens and closes in the window appears as "completed" — this matches what handover readers care about (final state).
3. **Fail loudly on export** — `publisher.py` raises `RuntimeError` on any failure. The CLI exits non-zero; the API returns HTTP 500. Partial/corrupt reports are never delivered.
4. **All 4 sections always present** — Empty sections show "Nothing to report." Omitting a section would create ambiguity about whether it was intentionally empty or missing due to a bug.
5. **python-decouple** — Secrets (`SECRET_KEY`) are loaded from `.env` and never committed to git.
