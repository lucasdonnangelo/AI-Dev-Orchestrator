import { useState } from 'react'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const COMPLEXITY_STYLE = {
  low:    'bg-green-900/40 text-green-400 border-green-800',
  medium: 'bg-yellow-900/40 text-yellow-400 border-yellow-800',
  high:   'bg-red-900/40 text-red-400 border-red-800',
}

function ComplexityBadge({ value }) {
  if (!value) return null
  const normalized = value.toLowerCase()
  const cls = COMPLEXITY_STYLE[normalized] ?? 'bg-gray-800 text-gray-400 border-gray-700'
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${cls}`}>
      {value}
    </span>
  )
}

function SectionLabel({ children }) {
  return (
    <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-2">{children}</h3>
  )
}

// ---------------------------------------------------------------------------
// Plan display view
// ---------------------------------------------------------------------------

function PlanView({ plan }) {
  const filesToCreate = plan.files_to_create ?? []
  const filesToModify = plan.files_to_modify ?? []
  const steps         = plan.steps ?? []
  const criteria      = plan.acceptance_criteria ?? []

  return (
    <div className="space-y-5">
      {/* Description */}
      {plan.description && (
        <div>
          <SectionLabel>Description</SectionLabel>
          <p className="text-sm text-gray-300 leading-relaxed">{plan.description}</p>
        </div>
      )}

      {/* Steps */}
      {steps.length > 0 && (
        <div>
          <SectionLabel>Steps</SectionLabel>
          <ol className="space-y-1.5">
            {steps.map((step, i) => (
              <li key={i} className="flex gap-3 text-sm text-gray-300">
                <span className="text-indigo-400 font-mono shrink-0 w-5 text-right">{i + 1}.</span>
                <span className="leading-relaxed">{step}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Files */}
      {(filesToCreate.length > 0 || filesToModify.length > 0) && (
        <div>
          <SectionLabel>Files</SectionLabel>
          <ul className="space-y-1">
            {filesToCreate.map((f, i) => (
              <li key={`c${i}`} className="flex items-center gap-2 text-xs font-mono">
                <span className="text-green-500">+</span>
                <span className="text-gray-400">{f}</span>
              </li>
            ))}
            {filesToModify.map((f, i) => (
              <li key={`m${i}`} className="flex items-center gap-2 text-xs font-mono">
                <span className="text-yellow-500">~</span>
                <span className="text-gray-400">{f}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Acceptance criteria */}
      {criteria.length > 0 && (
        <div>
          <SectionLabel>Acceptance criteria</SectionLabel>
          <ul className="space-y-1.5">
            {criteria.map((c, i) => (
              <li key={i} className="flex gap-2 text-sm text-gray-300">
                <span className="text-gray-600 shrink-0">□</span>
                <span className="leading-relaxed">{c}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inline JSON editor (shown when paused)
// ---------------------------------------------------------------------------

function InlineEditor({ plan, runId, onSaved }) {
  const [text, setText]   = useState(JSON.stringify(plan, null, 2))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    let parsed
    try { parsed = JSON.parse(text) }
    catch { setError('Invalid JSON — fix before saving.'); return }
    setError('')
    setSaving(true)
    try {
      await api.post(`/api/edit-plan/${runId}`, { plan: parsed })
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-yellow-400">
        Run is paused. Edit the plan JSON below and click Save to resume.
      </p>
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        rows={18}
        spellCheck={false}
        className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-xs font-mono text-gray-200 resize-y focus:outline-none focus:border-indigo-500 transition-colors"
      />
      {error && <p className="text-red-400 text-xs">{error}</p>}
      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm rounded-lg py-2 transition-colors"
      >
        {saving ? 'Saving…' : 'Save & Resume'}
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Critic round history
// ---------------------------------------------------------------------------

function CriticHistory({ criticEvents }) {
  const rounds = criticEvents.filter(e =>
    e.type === 'critic_round' || e.type === 'critic_consensus'
  )
  if (!rounds.length) return null

  return (
    <div>
      <SectionLabel>Critic history</SectionLabel>
      <div className="space-y-3">
        {rounds.map((evt, i) => {
          const d = evt.data ?? {}
          const isConsensus = evt.type === 'critic_consensus'
          return (
            <div
              key={i}
              className={[
                'rounded-lg border p-3 text-xs space-y-2',
                isConsensus
                  ? 'bg-green-900/20 border-green-800'
                  : 'bg-gray-800 border-gray-700',
              ].join(' ')}
            >
              {/* Header */}
              <div className="flex items-center gap-2">
                <span className="text-gray-300 font-medium">
                  Round {d.round}
                </span>
                <span className={[
                  'px-1.5 py-0.5 rounded text-xs',
                  d.score >= 8 ? 'bg-green-900/50 text-green-400'
                    : d.score >= 6 ? 'bg-yellow-900/50 text-yellow-400'
                    : 'bg-red-900/50 text-red-400',
                ].join(' ')}>
                  {d.score}/10
                </span>
                {isConsensus && (
                  <span className="text-green-400 ml-auto">Consensus</span>
                )}
                {!isConsensus && (
                  <span className={`ml-auto ${d.consensus ? 'text-green-400' : 'text-gray-500'}`}>
                    {d.consensus ? 'Consensus' : 'No consensus'}
                  </span>
                )}
              </div>

              {/* Observations */}
              {(d.observations ?? []).length > 0 && (
                <div>
                  <p className="text-gray-500 mb-1">Observations</p>
                  <ul className="space-y-0.5">
                    {d.observations.map((obs, j) => (
                      <li key={j} className="text-gray-400 leading-relaxed">· {obs}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Suggestions */}
              {(d.suggestions ?? []).length > 0 && (
                <div>
                  <p className="text-gray-500 mb-1">Suggestions</p>
                  <ul className="space-y-0.5">
                    {d.suggestions.map((s, j) => (
                      <li key={j} className="text-gray-400 leading-relaxed">→ {s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PlanPanel
// ---------------------------------------------------------------------------

export default function PlanPanel({ plan, criticEvents, runId, runStatus }) {
  const [showEditor, setShowEditor] = useState(false)
  const [collapsed, setCollapsed]   = useState(false)

  if (!plan) return null

  const isPaused = runStatus === 'paused'

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* Panel header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800">
        <button
          onClick={() => setCollapsed(v => !v)}
          className="flex items-center gap-2 flex-1 text-left"
        >
          <span className="text-sm font-medium text-gray-200">Plan</span>
          <ComplexityBadge value={plan.estimated_complexity} />
          <span className="text-gray-600 text-xs ml-auto">{collapsed ? '▼' : '▲'}</span>
        </button>

        {isPaused && !collapsed && (
          <button
            onClick={() => setShowEditor(v => !v)}
            className={[
              'text-xs px-2.5 py-1 rounded-lg border transition-colors',
              showEditor
                ? 'bg-indigo-600 border-indigo-500 text-white'
                : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-white',
            ].join(' ')}
          >
            {showEditor ? 'View' : '✎ Edit'}
          </button>
        )}
      </div>

      {/* Panel body */}
      {!collapsed && (
        <div className="px-4 py-4 space-y-5">
          {isPaused && showEditor
            ? <InlineEditor
                plan={plan}
                runId={runId}
                onSaved={() => setShowEditor(false)}
              />
            : <PlanView plan={plan} />
          }

          {/* Critic history always visible (unless editing) */}
          {!(isPaused && showEditor) && (
            <CriticHistory criticEvents={criticEvents} />
          )}
        </div>
      )}
    </div>
  )
}
