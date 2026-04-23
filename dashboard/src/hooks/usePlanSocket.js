/**
 * usePlanSocket — connects to WS /ws/plan/{planRunId} and reduces the
 * plan runner event stream into a structured state object.
 *
 * Returned shape:
 *   plan           — { name, phases, total_tasks, done_tasks } from plan_loaded
 *   status         — 'idle'|'connecting'|'running'|'paused'|'complete'|'aborted'|'error'
 *   currentTaskId  — id of the task currently executing, or null
 *   currentRunId   — always null (backend does not relay cycle run_ids through plan WS)
 *   pauseReason    — 'subphase'|'phase'|'escalation'|'requested'|null
 *   pauseContext   — { done, escalated, commits, duration_s } | null
 *   results        — TaskResult[] accumulated from task_done/escalated/skipped events
 *   wsError        — string | null
 *   resume         — async fn: POST /api/plan/resume/{planRunId}
 *   abort          — async fn: POST /api/plan/abort/{planRunId}
 *
 * Reconnect behaviour:
 *   Same pattern as useRunSocket — retries up to MAX_RECONNECT times with
 *   RECONNECT_DELAY ms between attempts. State is reset on each reconnect
 *   so the server history-replay rebuilds cleanly without duplicates.
 *
 * Resume action:
 *   When the WS is open, sends {"action":"resume"} directly (lower latency).
 *   Falls back to POST /api/plan/resume/{id} if the socket is closed.
 */

import { useCallback, useEffect, useLayoutEffect, useReducer, useRef } from 'react'
import { api } from './useApi'

const MAX_RECONNECT   = 5
const RECONNECT_DELAY = 2000   // ms between reconnect attempts

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

const TERMINAL_STATUSES = new Set(['complete', 'aborted', 'error'])

const INITIAL_STATE = {
  plan:          null,
  status:        'idle',
  currentTaskId: null,
  currentRunId:  null,
  pauseReason:   null,
  pauseContext:  null,
  results:       [],
  wsError:       null,
}

function reducer(state, action) {
  switch (action.type) {

    case 'WS_OPEN':
      return { ...state, status: 'connecting', wsError: null }

    case 'WS_ERROR':
      return { ...state, wsError: action.payload }

    case 'WS_RECONNECTING':
      return { ...state, wsError: action.payload }

    case 'WS_RESET':
      return { ...INITIAL_STATE, status: 'connecting' }

    case 'WS_CLOSE':
      if (TERMINAL_STATUSES.has(state.status)) return state
      return { ...state, status: 'error' }

    case 'EVENT': {
      const evt        = action.payload
      const type       = evt.type
      const data       = evt.data ?? {}

      // --- WS control messages ---
      if (type === 'ping') return state
      if (type === 'done') {
        // Server sentinel after terminal plan event — only advance status if
        // the reducer hasn't already marked a terminal state.
        if (TERMINAL_STATUSES.has(state.status)) return state
        return { ...state, status: 'complete' }
      }
      if (type === 'error') {
        return { ...state, wsError: data.detail ?? evt.detail ?? 'WebSocket error' }
      }

      // --- Plan runner events ---
      switch (type) {

        case 'plan_loaded':
          return {
            ...state,
            status: 'running',
            plan: {
              name:        data.name        ?? '',
              phases:      data.phases      ?? [],
              total_tasks: data.total_tasks ?? 0,
              done_tasks:  data.done_tasks  ?? 0,
            },
          }

        case 'task_started':
          return {
            ...state,
            status:        'running',
            currentTaskId: data.task_id ?? null,
            currentRunId:  data.run_id  ?? null,
          }

        case 'task_done':
          return {
            ...state,
            currentTaskId: null,
            currentRunId:  null,
            results: [
              ...state.results,
              {
                task_id:     data.task_id    ?? null,
                status:      'done',
                commit_hash: data.commit_hash ?? null,
                score:       data.score       ?? null,
                duration_s:  data.duration_s  ?? null,
              },
            ],
          }

        case 'task_escalated':
          return {
            ...state,
            currentTaskId: null,
            currentRunId:  null,
            results: [
              ...state.results,
              {
                task_id: data.task_id ?? null,
                status:  'escalated',
                reason:  data.reason  ?? null,
              },
            ],
          }

        case 'task_skipped':
          return {
            ...state,
            results: [
              ...state.results,
              {
                task_id: data.task_id ?? null,
                status:  'skipped',
              },
            ],
          }

        case 'plan_paused':
          return {
            ...state,
            status:       'paused',
            pauseReason:  data.reason  ?? null,
            pauseContext: data.context ?? null,
          }

        case 'plan_resumed':
          return {
            ...state,
            status:       'running',
            pauseReason:  null,
            pauseContext: null,
          }

        case 'plan_complete':
          return {
            ...state,
            status:        'complete',
            currentTaskId: null,
          }

        case 'plan_aborted':
          return {
            ...state,
            status:        'aborted',
            currentTaskId: null,
          }

        default:
          // subphase_complete, phase_complete, and unknown events — no state change.
          return state
      }
    }

    default:
      return state
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function usePlanSocket(planRunId) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)

  // Refs that let callbacks and event handlers see current values without
  // becoming stale closures.
  const wsRef          = useRef(null)
  const statusRef      = useRef('idle')
  const attemptsRef    = useRef(0)
  const planRunIdRef   = useRef(planRunId)

  // Sync refs after each render so event callbacks always see current values
  // without capturing stale closures. useLayoutEffect runs synchronously after
  // DOM mutations, avoiding the "write ref during render" lint rule.
  useLayoutEffect(() => {
    statusRef.current    = state.status
    planRunIdRef.current = planRunId
  })

  // ---------------------------------------------------------------------------
  // WebSocket lifecycle
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!planRunId) return

    let cancelled = false
    attemptsRef.current = 0

    const protocol    = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const backendHost = import.meta.env.DEV ? 'localhost:8000' : window.location.host
    const url         = `${protocol}://${backendHost}/ws/plan/${planRunId}`

    function connect() {
      if (cancelled) return

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        attemptsRef.current = 0
        dispatch({ type: 'WS_OPEN' })
      }

      ws.onerror = () => {
        dispatch({ type: 'WS_ERROR', payload: 'WebSocket connection failed' })
      }

      ws.onclose = () => {
        if (cancelled) return

        if (
          !TERMINAL_STATUSES.has(statusRef.current) &&
          attemptsRef.current < MAX_RECONNECT
        ) {
          attemptsRef.current++
          dispatch({
            type:    'WS_RECONNECTING',
            payload: `Connection lost — reconnecting... (${attemptsRef.current}/${MAX_RECONNECT})`,
          })
          setTimeout(() => {
            if (!cancelled) {
              // Reset state so history-replay on reconnect rebuilds cleanly.
              dispatch({ type: 'WS_RESET' })
              connect()
            }
          }, RECONNECT_DELAY)
        } else {
          dispatch({ type: 'WS_CLOSE' })
        }
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          dispatch({ type: 'EVENT', payload: msg })
        } catch {
          // ignore malformed frames
        }
      }
    }

    connect()

    return () => {
      cancelled = true
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [planRunId])

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const resume = useCallback(async () => {
    const id = planRunIdRef.current
    if (!id) return
    const ws = wsRef.current
    // Prefer sending via open WS (lower latency + server semantics are identical).
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: 'resume' }))
    } else {
      await api.post(`/api/plan/resume/${id}`)
    }
  }, [])

  const abort = useCallback(async () => {
    const id = planRunIdRef.current
    if (!id) return
    await api.post(`/api/plan/abort/${id}`)
  }, [])

  return { ...state, resume, abort }
}
