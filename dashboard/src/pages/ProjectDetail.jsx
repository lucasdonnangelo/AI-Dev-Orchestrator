import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import Layout from '../components/Layout'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STACK_COLORS = {
  python: 'bg-blue-900/50 text-blue-400 border-blue-800',
  node:   'bg-green-900/50 text-green-400 border-green-800',
  go:     'bg-cyan-900/50 text-cyan-400 border-cyan-800',
  rust:   'bg-orange-900/50 text-orange-400 border-orange-800',
  java:   'bg-red-900/50 text-red-400 border-red-800',
  ruby:   'bg-pink-900/50 text-pink-400 border-pink-800',
  php:    'bg-indigo-900/50 text-indigo-400 border-indigo-800',
}

const STATUS_STYLES = {
  approved:  'bg-green-900/60 text-green-400',
  escalated: 'bg-red-900/60 text-red-400',
  running:   'bg-blue-900/60 text-blue-400',
  paused:    'bg-yellow-900/60 text-yellow-400',
  cancelled: 'bg-gray-800 text-gray-500',
  error:     'bg-red-900/60 text-red-400',
}

const TABS = ['Overview', 'Config', 'History']

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StackBadge({ stack }) {
  const cls = STACK_COLORS[stack] ?? 'bg-gray-800 text-gray-400 border-gray-700'
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${cls}`}>{stack}</span>
  )
}

function SectionTitle({ children }) {
  return (
    <h2 className="text-xs text-gray-500 uppercase tracking-wider mb-3">{children}</h2>
  )
}

// ---------------------------------------------------------------------------
// Tab: Overview
// ---------------------------------------------------------------------------

function OverviewTab({ projectId, project }) {
  const navigate = useNavigate()
  const [readme, setReadme] = useState(null)   // null = loading
  const [tree, setTree]     = useState(null)
  const [task, setTask]     = useState('')
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')

  useEffect(() => {
    api.get(`/api/projects/${projectId}/readme`)
      .then(d => setReadme(d.content))
      .catch(() => setReadme(''))
    api.get(`/api/projects/${projectId}/tree`)
      .then(d => setTree(d.content))
      .catch(() => setTree(''))
  }, [projectId])

  async function handleRun(e) {
    e.preventDefault()
    if (!task.trim()) return
    setRunError('')
    setRunning(true)
    try {
      const { run_id } = await api.post('/api/run', {
        task: task.trim(),
        project_dir: project.path,
      })
      navigate(`/run/${run_id}`)
    } catch (err) {
      setRunError(err.message)
      setRunning(false)
    }
  }

  return (
    <div className="space-y-6">

      {/* Quick Run */}
      <section>
        <SectionTitle>Quick Run</SectionTitle>
        <form
          onSubmit={handleRun}
          className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3"
        >
          <textarea
            value={task}
            onChange={e => setTask(e.target.value)}
            placeholder="Describe the task to execute in this project…"
            rows={3}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 resize-none focus:outline-none focus:border-indigo-500 transition-colors leading-relaxed"
          />
          {runError && <p className="text-red-400 text-xs">{runError}</p>}
          <button
            type="submit"
            disabled={running || !task.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm rounded-lg px-5 py-2 transition-colors"
          >
            {running ? 'Starting…' : 'Execute'}
          </button>
        </form>
      </section>

      {/* README + Tree */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* README */}
        <section>
          <SectionTitle>README</SectionTitle>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 h-72 overflow-auto">
            {readme === null ? (
              <div className="animate-pulse space-y-2">
                <div className="h-3 bg-gray-800 rounded w-3/4" />
                <div className="h-3 bg-gray-800 rounded w-1/2" />
                <div className="h-3 bg-gray-800 rounded w-5/6" />
              </div>
            ) : readme === '' ? (
              <p className="text-gray-600 text-xs">No README found in this project.</p>
            ) : (
              <pre className="text-xs text-gray-300 whitespace-pre-wrap leading-relaxed font-mono">
                {readme}
              </pre>
            )}
          </div>
        </section>

        {/* Directory tree */}
        <section>
          <SectionTitle>Structure</SectionTitle>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 h-72 overflow-auto">
            {tree === null ? (
              <div className="animate-pulse space-y-1">
                {[80, 60, 70, 50, 65].map((w, i) => (
                  <div key={i} className="h-3 bg-gray-800 rounded" style={{ width: `${w}%` }} />
                ))}
              </div>
            ) : tree === '' ? (
              <p className="text-gray-600 text-xs">No structure available.</p>
            ) : (
              <pre className="text-xs text-gray-400 leading-relaxed font-mono whitespace-pre">
                {tree}
              </pre>
            )}
          </div>
        </section>

      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Config — constants & helpers
// ---------------------------------------------------------------------------

const CFG_DEFAULTS = {
  planner_provider:        'anthropic',
  critic_provider:         'google',
  reviewer_provider:       'google',
  decisor_provider:        'google',
  google_model:            'gemini-2.5-flash',
  openai_model:            'gpt-4o-mini',
  critic_min_rounds:       2,
  critic_max_rounds:       5,
  max_retries:             3,
  git_auto_branch:         false,
  git_conventional_commits: true,
}

const PROVIDERS    = ['anthropic', 'google', 'openai']
const PROMPT_ROLES = ['planner', 'critic', 'reviewer', 'decisor']

function defaultForm() {
  return {
    ...CFG_DEFAULTS,
    prompts: { planner: '', critic: '', reviewer: '', decisor: '' },
  }
}

function formFromFields(yamlFields) {
  const f = defaultForm()
  for (const k of Object.keys(CFG_DEFAULTS)) {
    if (yamlFields[k] !== undefined) f[k] = yamlFields[k]
  }
  const p = yamlFields.prompts || {}
  f.prompts = {
    planner:  p.planner  ?? '',
    critic:   p.critic   ?? '',
    reviewer: p.reviewer ?? '',
    decisor:  p.decisor  ?? '',
  }
  return f
}

function formToYaml(f) {
  const lines = []
  for (const [k, def] of Object.entries(CFG_DEFAULTS)) {
    const v = f[k]
    if (v !== def) {
      lines.push(typeof v === 'boolean' ? `${k}: ${v}` : `${k}: ${v}`)
    }
  }
  const nonEmpty = PROMPT_ROLES.filter(r => f.prompts[r]?.trim())
  if (nonEmpty.length) {
    lines.push('prompts:')
    for (const role of nonEmpty) {
      const text = f.prompts[role].trim()
      if (text.includes('\n')) {
        lines.push(`  ${role}: |`)
        text.split('\n').forEach(l => lines.push(`    ${l}`))
      } else {
        lines.push(`  ${role}: "${text.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`)
      }
    }
  }
  return lines.length ? lines.join('\n') + '\n' : ''
}

// ---------------------------------------------------------------------------
// Config sub-components
// ---------------------------------------------------------------------------

function CfgSelect({ label, field: fld, value, onChange }) {
  const isDefault = value === CFG_DEFAULTS[fld]
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      <select
        value={value}
        onChange={e => onChange(fld, e.target.value)}
        className={`w-full bg-gray-800 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors border ${isDefault ? 'border-gray-700' : 'border-indigo-600'}`}
      >
        {PROVIDERS.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

function CfgText({ label, field: fld, value, onChange, placeholder }) {
  const isDefault = value === CFG_DEFAULTS[fld]
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      <input
        type="text"
        value={value}
        onChange={e => onChange(fld, e.target.value)}
        placeholder={placeholder}
        className={`w-full bg-gray-800 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 transition-colors border ${isDefault ? 'border-gray-700' : 'border-indigo-600'}`}
      />
    </div>
  )
}

function CfgNumber({ label, field: fld, value, min, max, onChange }) {
  const isDefault = value === CFG_DEFAULTS[fld]
  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={e => onChange(fld, Number(e.target.value))}
        className={`w-full bg-gray-800 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors border ${isDefault ? 'border-gray-700' : 'border-indigo-600'}`}
      />
    </div>
  )
}

function CfgToggle({ label, field: fld, value, onChange }) {
  const isDefault = value === CFG_DEFAULTS[fld]
  return (
    <label className="flex items-center justify-between cursor-pointer">
      <span className={`text-sm ${isDefault ? 'text-gray-400' : 'text-white'}`}>{label}</span>
      <button
        type="button"
        onClick={() => onChange(fld, !value)}
        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${value ? 'bg-indigo-600' : 'bg-gray-700'}`}
      >
        <span
          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${value ? 'translate-x-4' : 'translate-x-1'}`}
        />
      </button>
    </label>
  )
}

function CfgSection({ title, children }) {
  return (
    <div>
      <p className="text-xs text-gray-600 uppercase tracking-wider mb-3">{title}</p>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Visual editor
// ---------------------------------------------------------------------------

function VisualEditor({ form, onChange }) {
  function set(fld, val) { onChange(fld, val) }
  function setPrompt(role, val) { onChange('prompts', { ...form.prompts, [role]: val }) }

  return (
    <div className="space-y-6">

      <CfgSection title="Providers">
        <div className="grid grid-cols-2 gap-3">
          <CfgSelect label="Planner"  field="planner_provider"  value={form.planner_provider}  onChange={set} />
          <CfgSelect label="Critic"   field="critic_provider"   value={form.critic_provider}   onChange={set} />
          <CfgSelect label="Reviewer" field="reviewer_provider" value={form.reviewer_provider} onChange={set} />
          <CfgSelect label="Decisor"  field="decisor_provider"  value={form.decisor_provider}  onChange={set} />
        </div>
      </CfgSection>

      <CfgSection title="Models">
        <div className="grid grid-cols-2 gap-3">
          <CfgText label="Google model"  field="google_model"  value={form.google_model}  onChange={set} placeholder="gemini-2.5-flash" />
          <CfgText label="OpenAI model"  field="openai_model"  value={form.openai_model}  onChange={set} placeholder="gpt-4o-mini" />
        </div>
      </CfgSection>

      <CfgSection title="Critic loop">
        <div className="grid grid-cols-2 gap-3">
          <CfgNumber label="Min rounds" field="critic_min_rounds" value={form.critic_min_rounds} min={1} max={10} onChange={set} />
          <CfgNumber label="Max rounds" field="critic_max_rounds" value={form.critic_max_rounds} min={1} max={10} onChange={set} />
        </div>
      </CfgSection>

      <CfgSection title="Execution">
        <div className="w-48">
          <CfgNumber label="Max retries" field="max_retries" value={form.max_retries} min={1} max={10} onChange={set} />
        </div>
      </CfgSection>

      <CfgSection title="Git">
        <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 space-y-3">
          <CfgToggle label="Auto-create branch per task" field="git_auto_branch"         value={form.git_auto_branch}         onChange={set} />
          <CfgToggle label="Conventional commit messages" field="git_conventional_commits" value={form.git_conventional_commits} onChange={set} />
        </div>
      </CfgSection>

      <CfgSection title="Prompt overrides">
        <p className="text-xs text-gray-600 mb-3">
          Text appended to (or replacing) the built-in system prompt for each agent.
          Leave blank to use the default prompt.
        </p>
        <div className="space-y-3">
          {PROMPT_ROLES.map(role => (
            <div key={role}>
              <label className="block text-xs text-gray-500 capitalize mb-1">{role}</label>
              <textarea
                value={form.prompts[role]}
                onChange={e => setPrompt(role, e.target.value)}
                rows={3}
                placeholder={`Custom system prompt for ${role} (or leave blank for default)`}
                spellCheck={false}
                className={`w-full bg-gray-800 rounded-lg px-3 py-2 text-xs text-gray-300 font-mono resize-none focus:outline-none focus:border-indigo-500 transition-colors leading-relaxed border ${form.prompts[role]?.trim() ? 'border-indigo-600' : 'border-gray-700'}`}
              />
            </div>
          ))}
        </div>
      </CfgSection>

    </div>
  )
}

// ---------------------------------------------------------------------------
// Resolved config preview
// ---------------------------------------------------------------------------

function ResolvedPreview({ projectId }) {
  const [resolved,    setResolved]    = useState(null)
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState('')
  const [expanded,    setExpanded]    = useState({})
  const [showPanel,   setShowPanel]   = useState(false)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const data = await api.get(`/api/projects/${projectId}/resolved-config`)
      setResolved(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function togglePrompt(role) {
    setExpanded(prev => ({ ...prev, [role]: !prev[role] }))
  }

  function handleOpen() {
    setShowPanel(true)
    load()
  }

  function srcBadge(key, val) {
    const isDefault = String(val) === String(CFG_DEFAULTS[key])
    return isDefault
      ? <span className="text-xs text-gray-600">default</span>
      : <span className="text-xs text-indigo-400">project</span>
  }

  const CONFIG_ROWS = [
    ['planner_provider',        'Planner provider'],
    ['critic_provider',         'Critic provider'],
    ['reviewer_provider',       'Reviewer provider'],
    ['decisor_provider',        'Decisor provider'],
    ['google_model',            'Google model'],
    ['openai_model',            'OpenAI model'],
    ['critic_min_rounds',       'Critic min rounds'],
    ['critic_max_rounds',       'Critic max rounds'],
    ['max_retries',             'Max retries'],
    ['git_auto_branch',         'Git auto branch'],
    ['git_conventional_commits','Conventional commits'],
  ]

  return (
    <div className="border-t border-gray-800 pt-4">
      {!showPanel ? (
        <button
          onClick={handleOpen}
          className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
        >
          Preview resolved config (3 layers) ›
        </button>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-500 uppercase tracking-wider">Resolved config (defaults + project + env)</p>
            <button onClick={() => { setShowPanel(false); setResolved(null) }} className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
              Hide
            </button>
          </div>

          {loading && (
            <div className="animate-pulse space-y-2">
              {[1,2,3].map(i => <div key={i} className="h-3 bg-gray-800 rounded w-2/3" />)}
            </div>
          )}

          {error && <p className="text-xs text-red-400">{error}</p>}

          {resolved && (
            <div className="space-y-4">
              {/* Fields table */}
              <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="text-left text-xs text-gray-600 px-4 py-2 font-normal">Field</th>
                      <th className="text-left text-xs text-gray-600 px-4 py-2 font-normal">Resolved value</th>
                      <th className="text-left text-xs text-gray-600 px-4 py-2 font-normal">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {CONFIG_ROWS.map(([key, label]) => (
                      <tr key={key} className="hover:bg-gray-800/30 transition-colors">
                        <td className="px-4 py-2 text-xs text-gray-500 font-mono">{key}</td>
                        <td className="px-4 py-2 text-xs text-white">{String(resolved[key])}</td>
                        <td className="px-4 py-2">{srcBadge(key, resolved[key])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* System prompts */}
              <div>
                <p className="text-xs text-gray-600 mb-2">Active system prompts</p>
                <div className="space-y-2">
                  {PROMPT_ROLES.map(role => {
                    const text   = resolved.resolved_prompts?.[role] ?? ''
                    const isOpen = expanded[role]
                    const hasOverride = !!resolved.prompt_overrides?.[role]
                    return (
                      <div key={role} className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                        <button
                          onClick={() => togglePrompt(role)}
                          className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-gray-800/40 transition-colors"
                        >
                          <span className="text-xs text-gray-300 capitalize font-medium">{role}</span>
                          <div className="flex items-center gap-2">
                            {hasOverride && (
                              <span className="text-xs text-indigo-400">override active</span>
                            )}
                            <span className="text-xs text-gray-600">{text.length} chars</span>
                            <span className="text-xs text-gray-600">{isOpen ? '▲' : '▼'}</span>
                          </div>
                        </button>
                        {isOpen && (
                          <pre className="px-4 pb-4 text-xs text-gray-400 font-mono whitespace-pre-wrap leading-relaxed max-h-72 overflow-auto border-t border-gray-800">
                            {text}
                          </pre>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Config
// ---------------------------------------------------------------------------

function ConfigTab({ projectId }) {
  const [mode,    setMode]    = useState('visual')  // 'visual' | 'raw'
  const [form,    setForm]    = useState(null)       // null = loading
  const [raw,     setRaw]     = useState(null)       // raw YAML string
  const [found,   setFound]   = useState(false)
  const [dirty,   setDirty]   = useState(false)
  const [saving,  setSaving]  = useState(false)
  const [saved,   setSaved]   = useState(false)
  const [error,   setError]   = useState('')
  const [switching, setSwitching] = useState(false)

  // ---- initial load --------------------------------------------------------

  useEffect(() => {
    api.get(`/api/projects/${projectId}/config`)
      .then(d => {
        setRaw(d.content)
        setFound(d.found)
        setForm(formFromFields(d.fields || {}))
      })
      .catch(() => {
        setRaw('')
        setFound(false)
        setForm(defaultForm())
      })
  }, [projectId])

  // ---- helpers -------------------------------------------------------------

  function handleFormChange(fld, val) {
    setForm(prev => ({ ...prev, [fld]: val }))
    setDirty(true)
    setSaved(false)
  }

  async function switchToRaw() {
    if (mode === 'raw') return
    setRaw(formToYaml(form))
    setMode('raw')
  }

  async function switchToVisual() {
    if (mode === 'visual') return
    setSwitching(true)
    try {
      const d = await api.post(`/api/projects/${projectId}/config-parse`, { content: raw })
      setForm(formFromFields(d.fields || {}))
      setMode('visual')
    } catch (err) {
      setError(`Cannot switch: ${err.message}`)
    } finally {
      setSwitching(false)
    }
  }

  async function handleSave() {
    const content = mode === 'visual' ? formToYaml(form) : raw
    setSaving(true)
    setSaved(false)
    setError('')
    try {
      await api.put(`/api/projects/${projectId}/config`, { content })
      setFound(true)
      setDirty(false)
      setSaved(true)
      // Keep raw in sync after visual save
      if (mode === 'visual') setRaw(content)
      setTimeout(() => setSaved(false), 2500)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // ---- loading skeleton ----------------------------------------------------

  if (form === null) {
    return (
      <div className="max-w-2xl animate-pulse space-y-3">
        <div className="h-4 bg-gray-800 rounded w-1/3" />
        <div className="h-32 bg-gray-900 border border-gray-800 rounded-xl" />
      </div>
    )
  }

  // ---- render --------------------------------------------------------------

  return (
    <div className="max-w-2xl space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-white font-medium font-mono">.orchestrator.yaml</p>
          <p className="text-xs text-gray-600 mt-0.5">
            {found ? 'Loaded from project directory.' : 'File not found — save to create it.'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Mode toggle */}
          <div className="flex bg-gray-900 border border-gray-800 rounded-lg p-0.5 text-xs">
            <button
              onClick={switchToVisual}
              disabled={switching}
              className={`px-3 py-1 rounded-md transition-colors ${mode === 'visual' ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300'}`}
            >
              Visual
            </button>
            <button
              onClick={switchToRaw}
              className={`px-3 py-1 rounded-md transition-colors ${mode === 'raw' ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300'}`}
            >
              Raw YAML
            </button>
          </div>

          {saved  && <span className="text-xs text-green-400">Saved!</span>}
          {error  && <span className="text-xs text-red-400 truncate max-w-xs">{error}</span>}

          <button
            onClick={handleSave}
            disabled={saving || (!dirty && found)}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs rounded-lg px-4 py-1.5 transition-colors"
          >
            {saving ? 'Saving…' : dirty ? 'Save *' : 'Save'}
          </button>
        </div>
      </div>

      {/* Editor */}
      {mode === 'visual' ? (
        <VisualEditor form={form} onChange={handleFormChange} />
      ) : (
        <textarea
          value={raw}
          onChange={e => { setRaw(e.target.value); setDirty(true); setSaved(false) }}
          rows={22}
          spellCheck={false}
          placeholder={
            '# .orchestrator.yaml — project-level config overrides\n' +
            '# planner_provider: anthropic\n' +
            '# critic_provider: google\n' +
            '# google_model: gemini-2.5-flash\n' +
            '# critic_min_rounds: 2\n' +
            '# critic_max_rounds: 5\n' +
            '# max_retries: 3\n'
          }
          className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-xs text-gray-300 font-mono resize-none focus:outline-none focus:border-indigo-500 transition-colors leading-relaxed"
        />
      )}

      {/* Hint about non-default highlight */}
      {mode === 'visual' && (
        <p className="text-xs text-gray-700">
          Fields with an <span className="text-indigo-500">indigo border</span> differ from the default value
          and will be written to the YAML on save.
        </p>
      )}

      {/* Resolved config preview */}
      <ResolvedPreview projectId={projectId} />

    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: History
// ---------------------------------------------------------------------------

function HistoryTab() {
  const [runs, setRuns] = useState(null)

  useEffect(() => {
    api.get('/api/history?limit=50')
      .then(setRuns)
      .catch(() => setRuns([]))
  }, [])

  if (runs === null) {
    return (
      <div className="animate-pulse space-y-2">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-10 bg-gray-900 border border-gray-800 rounded-lg" />
        ))}
      </div>
    )
  }

  if (runs.length === 0) {
    return <p className="text-gray-600 text-sm py-8 text-center">No runs recorded yet.</p>
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-700">
        Showing recent runs across all projects.
        Per-project filtering will be available in Phase 5.5.
      </p>
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left text-xs text-gray-500 px-4 py-3 font-normal">Task</th>
              <th className="text-left text-xs text-gray-500 px-4 py-3 font-normal">Status</th>
              <th className="text-left text-xs text-gray-500 px-4 py-3 font-normal">Date</th>
              <th className="text-left text-xs text-gray-500 px-4 py-3 font-normal">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {runs.map((run, i) => {
              const date = run.started_at
                ? new Date(run.started_at).toLocaleString(undefined, {
                    month: 'short', day: 'numeric',
                    hour: '2-digit', minute: '2-digit',
                  })
                : '—'
              const score = run.review?.score != null
                ? run.review.score.toFixed(1)
                : '—'
              const cls = STATUS_STYLES[run.status] ?? 'bg-gray-800 text-gray-400'

              return (
                <tr key={i} className="hover:bg-gray-800/40 transition-colors">
                  <td
                    className="px-4 py-3 text-gray-300 text-xs truncate max-w-xs"
                    title={run.task}
                  >
                    {run.task}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${cls}`}>
                      {run.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600 text-xs whitespace-nowrap">{date}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{score}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ProjectDetail page
// ---------------------------------------------------------------------------

export default function ProjectDetail() {
  const { projectId } = useParams()
  const navigate      = useNavigate()

  const [project,   setProject]   = useState(null)
  const [stackInfo, setStackInfo] = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [notFound,  setNotFound]  = useState(false)
  const [tab,       setTab]       = useState('Overview')

  // Load project + stack info on mount
  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.get('/api/projects'),
      api.get(`/api/projects/${projectId}/info`).catch(() => null),
    ])
      .then(([projects, info]) => {
        const found = projects.find(p => p.id === projectId)
        if (!found) { setNotFound(true); return }
        setProject(found)
        setStackInfo(info)
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false))
  }, [projectId])

  // ---- loading state -------------------------------------------------------

  if (loading) {
    return (
      <Layout>
        <div className="flex-1 p-6 space-y-4">
          <div className="h-3 bg-gray-800 rounded w-16 animate-pulse" />
          <div className="h-6 bg-gray-800 rounded w-1/3 animate-pulse" />
          <div className="h-4 bg-gray-800 rounded w-1/2 animate-pulse" />
        </div>
      </Layout>
    )
  }

  if (notFound || !project) {
    return (
      <Layout>
        <div className="flex-1 p-6">
          <button
            onClick={() => navigate('/projects')}
            className="text-indigo-400 hover:text-indigo-300 text-sm mb-4 block transition-colors"
          >
            ← Back to Projects
          </button>
          <p className="text-red-400 text-sm">Project not found.</p>
        </div>
      </Layout>
    )
  }

  const stacks = stackInfo?.stack ?? []

  // ---- main render ---------------------------------------------------------

  return (
    <Layout>
      <div className="flex-1 flex flex-col">

        {/* Project header */}
        <div className="border-b border-gray-800 px-6 pt-5 pb-0">
          <button
            onClick={() => navigate('/projects')}
            className="text-xs text-indigo-400 hover:text-indigo-300 mb-3 inline-flex items-center gap-1 transition-colors"
          >
            ← Projects
          </button>

          <div className="mb-3">
            <h1 className="text-white font-semibold text-lg leading-tight mb-1">
              {project.name}
            </h1>
            <p
              className="text-gray-600 text-xs truncate max-w-xl"
              title={project.path}
            >
              {project.path}
            </p>
          </div>

          {/* Stack badges */}
          {stacks.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-3">
              {stacks.map(s => <StackBadge key={s} stack={s} />)}
            </div>
          )}
          {stackInfo?.path_exists === false && (
            <p className="text-red-500 text-xs mb-3">
              Warning: project path does not exist on disk.
            </p>
          )}

          {/* Tabs */}
          <div className="flex gap-1 -mb-px">
            {TABS.map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm rounded-t-md transition-colors border-b-2 ${
                  tab === t
                    ? 'text-white border-indigo-500 bg-gray-900/40'
                    : 'text-gray-500 border-transparent hover:text-gray-300 hover:bg-gray-900/30'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        <div className="flex-1 p-6 overflow-auto">
          {tab === 'Overview' && (
            <OverviewTab projectId={projectId} project={project} />
          )}
          {tab === 'Config' && (
            <ConfigTab projectId={projectId} />
          )}
          {tab === 'History' && (
            <HistoryTab />
          )}
        </div>

      </div>
    </Layout>
  )
}
