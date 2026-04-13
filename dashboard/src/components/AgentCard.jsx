import { useState } from 'react'

// ---------------------------------------------------------------------------
// Tailwind color map per agent
// ---------------------------------------------------------------------------

const COLOR = {
  indigo: {
    border:  'border-indigo-500',
    glow:    'shadow-indigo-500/20',
    badge:   'bg-indigo-900/50 text-indigo-300',
    dot:     'bg-indigo-400',
    spinner: 'border-indigo-400',
    label:   'text-indigo-300',
  },
  cyan: {
    border:  'border-cyan-500',
    glow:    'shadow-cyan-500/20',
    badge:   'bg-cyan-900/50 text-cyan-300',
    dot:     'bg-cyan-400',
    spinner: 'border-cyan-400',
    label:   'text-cyan-300',
  },
  green: {
    border:  'border-green-500',
    glow:    'shadow-green-500/20',
    badge:   'bg-green-900/50 text-green-300',
    dot:     'bg-green-400',
    spinner: 'border-green-400',
    label:   'text-green-300',
  },
  yellow: {
    border:  'border-yellow-500',
    glow:    'shadow-yellow-500/20',
    badge:   'bg-yellow-900/50 text-yellow-300',
    dot:     'bg-yellow-400',
    spinner: 'border-yellow-400',
    label:   'text-yellow-300',
  },
  purple: {
    border:  'border-purple-500',
    glow:    'shadow-purple-500/20',
    badge:   'bg-purple-900/50 text-purple-300',
    dot:     'bg-purple-400',
    spinner: 'border-purple-400',
    label:   'text-purple-300',
  },
}

// ---------------------------------------------------------------------------
// Status indicator
// ---------------------------------------------------------------------------

function StatusIndicator({ status, color }) {
  const c = COLOR[color]
  if (status === 'active') {
    return (
      <span
        className={`inline-block w-4 h-4 rounded-full border-2 border-t-transparent ${c.spinner} animate-spin`}
      />
    )
  }
  if (status === 'done') {
    return <span className="text-green-400 text-sm leading-none">✓</span>
  }
  if (status === 'failed') {
    return <span className="text-red-400 text-sm leading-none">✕</span>
  }
  // idle
  return <span className={`inline-block w-2 h-2 rounded-full bg-gray-700`} />
}

// ---------------------------------------------------------------------------
// Event detail row
// ---------------------------------------------------------------------------

function EventRow({ evt }) {
  const type = evt.type ?? ''
  const data = evt.data ?? {}

  // Build a human-readable summary per event type
  let summary = ''
  if (type === 'plan_started')       summary = `Planning: "${data.task ?? ''}"`
  else if (type === 'plan_completed') summary = `Plan ready — ${data.plan?.steps?.length ?? 0} step(s)`
  else if (type === 'critic_round')   summary = `Round ${data.round} · score ${data.score}/10 · consensus: ${data.consensus ? 'yes' : 'no'}`
  else if (type === 'critic_consensus') summary = `Consensus reached at round ${data.round} · score ${data.score}/10`
  else if (type === 'execute_started')  summary = `Attempt ${data.attempt}/${data.max_attempts}`
  else if (type === 'execute_completed') summary = `Done — ${data.diff_lines ?? 0} diff lines`
  else if (type === 'review_started')   summary = `Reviewing attempt ${data.attempt}`
  else if (type === 'review_completed') summary = `${data.approved ? 'Approved' : 'Rejected'} · score ${data.score}/10 · ${data.issues_count ?? 0} issue(s)`
  else if (type === 'decision_started') summary = 'Validating coherence with plan…'
  else if (type === 'decision_completed') summary = `${data.approved ? 'Coherent' : 'Inconsistent'} — ${data.reasoning?.slice(0, 80) ?? ''}${(data.reasoning?.length ?? 0) > 80 ? '…' : ''}`
  else summary = type

  const time = evt.timestamp
    ? new Date(evt.timestamp).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : ''

  return (
    <div className="flex gap-2 text-xs py-1.5 border-b border-gray-800 last:border-0">
      <span className="text-gray-600 shrink-0 font-mono">{time}</span>
      <span className="text-gray-400">{summary}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// AgentCard
// ---------------------------------------------------------------------------

export default function AgentCard({ agentDef, agentState }) {
  const [expanded, setExpanded] = useState(false)
  const { label, color } = agentDef
  const { status, events } = agentState
  const c = COLOR[color] ?? COLOR.indigo

  const isActive = status === 'active'
  const hasDone  = status !== 'idle'

  return (
    <div
      className={[
        'bg-gray-900 border rounded-xl flex flex-col transition-all duration-300',
        isActive
          ? `${c.border} shadow-lg ${c.glow}`
          : hasDone
            ? 'border-gray-700'
            : 'border-gray-800',
      ].join(' ')}
    >
      {/* Card header */}
      <button
        onClick={() => hasDone && setExpanded(v => !v)}
        className={[
          'flex items-center gap-3 px-4 py-3 w-full text-left',
          hasDone ? 'cursor-pointer' : 'cursor-default',
        ].join(' ')}
      >
        <StatusIndicator status={status} color={color} />

        <span
          className={[
            'text-sm font-medium flex-1',
            isActive ? c.label : hasDone ? 'text-gray-300' : 'text-gray-600',
          ].join(' ')}
        >
          {label}
        </span>

        {events.length > 0 && (
          <span className={`text-xs px-1.5 py-0.5 rounded ${c.badge}`}>
            {events.length}
          </span>
        )}

        {hasDone && events.length > 0 && (
          <span className="text-gray-600 text-xs ml-1">
            {expanded ? '▲' : '▼'}
          </span>
        )}
      </button>

      {/* Expanded event list */}
      {expanded && events.length > 0 && (
        <div className="px-4 pb-3 border-t border-gray-800">
          {events.map((evt, i) => (
            <EventRow key={i} evt={evt} />
          ))}
        </div>
      )}
    </div>
  )
}
