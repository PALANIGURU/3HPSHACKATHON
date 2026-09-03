import { useState, useRef, useCallback, useEffect } from 'react'
import {
  FiZap,
  FiRadio,
  FiShuffle,
  FiClipboard,
  FiFileText,
  FiPackage,
  FiCheckCircle,
  FiAlertCircle,
  FiClock,
  FiDownload,
  FiSliders,
  FiActivity,
  FiTerminal,
  FiMoon,
  FiTrendingUp,
  FiCompass,
  FiCheckSquare,
  FiRefreshCw,
  FiEye,
  FiLayers
} from 'react-icons/fi'

/* ─── Step Icons Configuration ────────────────────────────────────────── */
const STEPS_CONFIG = [
  { id: 'validate', label: 'Validating parameters',     icon: FiZap },
  { id: 'fetch',    label: 'Fetching activity data',    icon: FiRadio },
  { id: 'dedup',    label: 'Deduplicating events',      icon: FiShuffle },
  { id: 'section',  label: 'Applying sectioning rules', icon: FiClipboard },
  { id: 'render',   label: 'Rendering .docx report',   icon: FiFileText },
  { id: 'finalise', label: 'Finalising and packaging',  icon: FiPackage },
]

const SCENARIOS = [
  { id: '',       icon: FiSliders,     name: 'Live Data', desc: 'Read from sources.json' },
  { id: 'quiet',  icon: FiMoon,        name: 'Quiet',     desc: 'Minimal activity' },
  { id: 'busy',   icon: FiTrendingUp,  name: 'Busy',      desc: 'All 4 sections' },
  { id: 'messy',  icon: FiCompass,     name: 'Messy',     desc: 'Duplicates + chaos' },
]

const DEFAULT_START = '2024-01-15T07:00:00Z'
const DEFAULT_END   = '2024-01-15T12:00:00Z'

/* ─── Helper: download base64 file ────────────────────────────────────── */
function downloadB64(b64, filename) {
  const bytes = atob(b64)
  const arr   = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const blob  = new Blob([arr], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
  const url   = URL.createObjectURL(blob)
  const a     = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

/* ─── Sub-components ───────────────────────────────────────────────────── */
function StepStatusIcon({ status }) {
  if (status === 'running') return <FiRefreshCw className="spin-icon" />
  if (status === 'done')    return <FiCheckCircle />
  if (status === 'error')   return <FiAlertCircle />
  return <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--text-muted)' }} />
}

function CountPills({ counts }) {
  const labels = {
    completed:   { label: 'Completed',   icon: FiCheckSquare },
    in_progress: { label: 'In Progress', icon: FiRefreshCw },
    blockers:    { label: 'Blockers',    icon: FiAlertCircle },
    watch_list:  { label: 'Watch-list',  icon: FiEye },
    still_open:  { label: 'Carried Over', icon: FiLayers },
  }
  return (
    <div className="counts-row">
      {Object.entries(labels).map(([k, { label, icon: Icon }]) => counts[k] > 0 && (
        <span key={k} className="count-pill">
          <Icon style={{ fontSize: 12 }} /> {label}: {counts[k]}
        </span>
      ))}
    </div>
  )
}

function StatsBar({ counts }) {
  const cells = [
    { k: 'completed',   label: 'Completed',   icon: FiCheckSquare },
    { k: 'in_progress', label: 'In Progress',  icon: FiRefreshCw },
    { k: 'blockers',    label: 'Blockers',     icon: FiAlertCircle },
    { k: 'watch_list',  label: 'Watch-list',   icon: FiEye },
    { k: 'still_open',  label: 'Carried Over', icon: FiLayers },
  ]
  const total = Object.entries(counts).reduce((a, [k, v]) => k !== 'still_open' ? a + v : a, 0)
  return (
    <div className="stats-bar">
      <div className="stat-cell">
        <div className="stat-value">{total}</div>
        <div className="stat-label"><FiActivity /> Total Items</div>
      </div>
      {cells.map(({ k, label, icon: Icon }) => (
        <div key={k} className="stat-cell">
          <div className="stat-value">{counts[k] ?? 0}</div>
          <div className="stat-label"><Icon /> {label}</div>
        </div>
      ))}
    </div>
  )
}

/* ─── Main App ─────────────────────────────────────────────────────────── */
export default function App() {
  const [shiftStart, setShiftStart] = useState(DEFAULT_START)
  const [shiftEnd,   setShiftEnd]   = useState(DEFAULT_END)
  const [scenario,   setScenario]   = useState('busy')
  const [running,    setRunning]    = useState(false)
  const [stepStates, setStepStates] = useState({})
  const [pct,        setPct]        = useState(0)
  const [logLines,   setLogLines]   = useState([])
  const [result,     setResult]     = useState(null)
  const [backendOk,  setBackendOk]  = useState(null)

  const logRef = useRef(null)

  /* Health check */
  useEffect(() => {
    setBackendOk(null)
    fetch('/api/health/')
      .then(r => r.ok ? setBackendOk(true) : setBackendOk(false))
      .catch(() => setBackendOk(false))
  }, [])

  /* Auto-scroll log */
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logLines])

  const addLog = useCallback((msg, type = 'info') => {
    const ts = new Date().toLocaleTimeString('en-GB', { hour12: false })
    setLogLines(prev => [...prev.slice(-80), { ts, msg, type }])
  }, [])

  const reset = useCallback(() => {
    setStepStates({})
    setPct(0)
    setResult(null)
    setLogLines([])
  }, [])

  const handleGenerate = useCallback(async () => {
    if (running) return
    reset()
    setRunning(true)
    addLog('Starting report generation stream...', 'info')

    const body = { shift_start: shiftStart, shift_end: shiftEnd }
    if (scenario) body.scenario = scenario

    try {
      const response = await fetch('/api/generate-report/stream/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        const text = await response.text()
        addLog(`Server error ${response.status}: ${text}`, 'error')
        setRunning(false)
        return
      }

      const reader  = response.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            const { step, status, message, pct: p, ts, counts, file_b64, filename, summary } = evt

            setStepStates(prev => ({
              ...prev,
              [step]: { status, message, ts: ts || '' },
            }))
            if (p !== undefined) setPct(p)

            addLog(`[${step}] ${message}`, status === 'error' ? 'error' : status === 'done' ? 'success' : 'info')

            if (file_b64 && filename) {
              setResult({ file_b64, filename, summary })
              addLog(`Report ready: ${filename}`, 'success')
            }

            if (status === 'error') {
              addLog('Generation stopped due to error.', 'error')
              setRunning(false)
              return
            }
          } catch (e) {
            /* ignore unparseable lines */
          }
        }
      }
    } catch (err) {
      addLog(`Connection error: ${err.message}`, 'error')
    } finally {
      setRunning(false)
    }
  }, [running, shiftStart, shiftEnd, scenario, reset, addLog])

  const finalCounts = (() => {
    if (result?.summary?.counts) return result.summary.counts
    return { completed: 0, in_progress: 0, blockers: 0, watch_list: 0 }
  })()

  const hasResult   = !!result
  const hasError    = Object.values(stepStates).some(s => s.status === 'error')
  const overallDone = pct === 100 && !hasError

  const stepsDisplay = STEPS_CONFIG.map(sc => {
    const s = stepStates[sc.id]
    return {
      ...sc,
      status:  s?.status || 'idle',
      message: s?.message || '',
      ts:      s?.ts || '',
      counts:  sc.id === 'section' && s?.status === 'done' ? finalCounts : null,
    }
  })

  return (
    <div className="app">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="header">
        <div className="header-logo">3H</div>
        <div>
          <div className="header-title">Shift Handover Generator</div>
          <div className="header-sub">Liquid Glass Monochrome Edition</div>
        </div>
        <div className="header-badge">
          <span
            className={`status-dot ${
              backendOk === null ? 'checking' : backendOk ? 'online' : 'offline'
            }`}
          />
          {backendOk === null ? 'Connecting...' : backendOk ? 'Backend Online' : 'Backend Offline'}
        </div>
      </header>

      <main className="main">
        {/* ── Hero ───────────────────────────────────────────────────────── */}
        <section className="hero">
          <div className="hero-tag">
            <FiActivity /> Real-Time Engine
          </div>
          <h1>Shift Handover Report</h1>
          <p>
            Generate reproducible .docx shift handover reports with real-time liquid progress updates and strict boundary window enforcement.
          </p>
        </section>

        {/* ── Config card ─────────────────────────────────────────────────── */}
        <div className="card">
          <div className="card-title">
            <FiSliders className="card-title-icon" />
            Configuration & Shift Window
          </div>

          <div className="form-grid">
            <div className="field">
              <label htmlFor="shift-start">Shift Start (UTC)</label>
              <input
                id="shift-start"
                type="text"
                value={shiftStart}
                onChange={e => setShiftStart(e.target.value)}
                placeholder="2024-01-15T07:00:00Z"
                disabled={running}
              />
            </div>
            <div className="field">
              <label htmlFor="shift-end">Shift End (UTC)</label>
              <input
                id="shift-end"
                type="text"
                value={shiftEnd}
                onChange={e => setShiftEnd(e.target.value)}
                placeholder="2024-01-15T12:00:00Z"
                disabled={running}
              />
            </div>
            <div className="field form-grid-full">
              <label>Data Scenario / Source</label>
              <div className="scenario-grid">
                {SCENARIOS.map(sc => {
                  const Icon = sc.icon
                  return (
                    <div
                      key={sc.id}
                      id={`scenario-${sc.id || 'live'}`}
                      className={`scenario-card ${scenario === sc.id ? 'active' : ''}`}
                      onClick={() => !running && setScenario(sc.id)}
                    >
                      <Icon className="scenario-icon" />
                      <div className="scenario-name">{sc.name}</div>
                      <div className="scenario-desc">{sc.desc}</div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          <button
            id="btn-generate"
            className="btn-generate"
            onClick={handleGenerate}
            disabled={running || backendOk === false}
            style={{ marginTop: 24 }}
          >
            {running ? (
              <><FiRefreshCw className="spin-icon" /> Generating… {pct}%</>
            ) : overallDone ? (
              <><FiCheckCircle /> Generate Again</>
            ) : (
              <><FiZap /> Generate Report</>
            )}
          </button>
        </div>

        {/* ── Progress Card ───────────────────────────────────────────────── */}
        {Object.keys(stepStates).length > 0 && (
          <div className="card">
            <div className="card-title">
              <FiActivity className="card-title-icon" />
              Live Liquid Stream Progress
              {overallDone && (
                <span style={{ marginLeft: 'auto', fontSize: 11, color: '#ffffff', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <FiCheckCircle /> Complete
                </span>
              )}
            </div>

            <div className="progress-panel">
              <div className="progress-bar-wrap">
                <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
              </div>

              {stepsDisplay.map(step => {
                const StepIcon = step.icon
                return (
                  <div key={step.id} className={`step-row ${step.status}`}>
                    <div className={`step-icon ${step.status}`}>
                      <StepStatusIcon status={step.status} />
                    </div>
                    <div className="step-body">
                      <div className="step-label">
                        <StepIcon /> {step.label}
                        {step.ts && <span className="step-ts"><FiClock /> {step.ts}</span>}
                      </div>
                      {step.message && (
                        <div className="step-message">{step.message}</div>
                      )}
                      {step.counts && step.status === 'done' && (
                        <CountPills counts={step.counts} />
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {hasResult && (
              <button
                id="btn-download"
                className="btn-download"
                onClick={() => downloadB64(result.file_b64, result.filename)}
              >
                <FiDownload /> Download {result.filename}
              </button>
            )}
          </div>
        )}

        {/* ── Stats Bar ───────────────────────────────────────────────────── */}
        {result?.summary?.counts && (
          <StatsBar counts={result.summary.counts} />
        )}

        {/* ── Activity Log ───────────────────────────────────────────────── */}
        {logLines.length > 0 && (
          <div className="card">
            <div className="card-title">
              <FiTerminal className="card-title-icon" />
              Real-Time Activity Log
            </div>
            <div className="activity-log" ref={logRef}>
              {logLines.map((l, i) => (
                <div key={i} className="log-line">
                  <span className="log-ts">{l.ts}</span>
                  <span className={`log-msg ${l.type}`}>{l.msg}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
