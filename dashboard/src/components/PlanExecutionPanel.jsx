// ---------------------------------------------------------------------------
// PlanExecutionPanel — central panel showing the current task state.
// Stub implementation — will be expanded in Phase 7.2.4.
// ---------------------------------------------------------------------------

const STATUS_MSG = {
  idle:       'No execution in progress.',
  connecting: 'Connecting to plan run…',
}

export default function PlanExecutionPanel({
  status, currentTaskId, currentRunId, results, wsError, planRunId,
}) {
  const doneCount      = results.filter(r => r.status === 'done').length
  const escalatedCount = results.filter(r => r.status === 'escalated').length

  // Idle / connecting
  if (status === 'idle' || status === 'connecting') {
    return (
      <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
        {STATUS_MSG[status]}
      </div>
    )
  }

  // Terminal states
  if (status === 'complete' || status === 'aborted') {
    const isComplete = status === 'complete'
    return (
      <div className="p-6">
        <div className={[
          'rounded-xl border px-4 py-4 flex items-start gap-3',
          isComplete
            ? 'bg-green-900/20 border-green-800'
            : 'bg-gray-800 border-gray-700',
        ].join(' ')}>
          <span className={`text-xl leading-none mt-0.5 ${isComplete ? 'text-green-400' : 'text-gray-400'}`}>
            {isComplete ? '✓' : '—'}
          </span>
          <div>
            <p className={`text-sm font-semibold ${isComplete ? 'text-green-300' : 'text-gray-300'}`}>
              {isComplete ? 'Execution complete' : 'Execution aborted'}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {doneCount} tasks done · {escalatedCount} escalated
            </p>
          </div>
        </div>

        {/* Compact results list */}
        {results.length > 0 && (
          <div className="mt-4 space-y-1">
            <p className="text-xs text-gray-500 mb-2">Results</p>
            {results.map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-gray-400">
                <span className={
                  r.status === 'done'      ? 'text-green-400' :
                  r.status === 'escalated' ? 'text-red-400'   : 'text-gray-500'
                }>
                  {r.status === 'done' ? '✓' : r.status === 'escalated' ? '!' : '−'}
                </span>
                <span className="text-gray-500">{r.task_id}</span>
                {r.commit_hash && (
                  <span className="text-gray-600 font-mono">{r.commit_hash.slice(0, 7)}</span>
                )}
                {r.score != null && (
                  <span className="text-gray-600">score {r.score}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // Running or error
  return (
    <div className="p-6 space-y-4">
      {wsError && (
        <p className="text-red-400 text-xs">{wsError}</p>
      )}

      {/* Current task card */}
      {currentTaskId ? (
        <div className="rounded-xl border border-indigo-800/50 bg-indigo-900/10 px-4 py-3 space-y-1">
          <p className="text-xs text-indigo-400 font-medium uppercase tracking-wide">
            Running
          </p>
          <p className="text-sm text-gray-200 font-semibold">{currentTaskId}</p>
          {currentRunId && (
            <p className="text-xs text-gray-600 font-mono">
              run {currentRunId.slice(0, 8)}…
            </p>
          )}
        </div>
      ) : (
        <div className="text-gray-600 text-sm">
          Waiting for next task…
        </div>
      )}

      {/* Recent results */}
      {results.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500">Recent</p>
          {results.slice(-5).reverse().map((r, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-gray-400">
              <span className={
                r.status === 'done'      ? 'text-green-400' :
                r.status === 'escalated' ? 'text-red-400'   : 'text-gray-500'
              }>
                {r.status === 'done' ? '✓' : r.status === 'escalated' ? '!' : '−'}
              </span>
              <span className="text-gray-500">{r.task_id}</span>
              {r.commit_hash && (
                <span className="text-gray-600 font-mono">{r.commit_hash.slice(0, 7)}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
