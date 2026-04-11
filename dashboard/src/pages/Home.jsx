import Layout from '../components/Layout'
import Header from '../components/Header'

export default function Home() {
  return (
    <Layout>
      <Header title="Run" subtitle="Execute a task" />
      <main className="flex-1 p-6">
        <p className="text-gray-500 text-sm">Task 5.2.2 — coming next.</p>
      </main>
    </Layout>
  )
}
