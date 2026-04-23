import { useState } from 'react'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// PlanRunModal — configuration modal to start a hierarchical plan run.
// Stub implementation — will be expanded in Phase 7.2.6.
// ---------------------------------------------------------------------------

export default function PlanRunModal({ projects, initialProjectId, onClose, onStarted }) {
  const [projectId, setProjectId]       = useState(initialProjectId ?? '')
  const [pauseSubtask, setPauseSubtask] = useState(true)
  const [pausePhase, setPausePhase]     = useState(true)
  const [autoContinue, setAutoContinue] = useState(false)
  const [submitting, setSubmitting]     = useState(false)
  const [error, setError]               = useState(null)

  async function handleStart() {
    if (!projectId) { setError('Select a project.'); return }
    setSubmitting(true)
    setError(null)
    try {
      const data = await api.post('/api/plan/run', {
        project_id:          projectId,
        auto_continue:       autoContinue,
        pause_after_subtask: pauseSubtask && !autoContinue,
        pause_after_phase:   pausePhase   && !autoContinue,
      })
      onStarted(data.plan_run_id)
    } catch (e) {
      setError(e.message ?? 'Failed to start plan run.')
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="w-full max-w-md bg-gray-900 border border-gray-700 rounded-2xl p-6 space-y-5">
        <h2 className="text-white font-semibold text-base">Start Execution</h2>

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

        {/* Pause behaviour */}
        <div className="space-y-2.5">
          <p className="text-xs text-gray-400">Pause behaviour</p>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={autoContinue}
              onChange={e => setAutoContinue(e.target.checked)}
              className="accent-indigo-500 w-4 h-4"
            />
            <span className="text-sm text-gray-300">Run without pauses (auto-continue)</span>
          </label>
          {!autoContinue && (
            <div className="pl-1 space-y-2">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={pauseSubtask}
                  onChange={e => setPauseSubtask(e.target.checked)}
                  className="accent-indigo-500 w-4 h-4"
                />
                <span className="text-sm text-gray-300">Pause after each subfase</span>
              </label>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={pausePhase}
                  onChange={e => setPausePhase(e.target.checked)}
                  className="accent-indigo-500 w-4 h-4"
                />
                <span className="text-sm text-gray-300">Pause after each phase</span>
              </label>
            </div>
          )}
        </div>

        {error && <p className="text-red-400 text-xs">{error}</p>}

        {/* Actions */}
        <div className="flex gap-3 pt-1">
          <button
            onClick={onClose}
            disabled={submitting}
            className="flex-1 py-2 rounded-lg bg-gray-800 text-gray-300 text-sm hover:bg-gray-700 border border-gray-700 transition-colors disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            onClick={handleStart}
            disabled={submitting || !projectId}
            className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? 'Starting…' : 'Start'}
          </button>
        </div>
      </div>
    </div>
  )
}
