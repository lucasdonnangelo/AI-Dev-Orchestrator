/**
 * useRunSocket — connects to WS /ws/run/{runId} and reduces the event stream
 * into a structured state object consumed by RunDetail.
 *
 * Returned shape:
 *   agents      — map of agentKey -> { status, label, color, events[] }
 *   runStatus   — 'connecting'|'running'|'paused'|'approved'|'escalated'|'cancelled'|'error'|'done'
 *   tokens      — { input, output, cost }
 *   currentPlan — TaskPlan dict from PLAN_COMPLETED / CRITIC_CONSENSUS (latest)
 *   wsError     — string | null
 */

import { useEffect, useReducer, useRef } from 'react'

// ---------------------------------------------------------------------------
// Agent definitions (order = pipeline order)
// ---------------------------------------------------------------------------

export const AGENTS = [
  { key: 'planner',  label: 'Planner',  color: 'indigo' },
  { key: 'critic',   label: 'Critic',   color: 'cyan'   },
  { key: 'executor', label: 'Executor', color: 'green'  },
  { key: 'reviewer', label: 'Reviewer', color: 'yellow' },
  { key: 'decisor',  label: 'Decisor',  color: 'purple' },
]

function initAgents() {
  return Object.fromEntries(
    AGENTS.map(a => [a.key, { status: 'idle', events: [] }])
  )
}

// ---------------------------------------------------------------------------
// Event -> agent routing
// ---------------------------------------------------------------------------

const EVENT_ROUTING = {
  plan_started:       { agent: 'planner',  agentStatus: 'active' },
  plan_completed:     { agent: 'planner',  agentStatus: 'done'   },
  critic_round:       { agent: 'critic',   agentStatus: 'active' },
  critic_consensus:   { agent: 'critic',   agentStatus: 'done'   },
  execute_started:    { agent: 'executor', agentStatus: 'active' },
  execute_completed:  { agent: 'executor', agentStatus: 'done'   },
  review_started:     { agent: 'reviewer', agentStatus: 'active' },
  review_completed:   { agent: 'reviewer', agentStatus: 'done'   },
  decision_started:   { agent: 'decisor',  agentStatus: 'active' },
  decision_completed: { agent: 'decisor',  agentStatus: 'done'   },
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

function reducer(state, action) {
  switch (action.type) {

    case 'WS_OPEN':
      return { ...state, runStatus: 'connecting', wsError: null }

    case 'WS_ERROR':
      return { ...state, wsError: action.payload }

    case 'WS_CLOSE':
      // Only override status if we haven't reached a terminal state.
      if (['approved', 'escalated', 'cancelled', 'error'].includes(state.runStatus)) {
        return state
      }
      return { ...state, runStatus: 'done' }

    case 'EVENT': {
      const evt = action.payload          // { type, data, timestamp, run_id }
      const evtType = evt.type

      // --- WS control messages ---
      if (evtType === 'done') return { ...state, runStatus: state.runStatus }
      if (evtType === 'ping') return state
      if (evtType === 'error') return { ...state, wsError: evt.detail ?? 'Unknown WS error' }

      // --- Run-level status ---
      let runStatus = state.runStatus
      if (evtType === 'cycle_approved')  runStatus = 'approved'
      if (evtType === 'cycle_escalated') runStatus = 'escalated'
      if (evtType === 'cycle_paused')    runStatus = 'paused'
      if (evtType === 'cycle_resumed')   runStatus = 'running'
      // First agent event means we're running
      if (runStatus === 'connecting' && EVENT_ROUTING[evtType]) runStatus = 'running'

      // --- Token usage ---
      let tokens = state.tokens
      if (evtType === 'token_usage') {
        const d = evt.data ?? {}
        tokens = {
          input:  state.tokens.input  + (d.input_tokens  ?? 0),
          output: state.tokens.output + (d.output_tokens ?? 0),
          cost:   state.tokens.cost   + (d.cost_usd      ?? 0),
        }
      }

      // --- Current plan ---
      let currentPlan = state.currentPlan
      if ((evtType === 'plan_completed' || evtType === 'critic_consensus') && evt.data?.plan) {
        currentPlan = evt.data.plan
      }

      // --- Agent state ---
      const route = EVENT_ROUTING[evtType]
      let agents = state.agents
      if (route) {
        const prev = agents[route.agent]
        // If executor retries, reset executor status to active
        let agentStatus = route.agentStatus
        if (evtType === 'execute_started' && prev.status === 'done') agentStatus = 'active'

        agents = {
          ...agents,
          [route.agent]: {
            ...prev,
            status: agentStatus,
            events: [...prev.events, { ...evt, _ts: Date.now() }],
          },
        }
      }

      return { ...state, runStatus, tokens, agents, currentPlan }
    }

    default:
      return state
  }
}

const INITIAL_STATE = {
  runStatus:   'connecting',
  agents:      initAgents(),
  tokens:      { input: 0, output: 0, cost: 0 },
  currentPlan: null,
  wsError:     null,
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useRunSocket(runId) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)
  const wsRef = useRef(null)

  useEffect(() => {
    if (!runId) return

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    // Connect directly to backend (port 8000) to avoid Vite WS proxy quirks in dev.
    // In production (served from FastAPI), same-origin WS works naturally.
    const backendHost = import.meta.env.DEV ? 'localhost:8000' : window.location.host
    const url = `${protocol}://${backendHost}/ws/run/${runId}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen  = () => dispatch({ type: 'WS_OPEN' })
    ws.onerror = () => dispatch({ type: 'WS_ERROR', payload: 'WebSocket connection failed' })
    ws.onclose = () => dispatch({ type: 'WS_CLOSE' })
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        dispatch({ type: 'EVENT', payload: msg })
      } catch {
        // ignore malformed frames
      }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [runId])

  return { ...state, ws: wsRef.current }
}
