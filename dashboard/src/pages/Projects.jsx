import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import Layout from '../components/Layout'
import Header from '../components/Header'
import NewProjectModal from '../components/NewProjectModal'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// Stack badge
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

function StackBadge({ stack }) {
  const cls = STACK_COLORS[stack] ?? 'bg-gray-800 text-gray-400 border-gray-700'
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${cls}`}>
      {stack}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Project card
// ---------------------------------------------------------------------------

function ProjectCard({ project, stackInfo, onDelete, onClick }) {
  const [confirming, setConfirming] = useState(false)

  function handleDelete(e) {
    e.stopPropagation()
    if (!confirming) {
      setConfirming(true)
      return
    }
    onDelete(project.id)
  }

  function handleBlur() {
    // Cancela confirmacao se usuario clicar fora do botao
    setTimeout(() => setConfirming(false), 200)
  }

  // Stack display
  let stackContent
  if (stackInfo === null) {
    stackContent = <span className="text-xs text-gray-700">detecting…</span>
  } else if (stackInfo.path_exists === false) {
    stackContent = <span className="text-xs text-red-800">path not found</span>
  } else if (stackInfo.stack && stackInfo.stack.length > 0) {
    stackContent = stackInfo.stack.map(s => <StackBadge key={s} stack={s} />)
  } else {
    stackContent = <span className="text-xs text-gray-700">unknown stack</span>
  }

  return (
    <div
      onClick={() => onClick(project.id)}
      className="bg-gray-900 border border-gray-800 rounded-xl p-5 cursor-pointer hover:border-indigo-600/50 transition-all group"
    >
      {/* Top row: name + delete */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <h3 className="text-white font-medium text-sm truncate flex-1" title={project.name}>
          {project.name}
        </h3>
        <button
          onClick={handleDelete}
          onBlur={handleBlur}
          className={`text-xs px-2 py-0.5 rounded transition-colors shrink-0 leading-5 ${
            confirming
              ? 'bg-red-700 text-white'
              : 'text-gray-700 hover:text-red-400 hover:bg-gray-800'
          }`}
        >
          {confirming ? 'Confirm?' : '✕'}
        </button>
      </div>

      {/* Path */}
      <p
        className="text-xs text-gray-600 truncate mb-4"
        title={project.path}
      >
        {project.path}
      </p>

      {/* Stack badges */}
      <div className="flex flex-wrap gap-1 mb-4 min-h-[22px]">
        {stackContent}
      </div>

      {/* Footer row */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-700">Last run: —</span>
        <span className="text-xs text-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity">
          View details →
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState({ onAdd, onNew }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="text-5xl mb-4 text-gray-800 select-none">□</div>
      <p className="text-gray-400 text-sm mb-1">No projects registered yet</p>
      <p className="text-gray-600 text-xs mb-8">
        Add an existing folder or create a new one from a template.
      </p>
      <div className="flex gap-3">
        <button
          onClick={onAdd}
          className="bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 text-sm rounded-lg px-4 py-2 transition-colors"
        >
          Add Existing
        </button>
        <button
          onClick={onNew}
          className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg px-4 py-2 transition-colors"
        >
          New Project
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Projects page
// ---------------------------------------------------------------------------

export default function Projects() {
  const navigate = useNavigate()

  const [projects, setProjects]       = useState([])
  const [stackInfoMap, setStackInfoMap] = useState({})  // id -> {stack, path_exists} | null
  const [loading, setLoading]         = useState(true)
  const [modal, setModal]             = useState(null)  // null | 'add' | 'new'

  // ---- data loading -------------------------------------------------------

  const fetchStackInfo = useCallback((projectId) => {
    setStackInfoMap(prev => ({ ...prev, [projectId]: null }))
    api.get(`/api/projects/${projectId}/info`)
      .then(info => setStackInfoMap(prev => ({ ...prev, [projectId]: info })))
      .catch(() => setStackInfoMap(prev => ({
        ...prev,
        [projectId]: { stack: [], path_exists: false },
      })))
  }, [])

  const loadProjects = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get('/api/projects')
      setProjects(data)
      // Fetch stack info for all projects in parallel
      data.forEach(p => fetchStackInfo(p.id))
    } catch {
      setProjects([])
    } finally {
      setLoading(false)
    }
  }, [fetchStackInfo])

  useEffect(() => { loadProjects() }, [loadProjects])

  // ---- actions ------------------------------------------------------------

  async function handleDelete(id) {
    try {
      await api.delete(`/api/projects/${id}`)
      setProjects(prev => prev.filter(p => p.id !== id))
      setStackInfoMap(prev => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    } catch (err) {
      console.error('Failed to delete project:', err)
    }
  }

  function handleProjectCreated(project) {
    setProjects(prev => [...prev, project])
    fetchStackInfo(project.id)
  }

  // ---- render -------------------------------------------------------------

  const subtitle = loading
    ? 'loading…'
    : `${projects.length} registered`

  return (
    <Layout>
      <Header title="Projects" subtitle={subtitle} />

      <main className="flex-1 p-6">

        {/* Action bar */}
        {!loading && projects.length > 0 && (
          <div className="flex items-center justify-between mb-6">
            <p className="text-sm text-gray-600">
              {projects.length} project{projects.length !== 1 ? 's' : ''}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setModal('add')}
                className="bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 text-sm rounded-lg px-4 py-2 transition-colors"
              >
                + Add Existing
              </button>
              <button
                onClick={() => setModal('new')}
                className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg px-4 py-2 transition-colors"
              >
                + New Project
              </button>
            </div>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="bg-gray-900 border border-gray-800 rounded-xl p-5 animate-pulse">
                <div className="h-4 bg-gray-800 rounded w-1/2 mb-3" />
                <div className="h-3 bg-gray-800 rounded w-3/4 mb-4" />
                <div className="h-5 bg-gray-800 rounded w-1/4" />
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && projects.length === 0 && (
          <EmptyState
            onAdd={() => setModal('add')}
            onNew={() => setModal('new')}
          />
        )}

        {/* Projects grid */}
        {!loading && projects.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {projects.map(project => (
              <ProjectCard
                key={project.id}
                project={project}
                stackInfo={stackInfoMap[project.id] ?? null}
                onDelete={handleDelete}
                onClick={id => navigate(`/projects/${id}`)}
              />
            ))}
          </div>
        )}

      </main>

      {/* Modal — Add Existing */}
      {modal === 'add' && (
        <NewProjectModal
          title="Add Existing Project"
          showTemplate={false}
          onClose={() => setModal(null)}
          onCreated={handleProjectCreated}
        />
      )}

      {/* Modal — New Project (com template) */}
      {modal === 'new' && (
        <NewProjectModal
          title="New Project"
          showTemplate={true}
          onClose={() => setModal(null)}
          onCreated={handleProjectCreated}
        />
      )}
    </Layout>
  )
}
