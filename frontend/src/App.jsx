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
  FiLayers,
  FiUserCheck,
  FiUser,
  FiSend,
  FiCheck,
  FiX,
  FiTrello,
  FiLock,
  FiUnlock
} from 'react-icons/fi'

const STEPS_CONFIG = [
  { id: 'validate', label: 'Validating parameters & approval status', icon: FiZap },
  { id: 'fetch',    label: 'Fetching activity data & Jira worklogs', icon: FiRadio },
  { id: 'dedup',    label: 'Deduplicating events',                    icon: FiShuffle },
  { id: 'section',  label: 'Applying sectioning rules',               icon: FiClipboard },
  { id: 'render',   label: 'Rendering .docx report',                 icon: FiFileText },
  { id: 'finalise', label: 'Finalising and packaging',                icon: FiPackage },
]

const SCENARIOS = [
  { id: '',       icon: FiSliders,    name: 'Live Data', desc: 'Read from sources.json & Jira' },
  { id: 'quiet',  icon: FiMoon,       name: 'Quiet',     desc: 'Minimal activity' },
  { id: 'busy',   icon: FiTrendingUp, name: 'Busy',      desc: 'All 4 sections' },
  { id: 'messy',  icon: FiCompass,    name: 'Messy',     desc: 'Duplicates + chaos' },
]

const DEFAULT_START = '2024-01-15T07:00:00Z'
const DEFAULT_END   = '2024-01-15T12:00:00Z'

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

export default function App() {
  const [role,       setRole]       = useState('staff')
  const [shiftStart, setShiftStart] = useState(DEFAULT_START)
  const [shiftEnd,   setShiftEnd]   = useState(DEFAULT_END)
  const [scenario,   setScenario]   = useState('busy')
  const [userName,   setUserName]   = useState('John (Shift Engineer)')
  const [notes,      setNotes]      = useState('EU 500 error fix deployed; database pool connection resolved.')
  
  const [running,    setRunning]    = useState(false)
  const [stepStates, setStepStates] = useState({})
  const [pct,        setPct]        = useState(0)
  const [logLines,   setLogLines]   = useState([])
  const [result,     setResult]     = useState(null)
  const [backendOk,  setBackendOk]  = useState(null)
  
  const [approvals,  setApprovals]  = useState([])
  const [jiraEvents, setJiraEvents] = useState([])
  const [selectedReq, setSelectedReq] = useState(null)

  const logRef = useRef(null)

  const fetchApprovals = useCallback(async () => {
    try {
      const res = await fetch('/api/approvals/list/')
      if (res.ok) {
        const data = await res.json()
        setApprovals(data.requests || [])
      }
    } catch (e) {}
  }, [])

  const fetchJira = useCallback(async () => {
    try {
      const res = await fetch('/api/jira/events/')
      if (res.ok) {
        const data = await res.json()
        setJiraEvents(data.jira_events || [])
      }
    } catch (e) {}
  }, [])

  useEffect(() => {
    setBackendOk(null)
    fetch('/api/health/')
      .then(r => r.ok ? setBackendOk(true) : setBackendOk(false))
      .catch(() => setBackendOk(false))

    fetchApprovals()
    fetchJira()
  }, [fetchApprovals, fetchJira])

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

  // Staff action: Submit handover for approval
  const handleStaffSubmit = async () => {
    try {
      const res = await fetch('/api/approvals/submit/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          shift_start: shiftStart,
          shift_end: shiftEnd,
          submitted_by: userName,
          notes,
          scenario,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        addLog(`Handover submitted for approval! Request ID: ${data.request.id}`, 'success')
        fetchApprovals()
      } else {
        addLog('Failed to submit handover request.', 'error')
      }
    } catch (err) {
      addLog(`Submit error: ${err.message}`, 'error')
    }
  }

  // Trigger report generation stream for an approved request
  const startGenerationStream = useCallback(async (reqToUse) => {
    if (running) return
    reset()
    setRunning(true)
    addLog(`Starting approved report generation for ${reqToUse.id}...`, 'info')

    const body = {
      shift_start: reqToUse.shift_start || shiftStart,
      shift_end: reqToUse.shift_end || shiftEnd,
      request_id: reqToUse.id,
    }
    if (reqToUse.scenario) body.scenario = reqToUse.scenario

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
              setResult({ file_b64, filename, summary, slack_summary: evt.slack_summary })
              addLog(`Report ready: ${filename}`, 'success')
              downloadB64(file_b64, filename)
            }

            if (status === 'error') {
              addLog('Generation stopped due to error.', 'error')
              setRunning(false)
              return
            }
          } catch (e) {}
        }
      }
    } catch (err) {
      addLog(`Connection error: ${err.message}`, 'error')
    } finally {
      setRunning(false)
    }
  }, [running, shiftStart, shiftEnd, reset, addLog])

  // Manager action: Approve or reject
  const handleManagerReview = async (reqId, decision) => {
    try {
      const res = await fetch('/api/approvals/review/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: reqId,
          manager_name: 'Manager (Jane Doe)',
          decision,
          reason: decision === 'reject' ? 'Needs additional details on database pool status.' : '',
        }),
      })
      if (res.ok) {
        const data = await res.json()
        const updatedReq = data.request
        addLog(`Request ${reqId} ${decision.toUpperCase()}ED by Manager`, 'success')
        fetchApprovals()

        // If approved, trigger report generation immediately!
        if (decision === 'approve') {
          setSelectedReq(updatedReq)
          startGenerationStream(updatedReq)
        }
      }
    } catch (err) {
      addLog(`Review error: ${err.message}`, 'error')
    }
  }

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
          <div className="header-sub">Role-Based Approval & Real-Life Jira Tracker</div>
        </div>

        {/* Role Selector */}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <div className="scenario-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 6 }}>
            <button
              className={`count-pill ${role === 'staff' ? 'active' : ''}`}
              style={{ padding: '6px 14px', cursor: 'pointer', background: role === 'staff' ? '#ffffff' : 'transparent', color: role === 'staff' ? '#000000' : '#ffffff' }}
              onClick={() => setRole('staff')}
            >
              <FiUser /> Staff Mode
            </button>
            <button
              className={`count-pill ${role === 'manager' ? 'active' : ''}`}
              style={{ padding: '6px 14px', cursor: 'pointer', background: role === 'manager' ? '#ffffff' : 'transparent', color: role === 'manager' ? '#000000' : '#ffffff' }}
              onClick={() => setRole('manager')}
            >
              <FiUserCheck /> Manager Mode
            </button>
          </div>
          <div className="header-badge">
            <span className={`status-dot ${backendOk === null ? 'checking' : backendOk ? 'online' : 'offline'}`} />
            {backendOk ? 'Online' : 'Offline'}
          </div>
        </div>
      </header>

      <main className="main">
        <section className="hero">
          <div className="hero-tag">
            {role === 'staff' ? <><FiUser /> Staff Workspace</> : <><FiUserCheck /> Manager Review Portal</>}
          </div>
          <h1>{role === 'staff' ? 'Draft & Submit Handover' : 'Manager Handover Approval Portal'}</h1>
          <p>
            {role === 'staff'
              ? 'Staff members draft shift handover notes, track live Jira worklogs, and submit handovers to Manager for approval.'
              : 'Managers review submitted shift handovers, approve or reject, and trigger final .docx report exports.'}
          </p>
        </section>

        {/* ── Real-Life Jira Tracker Box ──────────────────────────────────── */}
        <div className="card">
          <div className="card-title">
            <FiTrello className="card-title-icon" /> Real-Life Jira Issue & Worklog Tracker
          </div>
          <div className="activity-log" style={{ maxHeight: 130 }}>
            {jiraEvents.map((j, idx) => (
              <div key={idx} className="log-line" style={{ justifyContent: 'space-between' }}>
                <span className="log-msg info"><strong>[{j.record_id}]</strong> {j.summary}</span>
                <span className="count-pill" style={{ fontSize: 10, padding: '2px 8px' }}>{j.status}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Approval Requests List for Manager / Staff ─────────────────── */}
        <div className="card">
          <div className="card-title">
            <FiUserCheck className="card-title-icon" /> Shift Handover Approval Requests
          </div>

          {approvals.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>No approval requests submitted yet.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {approvals.map(req => (
                <div
                  key={req.id}
                  style={{
                    padding: 14,
                    background: selectedReq?.id === req.id ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.02)',
                    border: '1px solid var(--glass-border)',
                    borderRadius: 'var(--radius-md)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
                      {req.status === 'approved' ? <FiUnlock style={{ color: '#ffffff' }} /> : <FiLock style={{ color: 'var(--text-muted)' }} />}
                      {req.id} — Submitted by {req.submitted_by}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
                      Window: {req.shift_start} → {req.shift_end} | Notes: {req.notes || 'None'}
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span className="count-pill" style={{ textTransform: 'uppercase', fontSize: 10 }}>
                      {req.status}
                    </span>

                    {role === 'manager' && req.status === 'pending_approval' && (
                      <>
                        <button
                          className="btn-download"
                          style={{ margin: 0, padding: '6px 12px', fontSize: 12 }}
                          onClick={() => handleManagerReview(req.id, 'approve')}
                        >
                          <FiCheck /> Approve & Generate
                        </button>
                        <button
                          className="btn-download"
                          style={{ margin: 0, padding: '6px 12px', fontSize: 12, background: 'rgba(255,255,255,0.05)' }}
                          onClick={() => handleManagerReview(req.id, 'reject')}
                        >
                          <FiX /> Reject
                        </button>
                      </>
                    )}

                    {req.status === 'approved' && (
                      <button
                        className="btn-download"
                        style={{ margin: 0, padding: '6px 14px', fontSize: 12, background: '#ffffff', color: '#000000', fontWeight: 800 }}
                        onClick={() => {
                          setSelectedReq(req)
                          startGenerationStream(req)
                        }}
                      >
                        <FiDownload /> Generate & Download Approved Report
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Form & Action Card ─────────────────────────────────────────── */}
        <div className="card">
          <div className="card-title">
            <FiSliders className="card-title-icon" />
            {role === 'staff' ? 'Draft Handover & Submit to Manager' : 'Generate Approved Handover Document'}
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

            {role === 'staff' && (
              <>
                <div className="field">
                  <label>Staff Member Name</label>
                  <input type="text" value={userName} onChange={e => setUserName(e.target.value)} />
                </div>
                <div className="field">
                  <label>Shift Handover Notes / Summary</label>
                  <input type="text" value={notes} onChange={e => setNotes(e.target.value)} />
                </div>
              </>
            )}

            <div className="field form-grid-full">
              <label>Data Scenario / Source</label>
              <div className="scenario-grid">
                {SCENARIOS.map(sc => {
                  const Icon = sc.icon
                  return (
                    <div
                      key={sc.id}
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

          {role === 'staff' ? (
            <button
              className="btn-generate"
              onClick={handleStaffSubmit}
              disabled={running}
              style={{ marginTop: 24 }}
            >
              <FiSend /> Submit Handover for Manager Approval
            </button>
          ) : (
            <button
              id="btn-generate"
              className="btn-generate"
              onClick={() => {
                const approvedReq = approvals.find(a => a.status === 'approved')
                if (approvedReq) {
                  setSelectedReq(approvedReq)
                  startGenerationStream(approvedReq)
                } else {
                  addLog('No Manager-approved handover request available yet.', 'error')
                }
              }}
              disabled={running || backendOk === false || !approvals.some(a => a.status === 'approved')}
              style={{ marginTop: 24 }}
            >
              {running ? (
                <><FiRefreshCw className="spin-icon" /> Generating Approved Report… {pct}%</>
              ) : overallDone ? (
                <><FiCheckCircle /> Generate Again</>
              ) : (
                <><FiZap /> Generate Approved .docx Report</>
              )}
            </button>
          )}
        </div>

        {/* ── Progress Card ───────────────────────────────────────────────── */}
        {Object.keys(stepStates).length > 0 && (
          <div className="card">
            <div className="card-title">
              <FiActivity className="card-title-icon" />
              Live Stream Progress
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
                      {step.message && <div className="step-message">{step.message}</div>}
                      {step.counts && step.status === 'done' && <CountPills counts={step.counts} />}
                    </div>
                  </div>
                )
              })}
            </div>

            {hasResult && (
              <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'flex', gap: 10 }}>
                  <button
                    id="btn-download"
                    className="btn-download"
                    style={{ flex: 1, marginTop: 0 }}
                    onClick={() => downloadB64(result.file_b64, result.filename)}
                  >
                    <FiDownload /> Download {result.filename}
                  </button>

                  {result.slack_summary && (
                    <button
                      className="btn-download"
                      style={{ margin: 0, padding: '12px 20px', background: 'rgba(255,255,255,0.06)', border: '1px solid var(--glass-border-hi)' }}
                      onClick={() => {
                        navigator.clipboard.writeText(result.slack_summary)
                        addLog('Slack summary copied to clipboard!', 'success')
                      }}
                    >
                      <FiFileText /> Copy Slack Summary
                    </button>
                  )}
                </div>

                {result.slack_summary && (
                  <div className="activity-log" style={{ maxHeight: 180, background: 'rgba(0,0,0,0.8)', border: '1px solid var(--glass-border)' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <FiFileText /> SLACK FORMATTED SUMMARY PREVIEW
                    </div>
                    <pre style={{ fontFamily: 'var(--font-mono)', fontSize: 11, whiteSpace: 'pre-wrap', color: '#ffffff', margin: 0 }}>
                      {result.slack_summary}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Stats Bar ───────────────────────────────────────────────────── */}
        {result?.summary?.counts && <StatsBar counts={result.summary.counts} />}

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
