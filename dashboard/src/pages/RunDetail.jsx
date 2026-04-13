import { useParams, useNavigate } from 'react-router-dom'
import Layout from '../components/Layout'
import Header from '../components/Header'
import AgentCard from '../components/AgentCard'
import RunControls from '../components/RunControls'
import { useRunSocket, AGENTS } from '../hooks/useRunSocket'

// ---------------------------------------------------------------------------
// Progress bar (stage 1-5 based on which agent is active/done)
// ---------------------------------------------------------------------------

function ProgressBar({ agents }) {
  const keys   = AGENTS.map(a => a.key)
  const done   = keys.filter(k => agents[k]?.status === 'done').length
  const active = keys.find(k => agents[k]?.status === 'active')
  const current = active ? keys.indexOf(active) + 1 : done
  const pct = Math.round((current / keys.length) * 100)

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-500">
        <span>Stage {current}/{keys.length}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-indigo-500 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Token/cost counter
// ---------------------------------------------------------------------------

function TokenCounter({ tokens }) {
  if (!tokens.input && !tokens.output) return null
  return (
    <div className="flex gap-4 text-xs text-gray-500">
      <span>↑ {tokens.input.toLocaleString()} in</span>
      <span>↓ {tokens.output.toLocaleString()} out</span>
      {tokens.cost > 0 && (
        <span className="text-gray-400">${tokens.cost.toFixed(4)}</span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Final result banner
// ---------------------------------------------------------------------------

const RESULT_STYLE = {
  approved:  { bg: 'bg-green-900/30 border-green-800',  text: 'text-green-400',  icon: '✓', label: 'Approved' },
  escalated: { bg: 'bg-red-900/30 border-red-800',      text: 'text-red-400',    icon: '!', label: 'Escalated — manual intervention needed' },
  cancelled: { bg: 'bg-gray-800 border-gray-700',       text: 'text-gray-400',   icon: '—', label: 'Cancelled' },
  error:     { bg: 'bg-red-900/30 border-red-800',      text: 'text-red-400',    icon: '✕', label: 'Error' },
}

function ResultBanner({ runStatus, wsError }) {
  const style = RESULT_STYLE[runStatus]
  if (!style) return null
  return (
    <div className={`border rounded-xl px-4 py-3 flex items-center gap-3 ${style.bg}`}>
      <span className={`text-lg leading-none ${style.text}`}>{style.icon}</span>
      <div>
        <p className={`text-sm font-medium ${style.text}`}>{style.label}</p>
        {wsError && <p className="text-xs text-gray-500 mt-0.5">{wsError}</p>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RunDetail page
// ---------------------------------------------------------------------------

export default function RunDetail() {
  const { runId } = useParams()
  const navigate  = useNavigate()
  const { agents, runStatus, tokens, currentPlan, wsError } = useRunSocket(runId)

  const statusLabel = {
    connecting: 'Connecting…',
    running:    'Running',
    paused:     'Paused',
    approved:   'Approved',
    escalated:  'Escalated',
    cancelled:  'Cancelled',
    error:      'Error',
    done:       'Done',
  }[runStatus] ?? runStatus

  const isLive = ['connecting', 'running', 'paused'].includes(runStatus)

  return (
    <Layout>
      <Header
        title="Execution"
        subtitle={runId.slice(0, 8) + '…'}
      />

      <main className="flex-1 p-6 max-w-3xl w-full mx-auto space-y-6">

        {/* Top row: status + controls */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            {isLive && runStatus === 'running' && (
              <span className="inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            )}
            {runStatus === 'paused' && (
              <span className="inline-block w-2 h-2 rounded-full bg-yellow-400" />
            )}
            <span className="text-sm text-gray-400 font-medium">{statusLabel}</span>
          </div>

          <RunControls
            runId={runId}
            runStatus={runStatus}
            currentPlan={currentPlan}
          />
        </div>

        {/* Progress bar */}
        {isLive && <ProgressBar agents={agents} />}

        {/* Result banner */}
        <ResultBanner runStatus={runStatus} wsError={wsError} />

        {/* WS error (non-terminal) */}
        {wsError && isLive && (
          <p className="text-red-400 text-xs">{wsError}</p>
        )}

        {/* Agent cards */}
        <div className="grid gap-3">
          {AGENTS.map(agentDef => (
            <AgentCard
              key={agentDef.key}
              agentDef={agentDef}
              agentState={agents[agentDef.key]}
            />
          ))}
        </div>

        {/* Token counter */}
        <TokenCounter tokens={tokens} />

        {/* Back link */}
        <button
          onClick={() => navigate('/')}
          className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
        >
          ← Back to Run
        </button>

      </main>
    </Layout>
  )
}
