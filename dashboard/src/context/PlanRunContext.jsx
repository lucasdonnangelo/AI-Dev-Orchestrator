import { createContext, useCallback, useContext, useState } from 'react'

// ---------------------------------------------------------------------------
// PlanRunContext — tracks the currently active plan run across the whole app.
//
// Used by:
//   PlanRun.jsx  — sets status when WS updates come in, clears on unmount
//   Sidebar.jsx  — reads status to show the "running" badge on the Plan item
// ---------------------------------------------------------------------------

const PlanRunContext = createContext({
  activePlanRunId:    null,
  activePlanStatus:   null,
  setActivePlanRun:   () => {},
  clearActivePlanRun: () => {},
})

export function PlanRunProvider({ children }) {
  const [activePlanRunId,  setId]     = useState(null)
  const [activePlanStatus, setStatus] = useState(null)

  const setActivePlanRun = useCallback((id, status) => {
    setId(id)
    setStatus(status)
  }, [])

  const clearActivePlanRun = useCallback(() => {
    setId(null)
    setStatus(null)
  }, [])

  return (
    <PlanRunContext.Provider value={{ activePlanRunId, activePlanStatus, setActivePlanRun, clearActivePlanRun }}>
      {children}
    </PlanRunContext.Provider>
  )
}

export const usePlanRunContext = () => useContext(PlanRunContext)
