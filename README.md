# 3HPS Hackathon — Shift Handover Report Generator

Automated Shift Handover Report Generator built with **Django + Django REST Framework** backend, **Vite + React** frontend, and **python-docx** report generator.

---

## Quick Start

### 1. Backend Setup (Django API)

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r ../requirements.txt

# Run migrations
python manage.py migrate

# Run unit tests (12 tests)
python manage.py test core

# Start Django development server (Port 8000)
python manage.py runserver 8000
```

### 2. Frontend Setup (Vite + React UI)

```bash
# Navigate to frontend directory
cd frontend

# Install npm packages
npm install

# Start Vite dev server (Port 5173)
npm run dev
```

Open **http://localhost:5173** in your browser to interact with the real-time progress generator dashboard.

---

## Key Features

- **No-DB Event Processing**: Reads and normalizes activity directly from JSON/HTTP sources without DB event state.
- **Deduplication Engine**: Groups events by `(source, record_id)` and sorts by timestamp to preserve the latest state.
- **Strict Shift Window Filtering**: `[shift_start, shift_end)` — start inclusive, end exclusive.
- **4 Section Categorization**: Completed, In Progress, Blockers, Watch-list.
- **Carry-Forward Snapshot Support**: Surfacing open items from previous shifts (`previous_shift_snapshot.json`).
- **Config-Driven Sources (`sources.json`)**: Add file or HTTP remote API sources with zero code changes.
- **HTTP Timeout Hardening**: Gracefully skips unreachable HTTP remote APIs or malformed events without crashing.
- **Real-Time Progress Streaming (SSE)**: Pushes step-by-step progress to the React frontend.
- **Multiple Output Formats**: Generates `.docx` documents (with auto-summary paragraph) and Slack-formatted markdown text files.

---

## CLI Usage

```bash
cd backend

# Generate report using a test scenario (quiet / busy / messy)
python manage.py generate_report --scenario busy --output report.docx

# Generate report using an explicit UTC shift window
python manage.py generate_report \
  --shift-start "2024-01-15T07:00:00Z" \
  --shift-end   "2024-01-15T12:00:00Z" \
  --output report.docx
```

---

## REST API Endpoints

- `POST /api/generate-report/`: Generates `.docx` file attachment or Slack text summary (`"format": "slack"`).
- `POST /api/generate-report/stream/`: Server-Sent Events stream for real-time progress updates.
- `GET /api/health/`: Health check endpoint (`{"status": "ok"}`).

---

## Project Structure

```
├── backend/
│   ├── backend/            # Django configuration & settings
│   ├── core/
│   │   ├── data/           # Configured sources (sources.json, tickets, incidents, chat, snapshot)
│   │   ├── scenarios/      # Test scenarios (quiet, busy, messy)
│   │   ├── fetch_activity.py
│   │   ├── generator.py
│   │   ├── publisher.py
│   │   ├── http_source.py
│   │   ├── shared_utils.py
│   │   ├── views.py
│   │   ├── progress_stream.py
│   │   └── tests.py
│   └── manage.py
├── frontend/               # Vite + React frontend UI
├── REPORT.md               # Detailed evaluation report
└── requirements.txt
```
