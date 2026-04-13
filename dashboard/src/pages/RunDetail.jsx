import { useParams } from 'react-router-dom'
import Layout from '../components/Layout'
import Header from '../components/Header'

export default function RunDetail() {
  const { runId } = useParams()
  return (
    <Layout>
      <Header title="Execution" subtitle={runId} />
      <main className="flex-1 p-6">
        <p className="text-gray-500 text-sm">Task 5.2.3 — Execution panel coming next.</p>
      </main>
    </Layout>
  )
}
