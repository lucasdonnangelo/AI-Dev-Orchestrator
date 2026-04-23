import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { PlanRunProvider } from './context/PlanRunContext'
import Home from './pages/Home'
import Projects from './pages/Projects'
import ProjectDetail from './pages/ProjectDetail'
import History from './pages/History'
import Metrics from './pages/Metrics'
import RunDetail from './pages/RunDetail'
import Plan from './pages/Plan'
import PlanRun from './pages/PlanRun'

export default function App() {
  return (
    <PlanRunProvider>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/run/:runId" element={<RunDetail />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:projectId" element={<ProjectDetail />} />
        <Route path="/history" element={<History />} />
        <Route path="/metrics" element={<Metrics />} />
        <Route path="/plan" element={<Plan />} />
        <Route path="/plan/:planRunId" element={<PlanRun />} />
      </Routes>
    </BrowserRouter>
    </PlanRunProvider>
  )
}
