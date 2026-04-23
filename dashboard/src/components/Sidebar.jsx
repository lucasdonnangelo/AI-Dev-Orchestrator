import { NavLink } from 'react-router-dom'
import { usePlanRunContext } from '../context/PlanRunContext'

const NAV_ITEMS = [
  { to: '/', label: 'Run', icon: '▶' },
  { to: '/projects', label: 'Projects', icon: '□' },
  { to: '/plan', label: 'Plan', icon: '⊟' },
  { to: '/history', label: 'History', icon: '≡' },
  { to: '/metrics', label: 'Metrics', icon: '◈' },
]

// Badge shown on the Plan item when a plan run is active
function PlanBadge({ status }) {
  if (status === 'running' || status === 'connecting') {
    return (
      <span
        className="ml-auto w-2 h-2 rounded-full bg-green-400 animate-pulse shrink-0"
        title="Plan running"
      />
    )
  }
  if (status === 'paused') {
    return (
      <span
        className="ml-auto w-2 h-2 rounded-full bg-yellow-400 shrink-0"
        title="Plan paused"
      />
    )
  }
  return null
}

export default function Sidebar() {
  const { activePlanStatus } = usePlanRunContext()

  return (
    <aside className="w-56 min-h-screen bg-gray-900 text-gray-300 flex flex-col border-r border-gray-800 shrink-0">
      {/* Brand */}
      <div className="px-4 py-5 border-b border-gray-800">
        <span className="text-white font-semibold text-sm tracking-wide">
          AI Dev Orchestrator
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-4 space-y-1">
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors',
                isActive
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white',
              ].join(' ')
            }
          >
            <span className="text-base leading-none">{icon}</span>
            {label}
            {to === '/plan' && <PlanBadge status={activePlanStatus} />}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-800 text-xs text-gray-600">
        v0.1.0 · local
      </div>
    </aside>
  )
}
