import { useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import Layout from '../components/Layout'
import Header from '../components/Header'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function fmtDuration(startIso, endIso) {
  if (!startIso || !endIso) return '—'
  const ms = new Date(endIso) - new Date(startIso)
  if (ms < 0) return '—'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s`
}

function toDateStr(iso) {
  if (!iso) return ''
  return iso.slice(0, 10) // "YYYY-MM-DD"
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_STYLE = {
  approved:  'bg-green-900/50 text-green-400 border-green-800',
  escalated: 'bg-red-900/50 text-red-400 border-red-800',
  rejected:  'bg-orange-900/50 text-orange-400 border-orange-800',
  committed: 'bg-emerald-900/50 text-emerald-400 border-emerald-800',
  executing: 'bg-blue-900/50 text-blue-400 border-blue-800',
  reviewing: 'bg-yellow-900/50 text-yellow-400 border-yellow-800',
  planned:   'bg-gray-800 text-gray-400 border-gray-700',
}

function StatusBadge({ status }) {
  const cls = STATUS_STYLE[status] ?? 'bg-gray-800 text-gray-400 border-gray-700'
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${cls}`}>
      {status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Score chip
// ---------------------------------------------------------------------------

function ScoreChip({ score }) {
  if (score == null) return <span className="text-gray-600">—</span>
  const color = score >= 8 ? 'text-green-400' : score >= 6 ? 'text-yellow-400' : 'text-red-400'
  return <span className={`font-mono text-sm ${color}`}>{score}/10</span>
}

// ---------------------------------------------------------------------------
// Diff viewer (inline, compact)
// ---------------------------------------------------------------------------

function classifyLine(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'header'
  if (line.startsWith('@@'))  return 'hunk'
  if (line.startsWith('+'))  return 'add'
  if (line.startsWith('-'))  return 'del'
  return 'ctx'
}

const LINE_STYLE = {
  header: 'text-gray-500',
  hunk:   'text-purple-400 bg-purple-900/20',
  add:    'text-green-300 bg-green-900/25',
  del:    'text-red-300 bg-red-900/25',
  ctx:    'text-gray-400',
}

function DiffViewer({ diff }) {
  const [collapsed, setCollapsed] = useState(true)

  if (!diff || !diff.trim()) {
    return <p className="text-gray-600 text-xs">No diff available.</p>
  }

  const lines = diff.split('\n')
  const added   = lines.filter(l => l.startsWith('+') && !l.startsWith('+++')).length
  const removed = lines.filter(l => l.startsWith('-') && !l.startsWith('---')).length

  return (
    <div className="border border-gray-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setCollapsed(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-2.5 bg-gray-900/60 border-b border-gray-800 text-left hover:bg-gray-800/60 transition-colors"
      >
        <span className="text-sm font-medium text-gray-200 flex-1">Diff</span>
        <span className="text-xs text-green-400">+{added}</span>
        <span className="text-xs text-red-400 mr-2">−{removed}</span>
        <span className="text-gray-600 text-xs">{collapsed ? '▼' : '▲'}</span>
      </button>
      {!collapsed && (
        <div className="overflow-x-auto bg-gray-950 max-h-96 overflow-y-auto">
          <pre className="text-xs font-mono leading-5 p-0 m-0">
            {lines.map((line, i) => {
              const kind = classifyLine(line)
              return (
                <div key={i} className={`flex px-4 whitespace-pre ${LINE_STYLE[kind]}`}>
                  <span className="select-none text-gray-700 w-8 shrink-0 text-right mr-4">{i + 1}</span>
                  <span className="flex-1">{line || ' '}</span>
                </div>
              )
            })}
          </pre>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Severity badge
// ---------------------------------------------------------------------------

const SEV_STYLE = {
  critical: 'bg-red-900/60 text-red-400 border-red-800',
  warning:  'bg-yellow-900/60 text-yellow-400 border-yellow-800',
  info:     'bg-blue-900/60 text-blue-400 border-blue-800',
}

// ---------------------------------------------------------------------------
// Timeline — step node (colored circle)
// ---------------------------------------------------------------------------

const NODE_STYLE = {
  pass: 'bg-green-500 border-green-400 text-white',
  fail: 'bg-red-500  border-red-400  text-white',
  warn: 'bg-yellow-500 border-yellow-400 text-gray-900',
  skip: 'bg-gray-800 border-gray-600 text-gray-500',
}
const NODE_ICON = { pass: '✓', fail: '✕', warn: '!', skip: '—' }

function StepNode({ status }) {
  const cls = NODE_STYLE[status] ?? NODE_STYLE.skip
  return (
    <div className={`w-7 h-7 rounded-full border-2 flex items-center justify-center text-xs font-bold shrink-0 ${cls}`}>
      {NODE_ICON[status] ?? '—'}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Timeline — single step row (expandable)
// ---------------------------------------------------------------------------

function TimelineStep({ nodeStatus, label, meta, defaultOpen = true, isLast = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  const hasContent = Boolean(children)

  return (
    <div className="flex gap-4">
      {/* Left column: node + connector line */}
      <div className="flex flex-col items-center">
        <StepNode status={nodeStatus} />
        {!isLast && (
          <div className="w-px flex-1 bg-gray-800 my-1" style={{ minHeight: '1rem' }} />
        )}
      </div>

      {/* Right column: header + body */}
      <div className={`flex-1 min-w-0 ${isLast ? '' : 'pb-4'}`}>
        <button
          onClick={() => hasContent && setOpen(v => !v)}
          className={`flex items-center gap-2 w-full text-left ${hasContent ? 'group' : 'cursor-default'}`}
        >
          <span className="text-sm font-semibold text-gray-200">{label}</span>
          {meta && (
            <span className="text-xs text-gray-500 truncate">{meta}</span>
          )}
          {hasContent && (
            <span className="text-gray-600 text-xs ml-auto shrink-0">
              {open ? '▲' : '▼'}
            </span>
          )}
        </button>

        {hasContent && open && (
          <div className="mt-3 space-y-3">
            {children}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Timeline helpers
// ---------------------------------------------------------------------------

function diffStats(diff) {
  if (!diff) return { added: 0, removed: 0 }
  const lines = diff.split('\n')
  return {
    added:   lines.filter(l => l.startsWith('+') && !l.startsWith('+++')).length,
    removed: lines.filter(l => l.startsWith('-') && !l.startsWith('---')).length,
  }
}

function execNodeStatus(status) {
  if (['approved', 'committed'].includes(status)) return 'pass'
  if (['escalated', 'rejected'].includes(status)) return 'fail'
  return 'skip'
}

// ---------------------------------------------------------------------------
// Cycle detail modal — timeline view
// ---------------------------------------------------------------------------

function CycleDetailModal({ entry, onClose }) {
  if (!entry) return null

  const plan     = entry.plan     ?? null
  const review   = entry.review   ?? null
  const decision = entry.decision ?? null
  const diff     = entry.diff     ?? ''
  const { added, removed } = diffStats(diff)

  // Step node statuses
  const planStatus     = plan     ? 'pass' : 'skip'
  const reviewStatus   = review   ? (review.approved  ? 'pass' : 'fail') : 'skip'
  const decisionStatus = decision ? (decision.approved ? 'pass' : 'fail') : 'skip'
  const execStatus     = execNodeStatus(entry.status)

  // Plan meta
  const createCount = (plan?.files_to_create ?? []).length
  const modifyCount = (plan?.files_to_modify ?? []).length
  const stepsCount  = (plan?.steps ?? []).length
  const planMeta = plan
    ? [
        stepsCount  ? `${stepsCount} steps`   : null,
        createCount ? `+${createCount} new`   : null,
        modifyCount ? `~${modifyCount} edited` : null,
        plan.estimated_complexity ? `complexity: ${plan.estimated_complexity}` : null,
      ].filter(Boolean).join(' · ')
    : 'no data'

  // Review meta
  const issueCount = (review?.issues ?? []).length
  const reviewMeta = review
    ? `${review.score}/10${issueCount ? ` · ${issueCount} issue${issueCount > 1 ? 's' : ''}` : ''}`
    : 'no data'

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 backdrop-blur-sm overflow-y-auto py-8 px-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-gray-950 border border-gray-800 rounded-2xl w-full max-w-3xl shadow-2xl">

        {/* ── Modal header ── */}
        <div className="flex items-start gap-4 px-6 py-4 border-b border-gray-800">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-gray-100 leading-snug">
              {entry.task}
            </p>
            <div className="flex items-center gap-3 mt-1.5 flex-wrap">
              <StatusBadge status={entry.status} />
              <span className="text-xs text-gray-500">{fmtDate(entry.started_at)}</span>
              <span className="text-xs text-gray-600">
                {fmtDuration(entry.started_at, entry.finished_at)}
              </span>
              {entry.commit_hash && (
                <span className="text-xs font-mono text-indigo-400">
                  commit {entry.commit_hash.slice(0, 8)}
                </span>
              )}
              {entry.attempt > 1 && (
                <span className="text-xs text-yellow-600">
                  attempt #{entry.attempt}
                </span>
              )}
              {entry.plan_run_id && (
                <Link
                  to={`/plan/${entry.plan_run_id}`}
                  onClick={e => e.stopPropagation()}
                  title="View plan run"
                  className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-indigo-900/30 text-indigo-400 border border-indigo-800/40 hover:bg-indigo-900/50 transition-colors"
                >
                  <span>⊟</span>
                  <span>
                    {entry.plan_task_id ?? 'plan'}
                    {entry.plan_name ? ` — ${entry.plan_name}` : ''}
                  </span>
                </Link>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-600 hover:text-gray-300 text-xl leading-none transition-colors shrink-0 mt-0.5"
          >
            ✕
          </button>
        </div>

        {/* ── Timeline body ── */}
        <div className="px-6 py-6">

          {/* 1. Planning */}
          <TimelineStep nodeStatus={planStatus} label="Planning" meta={planMeta}>
            {plan && (
              <>
                {plan.description && (
                  <p className="text-sm text-gray-300 leading-relaxed">{plan.description}</p>
                )}

                {(plan.files_to_create ?? []).length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-1.5">Files to create</p>
                    <ul className="space-y-0.5">
                      {plan.files_to_create.map((f, i) => (
                        <li key={i} className="text-xs font-mono text-green-400">+ {f}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {(plan.files_to_modify ?? []).length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-1.5">Files to modify</p>
                    <ul className="space-y-0.5">
                      {plan.files_to_modify.map((f, i) => (
                        <li key={i} className="text-xs font-mono text-yellow-400">~ {f}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {(plan.steps ?? []).length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-1.5">Steps</p>
                    <ol className="space-y-1.5">
                      {plan.steps.map((s, i) => (
                        <li key={i} className="flex gap-2 text-sm text-gray-300">
                          <span className="text-indigo-400 font-mono shrink-0 w-5 text-right">{i + 1}.</span>
                          <span className="leading-relaxed">{s}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                {(plan.acceptance_criteria ?? []).length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-1.5">Acceptance criteria</p>
                    <ul className="space-y-1.5">
                      {plan.acceptance_criteria.map((c, i) => (
                        <li key={i} className="flex gap-2 text-sm text-gray-300">
                          <span className="text-green-400 shrink-0">✓</span>
                          <span>{c}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </TimelineStep>

          {/* 2. Critic */}
          <TimelineStep
            nodeStatus="skip"
            label="Critic loop"
            meta="details not persisted in logs"
            defaultOpen={false}
          />

          {/* 3. Execute */}
          <TimelineStep
            nodeStatus={execStatus}
            label="Execute"
            meta={diff ? `+${added} lines · −${removed} lines` : 'no diff available'}
          >
            <DiffViewer diff={diff} />
          </TimelineStep>

          {/* 4. Review */}
          <TimelineStep nodeStatus={reviewStatus} label="Review (Gemini)" meta={reviewMeta}>
            {review && (
              <>
                {/* Score bar */}
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        review.score >= 8 ? 'bg-green-500'
                        : review.score >= 6 ? 'bg-yellow-500'
                        : 'bg-red-500'
                      }`}
                      style={{ width: `${Math.round((review.score / 10) * 100)}%` }}
                    />
                  </div>
                  <span className={`text-sm font-semibold tabular-nums ${
                    review.score >= 8 ? 'text-green-400'
                    : review.score >= 6 ? 'text-yellow-400'
                    : 'text-red-400'
                  }`}>
                    {review.score}/10
                  </span>
                </div>

                {review.summary && (
                  <p className="text-sm text-gray-300 leading-relaxed">{review.summary}</p>
                )}

                {(review.issues ?? []).length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">
                      Issues ({review.issues.length})
                    </p>
                    <div className="space-y-2">
                      {review.issues.map((issue, i) => (
                        <div key={i} className="border border-gray-800 rounded-lg p-3 space-y-1.5">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`text-xs px-2 py-0.5 rounded-full border ${SEV_STYLE[issue.severity] ?? SEV_STYLE.info}`}>
                              {issue.severity}
                            </span>
                            {issue.file && (
                              <span className="text-xs font-mono text-gray-500">
                                {issue.file}{issue.line != null ? `:${issue.line}` : ''}
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-gray-300">{issue.description}</p>
                          {issue.suggestion && (
                            <p className="text-xs text-gray-500 italic">→ {issue.suggestion}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {(review.suggestions ?? []).length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Suggestions</p>
                    <ul className="space-y-1">
                      {review.suggestions.map((s, i) => (
                        <li key={i} className="flex gap-2 text-sm text-gray-400">
                          <span className="text-gray-600 shrink-0">→</span>
                          <span>{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </TimelineStep>

          {/* 5. Decision */}
          <TimelineStep
            nodeStatus={decisionStatus}
            label="Decision (Gemini)"
            meta={decision ? (decision.approved ? 'Coherent with plan' : 'Inconsistent with plan') : 'no data'}
            isLast
          >
            {decision && (
              <div className={`border rounded-xl p-4 space-y-3 ${
                decision.approved
                  ? 'bg-green-900/20 border-green-800'
                  : 'bg-red-900/20 border-red-800'
              }`}>
                <span className={`text-sm font-medium ${decision.approved ? 'text-green-400' : 'text-red-400'}`}>
                  {decision.approved ? 'Coherent with plan' : 'Inconsistent with plan'}
                </span>
                {decision.reasoning && (
                  <p className="text-sm text-gray-300 leading-relaxed">{decision.reasoning}</p>
                )}
                {(decision.inconsistencies ?? []).length > 0 && (
                  <ul className="space-y-1">
                    {decision.inconsistencies.map((inc, i) => (
                      <li key={i} className="text-xs text-red-400 flex gap-2">
                        <span className="shrink-0">✕</span>
                        <span>{inc}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </TimelineStep>

        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Filter bar
// ---------------------------------------------------------------------------

const STATUS_OPTIONS = ['', 'approved', 'escalated', 'rejected', 'committed', 'executing']

function FilterBar({ statusFilter, setStatusFilter, dateFrom, setDateFrom, dateTo, setDateTo, onClear }) {
  const hasFilters = statusFilter || dateFrom || dateTo
  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* Status */}
      <select
        value={statusFilter}
        onChange={e => setStatusFilter(e.target.value)}
        className="bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-600"
      >
        <option value="">All statuses</option>
        {STATUS_OPTIONS.filter(Boolean).map(s => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>

      {/* Date from */}
      <input
        type="date"
        value={dateFrom}
        onChange={e => setDateFrom(e.target.value)}
        className="bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-600"
      />

      <span className="text-gray-600 text-xs">to</span>

      {/* Date to */}
      <input
        type="date"
        value={dateTo}
        onChange={e => setDateTo(e.target.value)}
        className="bg-gray-900 border border-gray-700 text-gray-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-600"
      />

      {hasFilters && (
        <button
          onClick={onClear}
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-1.5 border border-gray-700 rounded-lg"
        >
          Clear
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// History table
// ---------------------------------------------------------------------------

const PAGE_SIZE = 15

function HistoryTable({ entries, onRowClick }) {
  if (entries.length === 0) {
    return (
      <div className="text-center py-16 text-gray-600">
        <p className="text-sm">No runs match the current filters.</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
            <th className="text-left pb-3 pr-4 font-medium">Task</th>
            <th className="text-left pb-3 pr-4 font-medium">Status</th>
            <th className="text-left pb-3 pr-4 font-medium">Date</th>
            <th className="text-left pb-3 pr-4 font-medium">Duration</th>
            <th className="text-left pb-3 pr-4 font-medium">Score</th>
            <th className="text-left pb-3 pr-4 font-medium">Attempt</th>
            <th className="text-left pb-3 pr-4 font-medium">Commit</th>
            <th className="text-left pb-3 font-medium">Plan</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, i) => (
            <tr
              key={i}
              onClick={() => onRowClick(entry)}
              className="border-b border-gray-800/50 hover:bg-gray-800/30 cursor-pointer transition-colors group"
            >
              {/* Task */}
              <td className="py-3 pr-4 max-w-xs">
                <span
                  className="text-gray-200 group-hover:text-white transition-colors line-clamp-2 leading-snug"
                  title={entry.task}
                >
                  {entry.task}
                </span>
              </td>

              {/* Status */}
              <td className="py-3 pr-4">
                <StatusBadge status={entry.status} />
              </td>

              {/* Date */}
              <td className="py-3 pr-4 text-gray-400 whitespace-nowrap text-xs">
                {fmtDate(entry.started_at)}
              </td>

              {/* Duration */}
              <td className="py-3 pr-4 text-gray-500 text-xs whitespace-nowrap">
                {fmtDuration(entry.started_at, entry.finished_at)}
              </td>

              {/* Score */}
              <td className="py-3 pr-4">
                <ScoreChip score={entry.review?.score ?? null} />
              </td>

              {/* Attempt */}
              <td className="py-3 pr-4 text-gray-500 text-xs">
                #{entry.attempt ?? 1}
              </td>

              {/* Commit */}
              <td className="py-3 pr-4 text-xs font-mono text-indigo-400">
                {entry.commit_hash ? entry.commit_hash.slice(0, 8) : '—'}
              </td>

              {/* Plan run link — only shown when cycle belongs to a plan run */}
              <td className="py-3 text-xs">
                {entry.plan_run_id ? (
                  <Link
                    to={`/plan/${entry.plan_run_id}`}
                    onClick={e => e.stopPropagation()}
                    title={`Task ${entry.plan_task_id ?? '?'}${entry.plan_name ? ` — ${entry.plan_name}` : ''}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-900/30 text-indigo-400 border border-indigo-800/40 hover:bg-indigo-900/50 transition-colors whitespace-nowrap"
                  >
                    <span>⊟</span>
                    <span>{entry.plan_task_id ?? 'plan'}</span>
                  </Link>
                ) : (
                  <span className="text-gray-700">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

function Pagination({ page, totalPages, onPrev, onNext }) {
  if (totalPages <= 1) return null
  return (
    <div className="flex items-center justify-between pt-4 border-t border-gray-800">
      <button
        onClick={onPrev}
        disabled={page === 0}
        className="text-xs px-3 py-1.5 rounded-lg border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        ← Prev
      </button>
      <span className="text-xs text-gray-500">
        Page {page + 1} of {totalPages}
      </span>
      <button
        onClick={onNext}
        disabled={page >= totalPages - 1}
        className="text-xs px-3 py-1.5 rounded-lg border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        Next →
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// History page
// ---------------------------------------------------------------------------

export default function History() {
  const [entries, setEntries]     = useState([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)

  // Filters
  const [statusFilter, setStatusFilter] = useState('')
  const [dateFrom, setDateFrom]         = useState('')
  const [dateTo, setDateTo]             = useState('')

  // Pagination
  const [page, setPage] = useState(0)

  // Detail modal
  const [selected, setSelected] = useState(null)

  // Load all entries once
  useEffect(() => {
    setLoading(true)
    api.get('/api/history?limit=0')
      .then(data => {
        setEntries(data ?? [])
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  // Apply filters
  const filtered = useMemo(() => {
    return entries.filter(e => {
      if (statusFilter && e.status !== statusFilter) return false
      if (dateFrom && toDateStr(e.started_at) < dateFrom) return false
      if (dateTo   && toDateStr(e.started_at) > dateTo)   return false
      return true
    })
  }, [entries, statusFilter, dateFrom, dateTo])

  // Reset page when filters change
  useEffect(() => { setPage(0) }, [statusFilter, dateFrom, dateTo])

  const totalPages  = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageEntries = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  function clearFilters() {
    setStatusFilter('')
    setDateFrom('')
    setDateTo('')
  }

  return (
    <Layout>
      <Header title="History" />

      <main className="flex-1 p-6 max-w-6xl w-full mx-auto space-y-5">

        {/* Filter bar */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <FilterBar
            statusFilter={statusFilter} setStatusFilter={setStatusFilter}
            dateFrom={dateFrom}         setDateFrom={setDateFrom}
            dateTo={dateTo}             setDateTo={setDateTo}
            onClear={clearFilters}
          />
          {!loading && (
            <span className="text-xs text-gray-600">
              {filtered.length} / {entries.length} runs
            </span>
          )}
        </div>

        {/* Table card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl px-6 py-5">
          {loading && (
            <p className="text-gray-500 text-sm py-8 text-center">Loading history…</p>
          )}
          {!loading && error && (
            <p className="text-red-400 text-sm py-8 text-center">{error}</p>
          )}
          {!loading && !error && (
            <>
              <HistoryTable entries={pageEntries} onRowClick={setSelected} />
              <Pagination
                page={page}
                totalPages={totalPages}
                onPrev={() => setPage(p => Math.max(0, p - 1))}
                onNext={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              />
            </>
          )}
        </div>

      </main>

      {/* Detail modal */}
      {selected && (
        <CycleDetailModal entry={selected} onClose={() => setSelected(null)} />
      )}
    </Layout>
  )
}
