import { useParams, useNavigate } from 'react-router-dom'
import Layout from '../components/Layout'
import Header from '../components/Header'

// Placeholder para Task 5.3.2 — Detalhes do Projeto
export default function ProjectDetail() {
  const { projectId } = useParams()
  const navigate = useNavigate()

  return (
    <Layout>
      <Header title="Project Detail" subtitle="Task 5.3.2 — coming soon" />
      <main className="flex-1 p-6">
        <button
          onClick={() => navigate('/projects')}
          className="text-sm text-indigo-400 hover:text-indigo-300 mb-6 inline-flex items-center gap-1 transition-colors"
        >
          ← Back to Projects
        </button>
        <p className="text-gray-500 text-sm">Project ID: {projectId}</p>
        <p className="text-gray-700 text-xs mt-2">
          Details, config editor, and run history will be implemented in Phase 5.3.2.
        </p>
      </main>
    </Layout>
  )
}
