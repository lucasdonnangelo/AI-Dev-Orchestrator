// ---------------------------------------------------------------------------
// PlanPausePanel — prominent pause overlay shown in the center panel when
// status === 'paused'. Designed to be impossible to overlook.
//
// Props:
//   pauseReason  — 'subphase' | 'phase' | 'escalation' | 'requested' | null
//   pauseContext — { done, escalated, commits, duration_s, task_id?, reason? }
//   onResume     — async fn: continues execution
//   onAbort      — async fn: aborts the run
//   onSkip       — async fn | undefined: skips the escalated task (optional)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(seconds) {
  if (seconds == null) return null
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

// ---------------------------------------------------------------------------
// PauseIcon — visual indicator per reason type
// ---------------------------------------------------------------------------

function PauseIcon({ reason }) {
  const isEscalation = reason === 'escalation'
  return (
    <div className={[
      'inline-flex items-center justify-center w-14 h-14 rounded-full border-2',
      isEscalation
        ? 'bg-red-900/30 border-red-700/60'
        : 'bg-yellow-900/25 border-yellow-700/50',
    ].join(' ')}>
      {isEscalation ? (
        <span className="text-red-400 text-2xl font-bold leading-none">!</span>
      ) : (
        <span className="text-yellow-400 text-xl font-bold leading-none tracking-tighter">II</span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// StatRow — single labelled stat line
// ---------------------------------------------------------------------------

function StatRow({ label, value, valueClass = 'text-gray-200' }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5 border-b border-gray-800/60 last:border-0">
      <span className="text-sm text-gray-400">{label}</span>
      <span className={`text-sm font-medium ${valueClass}`}>{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CommitList
// ---------------------------------------------------------------------------

function CommitList({ commits }) {
  if (!commits?.length) return null
  return (
    <div className="space-y-1">
      <p className="text-xs text-gray-500 mb-1.5">Commits generated</p>
      <div className="bg-gray-800/50 rounded-lg px-3 py-2 space-y-1 max-h-28 overflow-y-auto">
        {commits.map((c, i) => (
          <p key={i} className="text-xs text-gray-300 font-mono truncate">{c}</p>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// NormalPausePanel — for subphase / phase / requested pauses
// ---------------------------------------------------------------------------

function NormalPausePanel({ pauseReason, pauseContext, onResume, onAbort }) {
  const ctx      = pauseContext ?? {}
  const duration = formatDuration(ctx.duration_s)

  const title = {
    subphase: 'Subfase complete',
    phase:    'Phase complete',
    requested: 'Paused',
  }[pauseReason] ?? 'Paused'

  const subtitle = {
    subphase:  'Review the results and continue when ready.',
    phase:     'Review the phase results and continue when ready.',
    requested: 'Execution is paused. Continue when ready.',
  }[pauseReason] ?? 'Continue when ready.'

  const hasStats = ctx.done != null || ctx.escalated != null || duration

  return (
    <div className="flex items-center justify-center min-h-full p-6">
      <div className="w-full max-w-lg bg-gray-900 border border-yellow-800/40 rounded-2xl shadow-xl shadow-black/40 p-6 space-y-5">

        {/* Icon + title */}
        <div className="text-center space-y-3">
          <PauseIcon reason={pauseReason} />
          <div>
            <p className="text-base font-semibold text-yellow-300">{title}</p>
            <p className="text-xs text-gray-500 mt-1">{subtitle}</p>
          </div>
        </div>

        {/* Stats */}
        {hasStats && (
          <div className="bg-gray-800/30 rounded-xl px-4 py-1">
            {ctx.done != null && (
              <StatRow label="Tasks completed" value={ctx.done} />
            )}
            {ctx.escalated != null && (
              <StatRow
                label="Tasks escalated"
                value={ctx.escalated}
                valueClass={ctx.escalated > 0 ? 'text-red-400' : 'text-gray-200'}
              />
            )}
            {duration && (
              <StatRow label="Duration" value={duration} />
            )}
          </div>
        )}

        {/* Commits */}
        <CommitList commits={ctx.commits} />

        {/* Actions */}
        <div className="flex gap-3 pt-1">
          <button
            onClick={onResume}
            className="flex-1 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-500 transition-colors"
          >
            Continue
          </button>
          <button
            onClick={onAbort}
            className="px-5 py-2.5 rounded-xl bg-gray-800 text-gray-400 text-sm hover:bg-gray-700 border border-gray-700 transition-colors"
          >
            Abort
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// EscalationPanel — for escalation pauses (task failed all retries)
// ---------------------------------------------------------------------------

function EscalationPanel({ pauseContext, onResume, onAbort, onSkip }) {
  const ctx      = pauseContext ?? {}
  const taskId   = ctx.task_id  ?? null
  const reason   = ctx.reason   ?? null
  const duration = formatDuration(ctx.duration_s)

  return (
    <div className="flex items-center justify-center min-h-full p-6">
      <div className="w-full max-w-lg bg-gray-900 border border-red-800/50 rounded-2xl shadow-xl shadow-black/40 p-6 space-y-5">

        {/* Icon + title */}
        <div className="text-center space-y-3">
          <PauseIcon reason="escalation" />
          <div>
            <p className="text-base font-semibold text-red-300">Task escalated</p>
            <p className="text-xs text-gray-500 mt-1">
              Manual intervention required before continuing.
            </p>
          </div>
        </div>

        {/* Escalated task info */}
        <div className="bg-red-900/10 border border-red-900/40 rounded-xl px-4 py-3 space-y-1.5">
          {taskId && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">Task</span>
              <span className="text-xs font-mono text-gray-300">{taskId}</span>
            </div>
          )}
          {reason && (
            <p className="text-xs text-gray-400 leading-snug">{reason}</p>
          )}
        </div>

        {/* Stats */}
        {(ctx.done != null || duration) && (
          <div className="bg-gray-800/30 rounded-xl px-4 py-1">
            {ctx.done != null && (
              <StatRow label="Tasks completed before escalation" value={ctx.done} />
            )}
            {duration && (
              <StatRow label="Duration" value={duration} />
            )}
          </div>
        )}

        {/* Commits before escalation */}
        <CommitList commits={ctx.commits} />

        {/* Actions: Retry / Skip / Abort */}
        <div className="space-y-2 pt-1">
          <button
            onClick={onResume}
            className="w-full py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-500 transition-colors"
          >
            Tentar novamente
          </button>
          <div className="flex gap-2">
            <button
              onClick={onSkip}
              disabled={!onSkip}
              className="flex-1 py-2 rounded-xl bg-gray-800 text-gray-300 text-sm hover:bg-gray-700 border border-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              title={!onSkip ? 'Not yet supported' : undefined}
            >
              Pular task
            </button>
            <button
              onClick={onAbort}
              className="flex-1 py-2 rounded-xl bg-red-900/30 text-red-400 text-sm hover:bg-red-900/50 border border-red-800/50 transition-colors"
            >
              Abortar
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PlanPausePanel — dispatcher
// ---------------------------------------------------------------------------

export default function PlanPausePanel({ pauseReason, pauseContext, onResume, onAbort, onSkip }) {
  if (pauseReason === 'escalation') {
    return (
      <EscalationPanel
        pauseContext={pauseContext}
        onResume={onResume}
        onAbort={onAbort}
        onSkip={onSkip}
      />
    )
  }

  return (
    <NormalPausePanel
      pauseReason={pauseReason}
      pauseContext={pauseContext}
      onResume={onResume}
      onAbort={onAbort}
    />
  )
}
