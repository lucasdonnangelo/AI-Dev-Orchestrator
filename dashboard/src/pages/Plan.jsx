import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import Layout from '../components/Layout'
import Header from '../components/Header'
import PlanTree from '../components/PlanTree'
import PlanRunModal from '../components/PlanRunModal'
import { api } from '../hooks/useApi'

export default function Plan() {
  const navigate = useNavigate()

  const [projects, setProjects]               = useState([])
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [plan, setPlan]                       = useState(null)
  const [loadError, setLoadError]             = useState(null)
  const [showRunModal, setShowRunModal]       = useState(false)

  useEffect(() => {
    api.get('/api/projects').then(setProjects).catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedProjectId) { setPlan(null); setLoadError(null); return }
    setLoadError(null)
    api.get(`/api/plan/load?project_id=${selectedProjectId}`)
      .then(data => setPlan(data))
      .catch(() => setLoadError('No PLANO.md found in this project.'))
  }, [selectedProjectId])

  function handleRunStarted(planRunId) {
    navigate(`/plan/${planRunId}`)
  }

  return (
    <Layout>
      <Header title="Plan" subtitle="Hierarchical execution" />

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="px-6 py-3 border-b border-gray-800 flex items-center gap-3 flex-wrap shrink-0">
          <select
            value={selectedProjectId}
            onChange={e => setSelectedProjectId(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="">Select project…</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>

          <button
            onClick={() => setShowRunModal(true)}
            disabled={!plan}
            className="px-4 py-1.5 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Start Execution
          </button>

          {loadError && (
            <span className="text-red-400 text-sm">{loadError}</span>
          )}
        </div>

        {/* Plan tree or empty state */}
        {plan ? (
          <div className="flex-1 overflow-y-auto p-2">
            <PlanTree plan={plan} currentTaskId={null} results={[]} />
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">
            {selectedProjectId
              ? 'No plan loaded.'
              : 'Select a project to view its plan.'}
          </div>
        )}
      </main>

      {showRunModal && (
        <PlanRunModal
          projects={projects}
          initialProjectId={selectedProjectId}
          onClose={() => setShowRunModal(false)}
          onStarted={handleRunStarted}
        />
      )}
    </Layout>
  )
}
