import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import Layout from '../components/Layout'
import Header from '../components/Header'
import PlanTree from '../components/PlanTree'
import PlanRunModal from '../components/PlanRunModal'
import PlanGenerateModal from '../components/PlanGenerateModal'
import { api } from '../hooks/useApi'

export default function Plan() {
  const navigate = useNavigate()

  const [projects, setProjects]                 = useState([])
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [plan, setPlan]                         = useState(null)
  const [loadError, setLoadError]               = useState(null)
  const [showRunModal, setShowRunModal]         = useState(false)
  const [showGenerateModal, setShowGenerateModal] = useState(false)

  useEffect(() => {
    api.get('/api/projects').then(setProjects).catch(() => {})
  }, [])

  const loadPlan = useCallback((projectId) => {
    if (!projectId) { setPlan(null); setLoadError(null); return }
    setLoadError(null)
    api.get(`/api/plan/load?project_id=${projectId}`)
      .then(data => setPlan(data))
      .catch(() => setLoadError('No PLANO.md found in this project.'))
  }, [])

  useEffect(() => {
    loadPlan(selectedProjectId)
  }, [selectedProjectId, loadPlan])

  function handleRunStarted(planRunId) {
    navigate(`/plan/${planRunId}`)
  }

  // Called when PlanGenerateModal saves a plan — reload the tree
  function handlePlanSaved() {
    setShowGenerateModal(false)
    loadPlan(selectedProjectId)
  }

  return (
    <Layout>
      <Header title="Plan" subtitle="Hierarchical execution" />

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="px-6 py-3 border-b border-gray-800 flex items-center gap-3 flex-wrap shrink-0">
          {/* Project selector */}
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

          {/* Generate plan with AI */}
          <button
            onClick={() => setShowGenerateModal(true)}
            disabled={!selectedProjectId}
            className="px-4 py-1.5 text-sm rounded-lg bg-gray-800 text-gray-300 border border-gray-700 hover:bg-gray-700 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Generate with AI
          </button>

          {/* Start execution — only when plan is loaded */}
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
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-gray-600 text-sm">
            {selectedProjectId ? (
              <>
                <p>No PLANO.md found in this project.</p>
                <button
                  onClick={() => setShowGenerateModal(true)}
                  className="text-indigo-400 hover:text-indigo-300 text-xs underline transition-colors"
                >
                  Generate one with AI →
                </button>
              </>
            ) : (
              <p>Select a project to view its plan.</p>
            )}
          </div>
        )}
      </main>

      {/* Run configuration modal */}
      {showRunModal && (
        <PlanRunModal
          projects={projects}
          initialProjectId={selectedProjectId}
          onClose={() => setShowRunModal(false)}
          onStarted={handleRunStarted}
        />
      )}

      {/* AI plan generation modal */}
      {showGenerateModal && (
        <PlanGenerateModal
          projects={projects}
          initialProjectId={selectedProjectId}
          onClose={() => setShowGenerateModal(false)}
          onSaved={handlePlanSaved}
        />
      )}
    </Layout>
  )
}
