import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import Layout from '../components/Layout'
import Header from '../components/Header'
import NewProjectModal from '../components/NewProjectModal'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_STYLES = {
  approved:  'bg-green-900/60 text-green-400 border-green-800',
  escalated: 'bg-red-900/60 text-red-400 border-red-800',
  running:   'bg-blue-900/60 text-blue-400 border-blue-800',
  paused:    'bg-yellow-900/60 text-yellow-400 border-yellow-800',
  cancelled: 'bg-gray-800 text-gray-500 border-gray-700',
  error:     'bg-red-900/60 text-red-400 border-red-800',
}

function StatusBadge({ status }) {
  const cls = STATUS_STYLES[status] ?? 'bg-gray-800 text-gray-400 border-gray-700'
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${cls}`}>
      {status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Recent runs list
// ---------------------------------------------------------------------------

function RecentRuns({ runs }) {
  if (!runs.length) {
    return (
      <p className="text-gray-600 text-sm text-center py-6">
        No runs yet. Execute a task to get started.
      </p>
    )
  }

  return (
    <ul className="divide-y divide-gray-800">
      {runs.map((run, i) => {
        const date = run.started_at
          ? new Date(run.started_at).toLocaleString(undefined, {
              month: 'short', day: 'numeric',
              hour: '2-digit', minute: '2-digit',
            })
          : '—'

        return (
          <li key={run.run_id ?? i} className="flex items-center gap-4 py-3">
            <StatusBadge status={run.status} />
            <span className="flex-1 text-sm text-gray-300 truncate" title={run.task}>
              {run.task}
            </span>
            <span className="text-xs text-gray-600 shrink-0">{date}</span>
          </li>
        )
      })}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// Home page
// ---------------------------------------------------------------------------

export default function Home() {
  const navigate = useNavigate()

  const [task, setTask]           = useState('')
  const [projects, setProjects]   = useState([])
  const [projectId, setProjectId] = useState('')
  const [recentRuns, setRecentRuns] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [runError, setRunError]   = useState('')

  // Resolve the filesystem path for the selected project.
  const selectedProject = projects.find(p => p.id === projectId)
  const projectDir = selectedProject?.path ?? '.'

  // ---- data loading -------------------------------------------------------

  const loadProjects = useCallback(() => {
    api.get('/api/projects')
      .then(data => {
        setProjects(data)
        // Auto-select first project if none chosen yet
        if (!projectId && data.length > 0) setProjectId(data[0].id)
      })
      .catch(() => {})
  }, [projectId])

  const loadHistory = useCallback(() => {
    api.get('/api/history?limit=5')
      .then(data => setRecentRuns(data.slice(0, 5)))
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadProjects()
    loadHistory()
  }, [loadProjects, loadHistory])

  // ---- execute ------------------------------------------------------------

  async function handleRun(e) {
    e.preventDefault()
    if (!task.trim()) return
    setRunError('')
    setSubmitting(true)
    try {
      const { run_id } = await api.post('/api/run', {
        task: task.trim(),
        project_dir: projectDir,
      })
      navigate(`/run/${run_id}`)
    } catch (err) {
      setRunError(err.message)
      setSubmitting(false)
    }
  }

  // ---- project created callback ------------------------------------------

  function handleProjectCreated(project) {
    setProjects(prev => [...prev, project])
    setProjectId(project.id)
  }

  // -------------------------------------------------------------------------

  return (
    <Layout>
      <Header title="Run" subtitle="Execute a task" />

      <main className="flex-1 p-6 max-w-3xl w-full mx-auto space-y-8">

        {/* ---- Task form ---- */}
        <section>
          <form onSubmit={handleRun} className="space-y-4">

            {/* Textarea */}
            <div>
              <label className="block text-xs text-gray-400 mb-2 uppercase tracking-wider">
                Task description
              </label>
              <textarea
                value={task}
                onChange={e => setTask(e.target.value)}
                placeholder="Describe what you want the orchestrator to implement…"
                rows={6}
                className="w-full bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-600 resize-none focus:outline-none focus:border-indigo-500 transition-colors leading-relaxed"
              />
            </div>

            {/* Project row */}
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <label className="block text-xs text-gray-400 mb-1">Project</label>
                {projects.length === 0 ? (
                  <p className="text-xs text-gray-600 py-2">
                    No projects registered yet. Add one below.
                  </p>
                ) : (
                  <select
                    value={projectId}
                    onChange={e => setProjectId(e.target.value)}
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 transition-colors"
                  >
                    <option value="">— select project —</option>
                    {projects.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                )}
              </div>

              <div className="pt-5">
                <button
                  type="button"
                  onClick={() => setShowModal(true)}
                  className="bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 text-sm rounded-lg px-4 py-2 transition-colors whitespace-nowrap"
                >
                  + New Project
                </button>
              </div>
            </div>

            {/* Project path hint */}
            {selectedProject && (
              <p className="text-xs text-gray-600 -mt-2 pl-1 truncate" title={selectedProject.path}>
                {selectedProject.path}
              </p>
            )}

            {/* Error */}
            {runError && (
              <p className="text-red-400 text-xs">{runError}</p>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={submitting || !task.trim()}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium text-sm rounded-xl py-3 transition-colors"
            >
              {submitting ? 'Starting…' : 'Execute'}
            </button>
          </form>
        </section>

        {/* ---- Recent runs ---- */}
        <section>
          <h2 className="text-xs text-gray-400 uppercase tracking-wider mb-3">
            Recent runs
          </h2>
          <div className="bg-gray-900 border border-gray-800 rounded-xl px-4">
            <RecentRuns runs={recentRuns} />
          </div>
        </section>

      </main>

      {/* New project modal */}
      {showModal && (
        <NewProjectModal
          onClose={() => setShowModal(false)}
          onCreated={handleProjectCreated}
        />
      )}
    </Layout>
  )
}
