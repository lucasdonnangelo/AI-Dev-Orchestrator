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
// Tab: Config
// ---------------------------------------------------------------------------

function ConfigTab({ projectId }) {
  const [content, setContent] = useState(null)  // null = loading
  const [found, setFound]     = useState(false)
  const [dirty, setDirty]     = useState(false)
  const [saving, setSaving]   = useState(false)
  const [saved, setSaved]     = useState(false)
  const [error, setError]     = useState('')

  useEffect(() => {
    api.get(`/api/projects/${projectId}/config`)
      .then(d => {
        setContent(d.content)
        setFound(d.found)
      })
      .catch(() => {
        setContent('')
        setFound(false)
      })
  }, [projectId])

  async function handleSave() {
    setSaving(true)
    setSaved(false)
    setError('')
    try {
      await api.put(`/api/projects/${projectId}/config`, { content })
      setFound(true)
      setDirty(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-2xl space-y-4">

      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-white font-medium font-mono">.orchestrator.yaml</p>
          {content !== null && !found && (
            <p className="text-xs text-gray-600 mt-0.5">
              File not found — save to create it.
            </p>
          )}
          {content !== null && found && !dirty && (
            <p className="text-xs text-gray-600 mt-0.5">Loaded from project directory.</p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {saved && <span className="text-xs text-green-400">Saved!</span>}
          {error && <span className="text-xs text-red-400 truncate max-w-xs">{error}</span>}
          <button
            onClick={handleSave}
            disabled={saving || content === null}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-xs rounded-lg px-4 py-1.5 transition-colors"
          >
            {saving ? 'Saving…' : dirty ? 'Save *' : 'Save'}
          </button>
        </div>
      </div>

      {/* Editor */}
      {content === null ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 animate-pulse space-y-2">
          <div className="h-3 bg-gray-800 rounded w-1/2" />
          <div className="h-3 bg-gray-800 rounded w-1/3" />
        </div>
      ) : (
        <textarea
          value={content}
          onChange={e => { setContent(e.target.value); setDirty(true); setSaved(false) }}
          rows={22}
          spellCheck={false}
          placeholder={
            '# .orchestrator.yaml — project-level config overrides\n' +
            '# planner_provider: anthropic\n' +
            '# critic_provider: google\n' +
            '# google_model: gemini-2.5-flash\n' +
            '# critic_min_rounds: 2\n' +
            '# critic_max_rounds: 5\n' +
            '# orchestrator_max_retries: 3\n'
          }
          className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-xs text-gray-300 font-mono resize-none focus:outline-none focus:border-indigo-500 transition-colors leading-relaxed"
        />
      )}

      <p className="text-xs text-gray-700">
        This file is the highest-priority config layer for this project.
        It overrides both global defaults and <code className="font-mono">~/.orchestrator/config.yaml</code>.
      </p>
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
