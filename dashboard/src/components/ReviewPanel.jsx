import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

// ---------------------------------------------------------------------------
// Diff viewer
// ---------------------------------------------------------------------------

function classifyLine(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'header'
  if (line.startsWith('@@'))  return 'hunk'
  if (line.startsWith('+'))   return 'add'
  if (line.startsWith('-'))   return 'del'
  return 'ctx'
}

const LINE_STYLE = {
  header: 'text-gray-500 bg-transparent select-none',
  hunk:   'text-purple-400 bg-purple-900/20',
  add:    'text-green-300 bg-green-900/25',
  del:    'text-red-300 bg-red-900/25',
  ctx:    'text-gray-400 bg-transparent',
}

function DiffViewer({ diff }) {
  const [collapsed, setCollapsed] = useState(false)

  if (!diff || !diff.trim()) {
    return (
      <p className="text-gray-600 text-xs px-4 py-3">No diff available.</p>
    )
  }

  const lines = diff.split('\n')
  // Count stats
  const added   = lines.filter(l => l.startsWith('+') && !l.startsWith('+++')).length
  const removed = lines.filter(l => l.startsWith('-') && !l.startsWith('---')).length

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setCollapsed(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 border-b border-gray-800 text-left hover:bg-gray-800/40 transition-colors"
      >
        <span className="text-sm font-medium text-gray-200 flex-1">Diff</span>
        <span className="text-xs text-green-400">+{added}</span>
        <span className="text-xs text-red-400 mr-2">−{removed}</span>
        <span className="text-gray-600 text-xs">{collapsed ? '▼' : '▲'}</span>
      </button>

      {/* Lines */}
      {!collapsed && (
        <div className="overflow-x-auto">
          <pre className="text-xs font-mono leading-5 p-0 m-0">
            {lines.map((line, i) => {
              const kind = classifyLine(line)
              return (
                <div
                  key={i}
                  className={`flex px-4 whitespace-pre ${LINE_STYLE[kind]}`}
                >
                  <span className="select-none text-gray-700 w-8 shrink-0 text-right mr-4 leading-5">
                    {kind !== 'header' && kind !== 'hunk' ? i + 1 : ''}
                  </span>
                  <span className="flex-1 overflow-x-visible">{line || ' '}</span>
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
// Review score gauge
// ---------------------------------------------------------------------------

function ScoreGauge({ score }) {
  const pct   = Math.round((score / 10) * 100)
  const color = score >= 8 ? 'bg-green-500'
              : score >= 6 ? 'bg-yellow-500'
              : 'bg-red-500'
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-sm font-semibold tabular-nums ${score >= 8 ? 'text-green-400' : score >= 6 ? 'text-yellow-400' : 'text-red-400'}`}>
        {score}/10
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Issue list
// ---------------------------------------------------------------------------

const SEVERITY_STYLE = {
  critical: { badge: 'bg-red-900/60 text-red-400 border-red-800',    dot: 'bg-red-500'    },
  warning:  { badge: 'bg-yellow-900/60 text-yellow-400 border-yellow-800', dot: 'bg-yellow-500' },
  info:     { badge: 'bg-blue-900/60 text-blue-400 border-blue-800',  dot: 'bg-blue-500'   },
}

function IssueRow({ issue }) {
  const sev = SEVERITY_STYLE[issue.severity] ?? SEVERITY_STYLE.info
  return (
    <div className="border border-gray-800 rounded-lg p-3 space-y-1.5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-xs px-2 py-0.5 rounded-full border ${sev.badge}`}>
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
  )
}

// ---------------------------------------------------------------------------
// Decision result
// ---------------------------------------------------------------------------

function DecisionResult({ decision }) {
  if (!decision) return null
  return (
    <div className={[
      'border rounded-xl p-4 space-y-3',
      decision.approved
        ? 'bg-green-900/20 border-green-800'
        : 'bg-red-900/20 border-red-800',
    ].join(' ')}>
      <div className="flex items-center gap-2">
        <span className={`text-sm font-medium ${decision.approved ? 'text-green-400' : 'text-red-400'}`}>
          Decisor — {decision.approved ? 'Coherent with plan' : 'Inconsistent with plan'}
        </span>
      </div>

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
  )
}

// ---------------------------------------------------------------------------
// Action buttons
// ---------------------------------------------------------------------------

function ActionButtons({ runStatus, commitHash }) {
  const navigate = useNavigate()

  if (runStatus === 'approved') {
    return (
      <div className="flex items-center gap-4 flex-wrap">
        <button
          onClick={() => navigate('/')}
          className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-xl px-5 py-2.5 transition-colors"
        >
          + New Task
        </button>
        {commitHash && (
          <span className="text-xs text-gray-500 font-mono">
            commit {commitHash.slice(0, 8)}
          </span>
        )}
      </div>
    )
  }

  if (runStatus === 'escalated') {
    return (
      <div className="space-y-3">
        <p className="text-xs text-gray-500">
          This run was escalated. Inspect the diff and issues above, intervene manually in the project, then start a new task.
        </p>
        <button
          onClick={() => navigate('/')}
          className="bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 text-sm rounded-xl px-5 py-2.5 transition-colors"
        >
          ← Back to Home
        </button>
      </div>
    )
  }

  return null
}

// ---------------------------------------------------------------------------
// ReviewPanel
// ---------------------------------------------------------------------------

export default function ReviewPanel({ review, decision, diff, runStatus, commitHash }) {
  const [collapsed, setCollapsed] = useState(false)

  // Only show when there is something to display
  const hasContent = review || decision || diff

  if (!hasContent) return null

  const isApproved   = review?.approved  ?? false
  const isConsistent = decision?.approved ?? false

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* Panel header */}
      <button
        onClick={() => setCollapsed(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 border-b border-gray-800 text-left hover:bg-gray-800/40 transition-colors"
      >
        <span className="text-sm font-medium text-gray-200 flex-1">Review &amp; Decision</span>
        <span className={`text-xs ${isApproved ? 'text-green-400' : 'text-red-400'}`}>
          {isApproved ? 'Approved' : review ? 'Rejected' : '—'}
        </span>
        <span className="text-gray-600 text-xs ml-2">{collapsed ? '▼' : '▲'}</span>
      </button>

      {!collapsed && (
        <div className="px-4 py-4 space-y-5">

          {/* Score + summary */}
          {review && (
            <div className="space-y-3">
              <ScoreGauge score={review.score} />
              {review.summary && (
                <p className="text-sm text-gray-300 leading-relaxed">{review.summary}</p>
              )}
            </div>
          )}

          {/* Issues */}
          {(review?.issues ?? []).length > 0 && (
            <div>
              <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-2">
                Issues ({review.issues.length})
              </h3>
              <div className="space-y-2">
                {review.issues.map((issue, i) => (
                  <IssueRow key={i} issue={issue} />
                ))}
              </div>
            </div>
          )}

          {/* Suggestions */}
          {(review?.suggestions ?? []).length > 0 && (
            <div>
              <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-2">Suggestions</h3>
              <ul className="space-y-1">
                {review.suggestions.map((s, i) => (
                  <li key={i} className="text-sm text-gray-400 flex gap-2">
                    <span className="text-gray-600 shrink-0">→</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Diff viewer */}
          <DiffViewer diff={diff} />

          {/* Decision */}
          <DecisionResult decision={decision} />

          {/* Actions */}
          <ActionButtons runStatus={runStatus} commitHash={commitHash} />

        </div>
      )}
    </div>
  )
}
