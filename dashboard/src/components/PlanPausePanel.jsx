// ---------------------------------------------------------------------------
// PlanPausePanel — displayed in the center panel when status === 'paused'.
// Stub implementation — will be expanded in Phase 7.2.5.
// ---------------------------------------------------------------------------

function formatDuration(seconds) {
  if (seconds == null) return null
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

const PAUSE_TITLE = {
  subphase:   'Subfase complete',
  phase:      'Phase complete',
  escalation: 'Task escalated — intervention required',
  requested:  'Paused',
}

const PAUSE_SUBTITLE = {
  subphase:   'Review the results below and continue when ready.',
  phase:      'Review the results below and continue when ready.',
  escalation: 'This task requires manual intervention before continuing.',
  requested:  'Execution is paused. Continue when ready.',
}

export default function PlanPausePanel({ pauseReason, pauseContext, onResume, onAbort }) {
  const title    = PAUSE_TITLE[pauseReason]    ?? 'Paused'
  const subtitle = PAUSE_SUBTITLE[pauseReason] ?? 'Continue when ready.'
  const ctx      = pauseContext ?? {}
  const duration = formatDuration(ctx.duration_s)

  return (
    <div className="flex items-center justify-center min-h-full p-6">
      <div className="w-full max-w-md bg-gray-900 border border-yellow-800/40 rounded-2xl p-6 space-y-5">

        {/* Icon + title */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-yellow-900/25 border border-yellow-800/40">
            <span className="text-yellow-400 text-xl leading-none">||</span>
          </div>
          <div>
            <p className="text-sm font-semibold text-yellow-300">{title}</p>
            <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
          </div>
        </div>

        {/* Summary stats */}
        {(ctx.done != null || ctx.escalated != null || duration) && (
          <div className="space-y-2 text-sm border border-gray-800 rounded-xl px-4 py-3">
            {ctx.done != null && (
              <div className="flex justify-between text-gray-400">
                <span>Tasks completed</span>
                <span className="text-gray-300 font-medium">{ctx.done}</span>
              </div>
            )}
            {ctx.escalated != null && (
              <div className="flex justify-between text-gray-400">
                <span>Tasks escalated</span>
                <span className={ctx.escalated > 0 ? 'text-red-400 font-medium' : 'text-gray-300 font-medium'}>
                  {ctx.escalated}
                </span>
              </div>
            )}
            {duration && (
              <div className="flex justify-between text-gray-400">
                <span>Duration</span>
                <span className="text-gray-300 font-medium">{duration}</span>
              </div>
            )}
          </div>
        )}

        {/* Commits list */}
        {ctx.commits?.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-gray-500">Commits generated</p>
            <div className="space-y-0.5">
              {ctx.commits.map((c, i) => (
                <p key={i} className="text-xs text-gray-400 font-mono truncate">{c}</p>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={onResume}
            className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 transition-colors"
          >
            Continue
          </button>
          <button
            onClick={onAbort}
            className="px-4 py-2 rounded-lg bg-gray-800 text-gray-400 text-sm hover:bg-gray-700 border border-gray-700 transition-colors"
          >
            Abort
          </button>
        </div>
      </div>
    </div>
  )
}
