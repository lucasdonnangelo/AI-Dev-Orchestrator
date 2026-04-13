import { useState } from 'react'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// Edit Plan modal — shown when run is paused
// ---------------------------------------------------------------------------

function EditPlanModal({ plan, runId, onClose, onSaved }) {
  const [text, setText] = useState(
    plan ? JSON.stringify(plan, null, 2) : ''
  )
  const [error, setError]   = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    let parsed
    try {
      parsed = JSON.parse(text)
    } catch {
      setError('Invalid JSON — fix the plan before saving.')
      return
    }
    setError('')
    setSaving(true)
    try {
      await api.post(`/api/edit-plan/${runId}`, { plan: parsed })
      onSaved()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-2xl p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-white font-semibold text-base">Edit Plan</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-lg leading-none">✕</button>
        </div>

        <p className="text-xs text-gray-500">
          Modify the JSON plan below. Changes take effect when the run resumes.
        </p>

        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          rows={16}
          spellCheck={false}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-xs font-mono text-gray-200 resize-y focus:outline-none focus:border-indigo-500 transition-colors"
        />

        {error && <p className="text-red-400 text-xs">{error}</p>}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-lg py-2 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm rounded-lg py-2 transition-colors"
          >
            {saving ? 'Saving…' : 'Save & Resume'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RunControls
// ---------------------------------------------------------------------------

export default function RunControls({ runId, runStatus, currentPlan, onStatusChange }) {
  const [showEditPlan, setShowEditPlan] = useState(false)
  const [loading, setLoading] = useState(null)  // 'pause'|'resume'|'cancel'|null

  const isRunning  = runStatus === 'running'
  const isPaused   = runStatus === 'paused'
  const isTerminal = ['approved', 'escalated', 'cancelled', 'error', 'done'].includes(runStatus)

  if (isTerminal) return null

  async function action(name, endpoint) {
    setLoading(name)
    try {
      await api.post(endpoint)
      onStatusChange?.()
    } catch {
      // Errors are visible via WS status; silence here.
    } finally {
      setLoading(null)
    }
  }

  return (
    <>
      <div className="flex gap-2 flex-wrap">
        {isRunning && (
          <button
            onClick={() => action('pause', `/api/pause/${runId}`)}
            disabled={loading === 'pause'}
            className="bg-yellow-900/50 hover:bg-yellow-800/60 border border-yellow-800 text-yellow-300 text-xs px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
          >
            {loading === 'pause' ? 'Pausing…' : '⏸ Pause'}
          </button>
        )}

        {isPaused && (
          <>
            <button
              onClick={() => action('resume', `/api/resume/${runId}`)}
              disabled={loading === 'resume'}
              className="bg-green-900/50 hover:bg-green-800/60 border border-green-800 text-green-300 text-xs px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
            >
              {loading === 'resume' ? 'Resuming…' : '▶ Resume'}
            </button>

            <button
              onClick={() => setShowEditPlan(true)}
              className="bg-indigo-900/50 hover:bg-indigo-800/60 border border-indigo-800 text-indigo-300 text-xs px-3 py-1.5 rounded-lg transition-colors"
            >
              ✎ Edit Plan
            </button>
          </>
        )}

        <button
          onClick={() => action('cancel', `/api/cancel/${runId}`)}
          disabled={loading === 'cancel'}
          className="bg-red-900/30 hover:bg-red-900/50 border border-red-900 text-red-400 text-xs px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
        >
          {loading === 'cancel' ? 'Cancelling…' : '✕ Cancel'}
        </button>
      </div>

      {showEditPlan && (
        <EditPlanModal
          plan={currentPlan}
          runId={runId}
          onClose={() => setShowEditPlan(false)}
          onSaved={() => {}}
        />
      )}
    </>
  )
}
