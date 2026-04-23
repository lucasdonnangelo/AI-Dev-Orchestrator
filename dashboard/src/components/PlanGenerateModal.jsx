import { useState, useEffect } from 'react'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// Loading messages — rotated every 3 s while the AI generates the plan
// ---------------------------------------------------------------------------

const LOADING_MESSAGES = [
  'Claude está planejando o projeto…',
  'Gemini está revisando o plano…',
  'Refinando com base no feedback…',
  'Consolidando o plano final…',
]

// ---------------------------------------------------------------------------
// MarkdownPreview — minimal renderer for PLANO.md structure
// (no external library needed — handles h1/h2/h3, tasks, bullets)
// ---------------------------------------------------------------------------

function MarkdownPreview({ text }) {
  if (!text) return null

  return (
    <div className="space-y-0.5 text-sm leading-relaxed">
      {text.split('\n').map((line, i) => {
        if (line.startsWith('# '))
          return (
            <p key={i} className="text-indigo-300 font-bold text-base pt-3 first:pt-0 pb-0.5 border-b border-gray-800">
              {line.slice(2)}
            </p>
          )
        if (line.startsWith('## '))
          return (
            <p key={i} className="text-gray-100 font-semibold pt-2">
              {line.slice(3)}
            </p>
          )
        if (line.startsWith('### '))
          return (
            <p key={i} className="text-gray-300 font-medium pl-2 pt-1">
              {line.slice(4)}
            </p>
          )
        if (line.startsWith('- [x] ') || line.startsWith('- [X] '))
          return (
            <p key={i} className="text-gray-500 pl-6 flex items-start gap-2">
              <span className="text-green-500 shrink-0 mt-0.5">✓</span>
              <span className="line-through">{line.slice(6)}</span>
            </p>
          )
        if (line.startsWith('- [ ] '))
          return (
            <p key={i} className="text-gray-300 pl-6 flex items-start gap-2">
              <span className="text-gray-600 shrink-0 mt-0.5">○</span>
              <span>{line.slice(6)}</span>
            </p>
          )
        if (line.startsWith('- '))
          return (
            <p key={i} className="text-gray-400 pl-6 flex items-start gap-2">
              <span className="text-gray-600 shrink-0 mt-0.5">·</span>
              <span>{line.slice(2)}</span>
            </p>
          )
        if (line.trim() === '')
          return <div key={i} className="h-1.5" />
        return (
          <p key={i} className="text-gray-400 pl-2">{line}</p>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// LoadingView
// ---------------------------------------------------------------------------

function LoadingView() {
  const [msgIdx, setMsgIdx] = useState(0)

  useEffect(() => {
    const t = setInterval(
      () => setMsgIdx(i => (i + 1) % LOADING_MESSAGES.length),
      3000
    )
    return () => clearInterval(t)
  }, [])

  return (
    <div className="flex flex-col items-center justify-center py-12 gap-5">
      {/* Spinner */}
      <div className="w-10 h-10 rounded-full border-2 border-indigo-600 border-t-transparent animate-spin" />
      {/* Rotating message */}
      <div className="text-center space-y-1">
        <p className="text-sm text-gray-300 font-medium transition-all">
          {LOADING_MESSAGES[msgIdx]}
        </p>
        <p className="text-xs text-gray-600">This may take a minute…</p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PlanGenerateModal
//
// Props:
//   projects         — [{ id, name }]
//   initialProjectId — pre-selected project id
//   onClose          — fn: dismiss without saving
//   onSaved          — fn(): plan saved, reload the tree
// ---------------------------------------------------------------------------

export default function PlanGenerateModal({ projects, initialProjectId, onClose, onSaved }) {
  // ── form fields ───────────────────────────────────────────────────────────
  const [projectId,   setProjectId]   = useState(initialProjectId ?? '')
  const [description, setDescription] = useState('')
  const [stack,       setStack]       = useState('')
  const [premises,    setPremises]    = useState('')

  // ── state machine: 'form' | 'loading' | 'preview' | 'editing' ────────────
  const [phase, setPhase] = useState('form')

  // ── generated plan ────────────────────────────────────────────────────────
  const [planText,  setPlanText]  = useState('')
  const [editText,  setEditText]  = useState('')
  const [error,     setError]     = useState(null)
  const [saving,    setSaving]    = useState(false)

  // ── actions ───────────────────────────────────────────────────────────────

  async function handleGenerate() {
    if (!projectId)    { setError('Select a project.'); return }
    if (!description.trim()) { setError('Enter a description.'); return }

    setError(null)
    setPhase('loading')

    try {
      const body = {
        project_id:  projectId,
        description: description.trim(),
        ...(stack.trim()    && { stack:    stack.trim()    }),
        ...(premises.trim() && { premises: premises.trim() }),
      }
      const data = await api.post('/api/plan/generate', body)
      const text = data?.raw_md ?? ''
      setPlanText(text)
      setEditText(text)
      setPhase('preview')
    } catch (e) {
      setError(e.message ?? 'Generation failed.')
      setPhase('form')
    }
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      await api.post('/api/plan/save', {
        project_id: projectId,
        content:    planText,
      })
      onSaved()
    } catch (e) {
      setError(e.message ?? 'Failed to save plan.')
      setSaving(false)
    }
  }

  function handleEdit() {
    setEditText(planText)
    setPhase('editing')
  }

  function handleSaveEdit() {
    setPlanText(editText)
    setPhase('preview')
  }

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={e => {
        if (e.target === e.currentTarget && phase !== 'loading' && !saving) onClose()
      }}
    >
      <div className="w-full max-w-2xl bg-gray-900 border border-gray-700 rounded-2xl shadow-xl shadow-black/50 flex flex-col max-h-[90vh]">

        {/* ── Header ────────────────────────────────────────────────────── */}
        <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between shrink-0">
          <div>
            <h2 className="text-white font-semibold text-base">Generate Plan with AI</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {{
                form:    'Describe your project — Claude will plan, Gemini will review.',
                loading: 'AI is generating your plan…',
                preview: 'Review the generated plan before saving.',
                editing: 'Edit the plan directly.',
              }[phase]}
            </p>
          </div>
          {phase !== 'loading' && (
            <button
              onClick={onClose}
              disabled={saving}
              className="text-gray-600 hover:text-gray-400 text-xl leading-none transition-colors disabled:opacity-40"
            >
              ×
            </button>
          )}
        </div>

        {/* ── Body ──────────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-6 py-5">

          {/* ── FORM phase ──────────────────────────────────────────────── */}
          {phase === 'form' && (
            <div className="space-y-4">
              {/* Project */}
              <div className="space-y-1.5">
                <label className="text-xs text-gray-400">Project *</label>
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

              {/* Description */}
              <div className="space-y-1.5">
                <label className="text-xs text-gray-400">Project description *</label>
                <textarea
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  rows={4}
                  placeholder="Describe what you want to build — goals, features, constraints…"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500 resize-none"
                />
              </div>

              {/* Stack */}
              <div className="space-y-1.5">
                <label className="text-xs text-gray-400">Stack (optional)</label>
                <input
                  type="text"
                  value={stack}
                  onChange={e => setStack(e.target.value)}
                  placeholder="e.g. FastAPI + React + PostgreSQL"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Premises */}
              <div className="space-y-1.5">
                <label className="text-xs text-gray-400">Premises / constraints (optional)</label>
                <textarea
                  value={premises}
                  onChange={e => setPremises(e.target.value)}
                  rows={3}
                  placeholder="e.g. Must support multi-tenancy. No external auth services."
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500 resize-none"
                />
              </div>
            </div>
          )}

          {/* ── LOADING phase ───────────────────────────────────────────── */}
          {phase === 'loading' && <LoadingView />}

          {/* ── PREVIEW phase ───────────────────────────────────────────── */}
          {phase === 'preview' && (
            <div className="bg-gray-800/40 border border-gray-800 rounded-xl px-5 py-4 min-h-48">
              <MarkdownPreview text={planText} />
            </div>
          )}

          {/* ── EDITING phase ───────────────────────────────────────────── */}
          {phase === 'editing' && (
            <textarea
              value={editText}
              onChange={e => setEditText(e.target.value)}
              className="w-full h-96 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm text-gray-200 font-mono focus:outline-none focus:border-indigo-500 resize-none"
            />
          )}

          {/* Error */}
          {error && (
            <p className="text-red-400 text-xs mt-3 bg-red-900/20 border border-red-900/40 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>

        {/* ── Footer / Actions ──────────────────────────────────────────── */}
        <div className="px-6 py-4 border-t border-gray-800 shrink-0">

          {phase === 'form' && (
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-xl bg-gray-800 text-gray-300 text-sm hover:bg-gray-700 border border-gray-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleGenerate}
                className="flex-1 py-2 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-500 transition-colors"
              >
                Generate
              </button>
            </div>
          )}

          {phase === 'preview' && (
            <div className="flex gap-2 flex-wrap">
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex-1 py-2 rounded-xl bg-green-700 text-white text-sm font-semibold hover:bg-green-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {saving ? 'Saving…' : 'Approve and Save'}
              </button>
              <button
                onClick={handleEdit}
                disabled={saving}
                className="px-4 py-2 rounded-xl bg-gray-800 text-gray-300 text-sm hover:bg-gray-700 border border-gray-700 transition-colors disabled:opacity-40"
              >
                Edit
              </button>
              <button
                onClick={onClose}
                disabled={saving}
                className="px-4 py-2 rounded-xl bg-gray-800 text-gray-400 text-sm hover:bg-gray-700 border border-gray-700 transition-colors disabled:opacity-40"
              >
                Discard
              </button>
            </div>
          )}

          {phase === 'editing' && (
            <div className="flex gap-3">
              <button
                onClick={() => setPhase('preview')}
                className="px-4 py-2 rounded-xl bg-gray-800 text-gray-300 text-sm hover:bg-gray-700 border border-gray-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveEdit}
                className="flex-1 py-2 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-500 transition-colors"
              >
                Apply edits
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
