import { useState } from 'react'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function taskStatus(taskId, currentTaskId, results) {
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
    escalated: { char: '!', cls: 'text-red-400' },
    skipped:   { char: '−', cls: 'text-gray-500' },
  }
  const { char, cls } = map[status] ?? map.pending
  return <span className={`font-mono text-xs leading-none ${cls}`}>{char}</span>
}

// ---------------------------------------------------------------------------
// TaskRow
// ---------------------------------------------------------------------------

function TaskRow({ task, status }) {
  const isActive = status === 'running'
  return (
    <div
      title={task.description}
      className={[
        'flex items-start gap-2 px-3 py-1.5 text-xs rounded mx-1 transition-colors',
        isActive
          ? 'bg-indigo-900/30 border border-indigo-800/50'
          : 'hover:bg-gray-800/40',
      ].join(' ')}
    >
      <span className="mt-0.5 shrink-0">
        <StatusIcon status={status} />
      </span>
      <span
        className={[
          'flex-1 min-w-0 leading-snug truncate',
          isActive  ? 'text-indigo-300 font-medium' : '',
          status === 'done' ? 'text-gray-500' : 'text-gray-300',
        ].join(' ')}
      >
        <span className="text-gray-600 mr-1 shrink-0">{task.id}</span>
        {task.description}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SubPhaseSection
// ---------------------------------------------------------------------------

function SubPhaseSection({ subphase, currentTaskId, results }) {
  return (
    <div className="mb-1">
      <div className="px-3 py-0.5 text-xs text-gray-500 font-medium">
        {subphase.id} — {subphase.name}
      </div>
      <div className="pl-2">
        {(subphase.tasks ?? []).map(task => (
          <TaskRow
            key={task.id}
            task={task}
            status={taskStatus(task.id, currentTaskId, results)}
          />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PhaseSection
// ---------------------------------------------------------------------------

function PhaseSection({ phase, currentTaskId, results, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen ?? true)

  // Count done tasks in this phase
  const allTaskIds = (phase.subphases ?? []).flatMap(sp =>
    (sp.tasks ?? []).map(t => t.id)
  )
  const doneCount = allTaskIds.filter(id => {
    const r = results.find(r => r.task_id === id)
    return r?.status === 'done'
  }).length

  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-800/60 transition-colors group"
      >
        <span className="text-gray-600 text-xs w-3 shrink-0 group-hover:text-gray-400">
          {open ? '▾' : '▸'}
        </span>
        <span className="flex-1 text-sm font-medium text-gray-200 truncate">
          {phase.id ? `${phase.id} ` : ''}{phase.name}
        </span>
        {allTaskIds.length > 0 && (
          <span className="text-xs text-gray-600 shrink-0">
            {doneCount}/{allTaskIds.length}
          </span>
        )}
      </button>
      {open && (
        <div className="pl-2">
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

  const phases = plan.phases ?? []

  // Keep the phase containing the current task open by default
  const activePhaseIdx = phases.findIndex(phase =>
    (phase.subphases ?? []).some(sp =>
      (sp.tasks ?? []).some(t => t.id === currentTaskId)
    )
  )

  return (
    <div className="py-2">
      {/* Plan name header */}
      <div className="px-3 py-2 mb-1 border-b border-gray-800">
        <p className="text-xs font-semibold text-gray-300 truncate">{plan.name}</p>
        {plan.total_tasks > 0 && (
          <p className="text-xs text-gray-600 mt-0.5">
            {plan.done_tasks ?? results.filter(r => r.status === 'done').length} / {plan.total_tasks} tasks
          </p>
        )}
      </div>

      {phases.map((phase, idx) => (
        <PhaseSection
          key={phase.id ?? idx}
          phase={phase}
          currentTaskId={currentTaskId}
          results={results}
          defaultOpen={idx === 0 || idx === activePhaseIdx}
        />
      ))}
    </div>
  )
}
