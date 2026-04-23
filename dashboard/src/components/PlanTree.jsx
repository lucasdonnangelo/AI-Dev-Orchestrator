import { useState, useEffect, useRef } from 'react'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getTaskStatus(taskId, currentTaskId, results) {
  if (taskId === currentTaskId) return 'running'
  const result = results.find(r => r.task_id === taskId)
  if (!result) return 'pending'
  return result.status // 'done' | 'escalated' | 'skipped'
}

// ---------------------------------------------------------------------------
// StatusIcon
// ---------------------------------------------------------------------------

function StatusIcon({ status }) {
  const map = {
    pending:   { char: '○', cls: 'text-gray-600' },
    running:   { char: '▶', cls: 'text-indigo-400 animate-pulse' },
    done:      { char: '✓', cls: 'text-green-400' },
    escalated: { char: '!', cls: 'text-red-400 font-bold' },
    skipped:   { char: '−', cls: 'text-gray-500' },
  }
  const { char, cls } = map[status] ?? map.pending
  return <span className={`font-mono text-xs leading-none ${cls}`}>{char}</span>
}

// ---------------------------------------------------------------------------
// TaskRow
// ---------------------------------------------------------------------------

function TaskRow({ task, status, result }) {
  const isActive    = status === 'running'
  const isDone      = status === 'done'
  const isEscalated = status === 'escalated'
  const commitHash  = result?.commit_hash
  const rowRef      = useRef(null)

  // Scroll active task into view when it becomes active
  useEffect(() => {
    if (isActive && rowRef.current) {
      rowRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [isActive])

  return (
    <div
      ref={rowRef}
      title={task.description}
      className={[
        'group flex items-start gap-2 px-3 py-1.5 text-xs rounded mx-1 transition-colors cursor-default',
        isActive
          ? 'bg-indigo-900/30 border border-indigo-800/50'
          : isEscalated
          ? 'bg-red-900/10 hover:bg-red-900/20'
          : 'hover:bg-gray-800/40',
      ].join(' ')}
    >
      {/* Status icon */}
      <span className="mt-0.5 shrink-0">
        <StatusIcon status={status} />
      </span>

      {/* Task id + description */}
      <span className="flex-1 min-w-0 flex items-baseline gap-1.5 overflow-hidden">
        <span className="text-gray-600 shrink-0 font-mono">{task.id}</span>
        <span className={[
          'truncate leading-snug',
          isActive    ? 'text-indigo-300 font-medium' :
          isDone      ? 'text-gray-500' :
          isEscalated ? 'text-red-300' :
                        'text-gray-300',
        ].join(' ')}>
          {task.description}
        </span>
      </span>

      {/* Commit hash — only for done tasks, visible on hover */}
      {isDone && commitHash && (
        <span className="font-mono text-gray-700 text-[10px] opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          {commitHash.slice(0, 7)}
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SubPhaseSection
// ---------------------------------------------------------------------------

function SubPhaseSection({ subphase, currentTaskId, results }) {
  const tasks = subphase.tasks ?? []

  const doneCount = tasks.filter(t => {
    const r = results.find(r => r.task_id === t.id)
    return r?.status === 'done'
  }).length

  return (
    <div className="mb-1.5">
      {/* SubPhase header with counter */}
      <div className="flex items-center gap-2 px-3 py-0.5">
        <span className="text-xs text-gray-500 font-medium truncate flex-1">
          {subphase.id} — {subphase.name}
        </span>
        {tasks.length > 0 && (
          <span className="text-[10px] text-gray-700 shrink-0">
            {doneCount}/{tasks.length}
          </span>
        )}
      </div>

      {/* Tasks */}
      <div className="pl-2">
        {tasks.map(task => {
          const st = getTaskStatus(task.id, currentTaskId, results)
          return (
            <TaskRow
              key={task.id}
              task={task}
              status={st}
              result={results.find(r => r.task_id === task.id) ?? null}
            />
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PhaseSection
// ---------------------------------------------------------------------------

function PhaseSection({ phase, currentTaskId, results, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen ?? true)

  const allTaskIds = (phase.subphases ?? []).flatMap(sp =>
    (sp.tasks ?? []).map(t => t.id)
  )
  const doneCount = allTaskIds.filter(id => {
    const r = results.find(r => r.task_id === id)
    return r?.status === 'done'
  }).length
  const isAllDone = allTaskIds.length > 0 && doneCount === allTaskIds.length
  const isActive  = currentTaskId != null && allTaskIds.includes(currentTaskId)

  // Auto-expand when a task in this phase becomes active
  useEffect(() => {
    if (isActive) setOpen(true)
  }, [isActive])

  return (
    <div className="mb-0.5">
      {/* Phase header — clickable to collapse */}
      <button
        onClick={() => setOpen(o => !o)}
        className={[
          'w-full flex items-center gap-2 px-3 py-2 text-left transition-colors group',
          isActive ? 'hover:bg-indigo-950/40' : 'hover:bg-gray-800/50',
        ].join(' ')}
      >
        {/* Chevron */}
        <span className={[
          'text-xs w-3 shrink-0 transition-colors',
          isActive ? 'text-indigo-500' : 'text-gray-600 group-hover:text-gray-400',
        ].join(' ')}>
          {open ? '▾' : '▸'}
        </span>

        {/* Status dot */}
        <span className={[
          'w-1.5 h-1.5 rounded-full shrink-0 mt-0.5',
          isActive  ? 'bg-indigo-400 animate-pulse' :
          isAllDone ? 'bg-green-500' :
          doneCount > 0 ? 'bg-indigo-700' :
                          'bg-gray-700',
        ].join(' ')} />

        {/* Phase name */}
        <span className={[
          'flex-1 text-sm font-semibold truncate',
          isActive ? 'text-indigo-200' : 'text-gray-200',
        ].join(' ')}>
          {phase.name}
        </span>

        {/* X/Y counter */}
        {allTaskIds.length > 0 && (
          <span className={[
            'text-xs shrink-0',
            isAllDone ? 'text-green-600' : 'text-gray-600',
          ].join(' ')}>
            {doneCount}/{allTaskIds.length}
          </span>
        )}
      </button>

      {/* SubPhases */}
      {open && (
        <div className="pl-3 pb-1 border-l border-gray-800/60 ml-4">
          {(phase.subphases ?? []).map(sp => (
            <SubPhaseSection
              key={sp.id}
              subphase={sp}
              currentTaskId={currentTaskId}
              results={results}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PlanTree
// ---------------------------------------------------------------------------

export default function PlanTree({ plan, currentTaskId, results }) {
  if (!plan) {
    return (
      <div className="p-4 text-xs text-gray-600 text-center">
        No plan loaded.
      </div>
    )
  }

  const phases     = plan.phases ?? []
  const totalDone  = results.filter(r => r.status === 'done').length
  const totalTasks = plan.total_tasks ?? 0
  const pct        = totalTasks > 0 ? Math.round((totalDone / totalTasks) * 100) : 0

  return (
    <div className="py-1">
      {/* Plan header */}
      <div className="px-3 py-2.5 mb-1 border-b border-gray-800">
        <p className="text-xs font-semibold text-gray-200 truncate" title={plan.name}>
          {plan.name}
        </p>
        {totalTasks > 0 && (
          <>
            <p className="text-[10px] text-gray-600 mt-0.5">
              {totalDone}/{totalTasks} complete
            </p>
            {/* Mini global progress bar */}
            <div className="mt-1.5 h-0.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-600 rounded-full transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
          </>
        )}
      </div>

      {/* Phases */}
      {phases.map((phase, idx) => {
        const containsCurrent = (phase.subphases ?? []).some(sp =>
          (sp.tasks ?? []).some(t => t.id === currentTaskId)
        )
        return (
          <PhaseSection
            key={phase.id ?? idx}
            phase={phase}
            currentTaskId={currentTaskId}
            results={results}
            defaultOpen={idx === 0 || containsCurrent}
          />
        )
      })}
    </div>
  )
}
