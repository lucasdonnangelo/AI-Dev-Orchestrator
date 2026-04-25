import { useState } from 'react'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// PlanRunModal — configuration modal to start a hierarchical plan run.
//
// Props:
//   projects         — list of registered projects [{ id, name }]
//   initialProjectId — pre-selected project id (optional)
//   onClose          — fn: close without starting
//   onStarted        — fn(planRunId): called on successful start
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// ScopeSelector
// ---------------------------------------------------------------------------

const SCOPE_OPTIONS = [
  { value: 'full',    label: 'Full plan' },
  { value: 'phase',   label: 'Phase',    placeholder: 'e.g. 1' },
  { value: 'subtask', label: 'Subfase',  placeholder: 'e.g. 1.2' },
]

function ScopeSelector({ scope, scopeId, onScopeChange, onScopeIdChange }) {
  const selected = SCOPE_OPTIONS.find(o => o.value === scope)

  return (
    <div className="space-y-2.5">
      <p className="text-xs text-gray-400">Scope</p>

      {/* Radio group */}
      <div className="flex flex-wrap gap-2">
        {SCOPE_OPTIONS.map(opt => (
          <label
            key={opt.value}
            className={[
              'flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm cursor-pointer transition-colors',
              scope === opt.value
                ? 'border-indigo-600 bg-indigo-900/30 text-indigo-300'
                : 'border-gray-700 bg-gray-800/50 text-gray-400 hover:border-gray-600',
            ].join(' ')}
          >
            <input
              type="radio"
              name="scope"
              value={opt.value}
              checked={scope === opt.value}
              onChange={() => onScopeChange(opt.value)}
              className="accent-indigo-500"
            />
            {opt.label}
          </label>
        ))}
      </div>

      {/* ID input for phase / subtask scope */}
      {scope !== 'full' && (
        <input
          type="text"
          value={scopeId}
          onChange={e => onScopeIdChange(e.target.value)}
          placeholder={selected?.placeholder ?? ''}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PlanRunModal
// ---------------------------------------------------------------------------

export default function PlanRunModal({ projects, initialProjectId, onClose, onStarted }) {
  const [projectId, setProjectId]       = useState(initialProjectId ?? '')
  const [scope, setScope]               = useState('full')
  const [scopeId, setScopeId]           = useState('')
  const [pauseSubtask, setPauseSubtask] = useState(true)
  const [pausePhase, setPausePhase]     = useState(true)
  const [autoContinue, setAutoContinue] = useState(false)
  const [submitting, setSubmitting]     = useState(false)
  const [error, setError]               = useState(null)

  // Reset scopeId when scope changes
  function handleScopeChange(newScope) {
    setScope(newScope)
    setScopeId('')
  }

  function validate() {
    if (!projectId)                           return 'Select a project.'
    if (scope !== 'full' && !scopeId.trim())  return `Enter a ${scope === 'phase' ? 'phase' : 'subfase'} ID.`
    return null
  }

  async function handleStart() {
    const validationError = validate()
    if (validationError) { setError(validationError); return }

    setSubmitting(true)
    setError(null)

    const body = {
      project_id:          projectId,
      auto_continue:       autoContinue,
      pause_after_subtask: pauseSubtask && !autoContinue,
      pause_after_phase:   pausePhase   && !autoContinue,
    }
    if (scope === 'phase'   && scopeId.trim()) body.phase   = scopeId.trim()
    if (scope === 'subtask' && scopeId.trim()) body.subtask = scopeId.trim()

    try {
      const data = await api.post('/api/plan/run', body)
      console.log('response:', data)
      console.log('navigating to /plan/' + data.plan_run_id)
      onStarted(data.plan_run_id)
    } catch (e) {
      setError(e.message ?? 'Failed to start plan run.')
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      onClick={e => { if (e.target === e.currentTarget && !submitting) onClose() }}
    >
      <div className="w-full max-w-md bg-gray-900 border border-gray-700 rounded-2xl shadow-xl shadow-black/40 p-6 space-y-5">

        {/* Title */}
        <div>
          <h2 className="text-white font-semibold text-base">Start Execution</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Configure and launch a hierarchical plan run.
          </p>
        </div>

        {/* Project selector */}
        <div className="space-y-1.5">
          <label className="text-xs text-gray-400">Project</label>
          <select
            value={projectId}
            onChange={e => setProjectId(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="">Select project…</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        {/* Scope */}
        <ScopeSelector
          scope={scope}
          scopeId={scopeId}
          onScopeChange={handleScopeChange}
          onScopeIdChange={setScopeId}
        />

        {/* Separator */}
        <div className="border-t border-gray-800" />

        {/* Pause behaviour */}
        <div className="space-y-2.5">
          <p className="text-xs text-gray-400">Pause behaviour</p>

          <label className="flex items-center gap-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={autoContinue}
              onChange={e => setAutoContinue(e.target.checked)}
              className="accent-indigo-500 w-4 h-4"
            />
            <span className="text-sm text-gray-300 group-hover:text-gray-200 transition-colors">
              Run without pauses (auto-continue)
            </span>
          </label>

          {!autoContinue && (
            <div className="pl-1 space-y-2">
              <label className="flex items-center gap-3 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={pauseSubtask}
                  onChange={e => setPauseSubtask(e.target.checked)}
                  className="accent-indigo-500 w-4 h-4"
                />
                <span className="text-sm text-gray-300 group-hover:text-gray-200 transition-colors">
                  Pause after each subfase
                </span>
              </label>
              <label className="flex items-center gap-3 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={pausePhase}
                  onChange={e => setPausePhase(e.target.checked)}
                  className="accent-indigo-500 w-4 h-4"
                />
                <span className="text-sm text-gray-300 group-hover:text-gray-200 transition-colors">
                  Pause after each phase
                </span>
              </label>
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <p className="text-red-400 text-xs bg-red-900/20 border border-red-900/40 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-1">
          <button
            onClick={onClose}
            disabled={submitting}
            className="flex-1 py-2.5 rounded-xl bg-gray-800 text-gray-300 text-sm hover:bg-gray-700 border border-gray-700 transition-colors disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            onClick={handleStart}
            disabled={submitting}
            className="flex-1 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? 'Starting…' : 'Start'}
          </button>
        </div>
      </div>
    </div>
  )
}
