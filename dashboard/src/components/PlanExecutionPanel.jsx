import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import AgentCard from './AgentCard'
import { useRunSocket, AGENTS } from '../hooks/useRunSocket'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function findTaskMeta(plan, taskId) {
  if (!plan || !taskId) return null
  for (const phase of plan.phases ?? []) {
    for (const sp of phase.subphases ?? []) {
      const task = (sp.tasks ?? []).find(t => t.id === taskId)
      if (task) return {
        id:          task.id,
        description: task.description,
        phaseName:   phase.name,
        subName:     sp.name,
      }
    }
  }
  return null
}

// ---------------------------------------------------------------------------
// CurrentTaskCard — shown while a task is executing
// ---------------------------------------------------------------------------

function CurrentTaskCard({ taskMeta, currentTaskId, attempt, maxAttempt }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {/* Breadcrumb: Phase › Subphase › task id */}
          <div className="flex items-center gap-1.5 text-xs text-gray-600 mb-2 flex-wrap">
            {taskMeta?.phaseName && (
              <>
                <span>{taskMeta.phaseName}</span>
                {taskMeta.subName && (
                  <>
                    <span>›</span>
                    <span>{taskMeta.subName}</span>
                  </>
                )}
                <span>›</span>
              </>
            )}
            <span className="font-mono text-gray-500">{currentTaskId}</span>
          </div>

          {/* Task description */}
          <p className="text-sm text-gray-100 font-medium leading-snug">
            {taskMeta?.description ?? currentTaskId}
          </p>
        </div>

        {/* Attempt badge — only shown on retry */}
        {attempt > 1 && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-900/30 text-yellow-400 border border-yellow-800/50 shrink-0 whitespace-nowrap">
            Attempt {attempt}/{maxAttempt}
          </span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// FlashResult — brief card shown for 2 s after a task completes/escalates
// ---------------------------------------------------------------------------

function FlashResult({ result }) {
  const isDone = result.status === 'done'
  return (
    <div className={[
      'rounded-xl border px-4 py-3 flex items-center gap-3',
      isDone
        ? 'bg-green-900/20 border-green-800'
        : 'bg-red-900/20 border-red-800',
    ].join(' ')}>
      <span className={`text-xl leading-none ${isDone ? 'text-green-400' : 'text-red-400'}`}>
        {isDone ? '✓' : '!'}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-gray-200">
          {result.task_id} — {isDone ? 'Approved' : 'Escalated'}
        </p>
        <div className="flex gap-3 text-xs text-gray-500 mt-0.5 flex-wrap">
          {result.score      != null && <span>Score {result.score}/10</span>}
          {result.commit_hash        && <span className="font-mono">{result.commit_hash.slice(0, 7)}</span>}
          {result.duration_s != null && <span>{Math.round(result.duration_s)}s</span>}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CompleteView — shown when status is 'complete' or 'aborted'
// ---------------------------------------------------------------------------

function CompleteView({ status, results }) {
  const navigate   = useNavigate()
  const doneCount  = results.filter(r => r.status === 'done').length
  const escalCount = results.filter(r => r.status === 'escalated').length
  const skipCount  = results.filter(r => r.status === 'skipped').length
  const withHash   = results.filter(r => r.commit_hash)
  const isComplete = status === 'complete'

  return (
    <div className="p-6 space-y-5">
      {/* Banner */}
      <div className={[
        'rounded-xl border px-4 py-4 flex items-start gap-3',
        isComplete ? 'bg-green-900/20 border-green-800' : 'bg-gray-800 border-gray-700',
      ].join(' ')}>
        <span className={`text-2xl leading-none mt-0.5 ${isComplete ? 'text-green-400' : 'text-gray-400'}`}>
          {isComplete ? '✓' : '—'}
        </span>
        <div>
          <p className={`text-base font-semibold ${isComplete ? 'text-green-300' : 'text-gray-300'}`}>
            {isComplete ? 'Execution complete' : 'Execution aborted'}
          </p>
          <div className="flex gap-4 text-sm text-gray-400 mt-0.5">
            <span>{doneCount} done</span>
            {escalCount > 0 && <span className="text-red-400">{escalCount} escalated</span>}
            {skipCount  > 0 && <span>{skipCount} skipped</span>}
          </div>
        </div>
      </div>

      {/* Commits list */}
      {withHash.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500">Commits generated</p>
          <div className="space-y-1.5">
            {withHash.map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-green-500 shrink-0">{r.commit_hash.slice(0, 7)}</span>
                <span className="text-gray-500 truncate flex-1">{r.task_id}</span>
                {r.score != null && (
                  <span className="text-gray-600 shrink-0">score {r.score}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={() => navigate('/plan')}
          className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 text-sm hover:bg-gray-700 border border-gray-700 transition-colors"
        >
          Back to Plan
        </button>
        <button
          onClick={() => navigate('/history')}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500 transition-colors"
        >
          View History
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PlanExecutionPanel
// ---------------------------------------------------------------------------

export default function PlanExecutionPanel({
  plan, status, currentTaskId, currentRunId, results, wsError, planRunId,
}) {
  // Agent streaming for the current task's orchestration cycle.
  // useRunSocket handles null gracefully (no connection attempt).
  const { agents } = useRunSocket(currentRunId)

  // Flash card: shown for 2 s immediately after a task transitions from
  // active → done/escalated, so the user sees the result before the next task starts.
  const [flashResult, setFlashResult] = useState(null)
  const prevTaskIdRef = useRef(null)

  useEffect(() => {
    const prevId = prevTaskIdRef.current
    prevTaskIdRef.current = currentTaskId

    if (prevId && !currentTaskId) {
      const result = results.find(r => r.task_id === prevId)
      if (result) {
        setFlashResult(result)
        const t = setTimeout(() => setFlashResult(null), 2000)
        return () => clearTimeout(t)
      }
    }
  }, [currentTaskId])   // eslint-disable-line react-hooks/exhaustive-deps

  // Task metadata (description, phase, subphase) from the plan structure
  const taskMeta = findTaskMeta(plan, currentTaskId)

  // Executor attempt — read from agent event stream so it stays accurate
  const executorEvents  = agents?.executor?.events ?? []
  const lastExecEvt     = [...executorEvents].reverse().find(e => e.type === 'execute_started')
  const attempt         = lastExecEvt?.data?.attempt      ?? 1
  const maxAttempt      = lastExecEvt?.data?.max_attempts ?? 3

  // ── Idle / connecting ─────────────────────────────────────────────────────
  if (status === 'idle' || status === 'connecting') {
    return (
      <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
        {status === 'idle' ? 'No execution in progress.' : 'Connecting…'}
      </div>
    )
  }

  // ── Terminal states ───────────────────────────────────────────────────────
  if (status === 'complete' || status === 'aborted') {
    return <CompleteView status={status} results={results} />
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (status === 'error') {
    return (
      <div className="p-6">
        <div className="rounded-xl border border-red-800 bg-red-900/20 px-4 py-3">
          <p className="text-sm font-semibold text-red-300">Connection error</p>
          {wsError && <p className="text-xs text-gray-500 mt-0.5">{wsError}</p>}
        </div>
      </div>
    )
  }

  // ── Running ───────────────────────────────────────────────────────────────
  return (
    <div className="p-6 space-y-4">
      {/* Non-terminal WS error */}
      {wsError && (
        <p className="text-red-400 text-xs">{wsError}</p>
      )}

      {/* Task-just-completed flash result */}
      {flashResult && <FlashResult result={flashResult} />}

      {/* Current task info card */}
      {currentTaskId && (
        <CurrentTaskCard
          taskMeta={taskMeta}
          currentTaskId={currentTaskId}
          attempt={attempt}
          maxAttempt={maxAttempt}
        />
      )}

      {/* Agent streaming cards — only when currentRunId is set */}
      {currentRunId ? (
        <div className="space-y-2">
          {AGENTS.map(agentDef => (
            <AgentCard
              key={agentDef.key}
              agentDef={agentDef}
              agentState={agents[agentDef.key]}
            />
          ))}
        </div>
      ) : currentTaskId ? (
        /* currentTaskId set but run not yet registered — transient state */
        <div className="text-xs text-gray-600 text-center py-4">
          Preparing task…
        </div>
      ) : null}

      {/* Waiting between tasks */}
      {!currentTaskId && !flashResult && (
        <div className="text-gray-600 text-sm text-center py-4">
          Waiting for next task…
        </div>
      )}

      {/* Recent results strip (last 5, newest first) */}
      {results.length > 0 && (
        <div className="pt-3 border-t border-gray-800 space-y-1.5">
          <p className="text-xs text-gray-600 mb-1">
            {results.filter(r => r.status === 'done').length} / {results.length} tasks complete
          </p>
          {results.slice(-5).reverse().map((r, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-gray-500">
              <span className={
                r.status === 'done'      ? 'text-green-400' :
                r.status === 'escalated' ? 'text-red-400'   : 'text-gray-600'
              }>
                {r.status === 'done' ? '✓' : r.status === 'escalated' ? '!' : '−'}
              </span>
              <span className="font-mono text-gray-600">{r.task_id}</span>
              {r.commit_hash && (
                <span className="font-mono text-gray-700">{r.commit_hash.slice(0, 7)}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
