import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import Layout from '../components/Layout'
import PlanTree from '../components/PlanTree'
import PlanExecutionPanel from '../components/PlanExecutionPanel'
import PlanPausePanel from '../components/PlanPausePanel'
import { usePlanSocket } from '../hooks/usePlanSocket'
import { usePlanRunContext } from '../context/PlanRunContext'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// Status dot
// ---------------------------------------------------------------------------

function StatusDot({ status }) {
  const styles = {
    running:    'bg-green-400 animate-pulse',
    paused:     'bg-yellow-400',
    complete:   'bg-indigo-400',
    aborted:    'bg-red-400',
    error:      'bg-red-400',
    connecting: 'bg-gray-400 animate-pulse',
  }
  return (
    <span className={`inline-block w-2 h-2 rounded-full ${styles[status] ?? 'bg-gray-600'}`} />
  )
}

const STATUS_LABEL = {
  idle:       'Idle',
  connecting: 'Connecting…',
  running:    'Running',
  paused:     'Paused',
  complete:   'Complete',
  aborted:    'Aborted',
  error:      'Error',
}

// ---------------------------------------------------------------------------
// PlanRun page
// ---------------------------------------------------------------------------

export default function PlanRun() {
  const { planRunId } = useParams()
  const navigate      = useNavigate()

  const {
    plan: wsPlan, status, currentTaskId, currentRunId,
    pauseReason, pauseContext, results, wsError,
    resume, abort,
  } = usePlanSocket(planRunId)

  // Sync plan run status to global context so Sidebar can show the badge
  const { setActivePlanRun, clearActivePlanRun } = usePlanRunContext()

  useEffect(() => {
    setActivePlanRun(planRunId, status)
  }, [planRunId, status, setActivePlanRun])

  useEffect(() => {
    return () => clearActivePlanRun()
  }, [clearActivePlanRun])   // eslint-disable-line react-hooks/exhaustive-deps

  // Full plan from REST — includes subphases + tasks for PlanTree
  const [fullPlan, setFullPlan] = useState(null)

  useEffect(() => {
    if (!planRunId) return
    api.get(`/api/plan/run/${planRunId}`)
      .then(data => { if (data?.plan) setFullPlan(data.plan) })
      .catch(() => {})
  }, [planRunId])

  // Use full plan when available; simplified WS plan as fallback while REST loads
  const displayPlan = fullPlan ?? wsPlan

  const doneCount  = results.filter(r => r.status === 'done').length
  const totalTasks = displayPlan?.total_tasks ?? 0
  const pct        = totalTasks > 0 ? Math.round((doneCount / totalTasks) * 100) : 0

  const isLive = ['connecting', 'running', 'paused'].includes(status)

  function handlePause() {
    api.post(`/api/plan/pause/${planRunId}`).catch(() => {})
  }

  return (
    <Layout>
      {/* ------------------------------------------------------------------ */}
      {/* Header zone                                                          */}
      {/* ------------------------------------------------------------------ */}
      <header className="h-14 border-b border-gray-800 px-6 flex items-center gap-4 shrink-0">
        {/* Title + status */}
        <div className="flex-1 min-w-0 flex items-center gap-3">
          <h1 className="text-white font-medium text-base truncate">
            {displayPlan?.name ?? 'Plan Execution'}
          </h1>
          <div className="flex items-center gap-2 text-xs text-gray-400 shrink-0">
            <StatusDot status={status} />
            <span>{STATUS_LABEL[status] ?? status}</span>
            {totalTasks > 0 && (
              <span className="text-gray-600">· {doneCount}/{totalTasks} tasks</span>
            )}
          </div>
        </div>

        {/* Progress bar */}
        {isLive && totalTasks > 0 && (
          <div className="w-32 shrink-0">
            <div className="flex justify-end text-xs text-gray-600 mb-0.5">
              <span>{pct}%</span>
            </div>
            <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )}

        {/* Controls */}
        <div className="flex items-center gap-2 shrink-0">
          {status === 'running' && (
            <button
              onClick={handlePause}
              className="text-xs px-3 py-1.5 rounded-md bg-gray-800 text-gray-300 hover:bg-gray-700 border border-gray-700 transition-colors"
            >
              Pause
            </button>
          )}
          {isLive && (
            <button
              onClick={abort}
              className="text-xs px-3 py-1.5 rounded-md bg-red-900/40 text-red-400 hover:bg-red-900/60 border border-red-800 transition-colors"
            >
              Abort
            </button>
          )}
          <button
            onClick={() => navigate('/plan')}
            className="text-xs text-gray-600 hover:text-gray-400 transition-colors ml-1"
          >
            ← Back
          </button>
        </div>
      </header>

      {/* ------------------------------------------------------------------ */}
      {/* Body: PlanTree (left) + execution panel (center)                    */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar — plan tree */}
        <aside className="w-72 border-r border-gray-800 overflow-y-auto shrink-0 bg-gray-900/30">
          <PlanTree
            plan={displayPlan}
            currentTaskId={currentTaskId}
            results={results}
          />
        </aside>

        {/* Center — execution or pause panel */}
        <main className="flex-1 overflow-y-auto">
          {status === 'paused' ? (
            <PlanPausePanel
              pauseReason={pauseReason}
              pauseContext={pauseContext}
              onResume={resume}
              onAbort={abort}
            />
          ) : (
            <PlanExecutionPanel
              plan={displayPlan}
              status={status}
              currentTaskId={currentTaskId}
              currentRunId={currentRunId}
              results={results}
              wsError={wsError}
              planRunId={planRunId}
            />
          )}
        </main>
      </div>
    </Layout>
  )
}
