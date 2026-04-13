import { useEffect, useState, useMemo } from 'react'
import {
  ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  PieChart, Pie, Cell,
  BarChart, Bar,
} from 'recharts'
import Layout from '../components/Layout'
import Header from '../components/Header'
import { api } from '../hooks/useApi'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDuration(sec) {
  if (sec == null) return '—'
  if (sec < 60) return `${Math.round(sec)}s`
  const m = Math.floor(sec / 60)
  return `${m}m ${Math.round(sec % 60)}s`
}

function fmtPct(rate) {
  if (rate == null) return '—'
  return `${Math.round(rate * 100)}%`
}

function toDateStr(iso) {
  return iso ? iso.slice(0, 10) : ''
}

// ---------------------------------------------------------------------------
// KPI card
// ---------------------------------------------------------------------------

function KpiCard({ label, value, sub, valueColor }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl px-6 py-5 space-y-1">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className={`text-3xl font-bold tabular-nums ${valueColor ?? 'text-gray-100'}`}>
        {value ?? '—'}
      </p>
      {sub && <p className="text-xs text-gray-600">{sub}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Chart card wrapper
// ---------------------------------------------------------------------------

function ChartCard({ title, children, className = '' }) {
  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-2xl px-6 py-5 ${className}`}>
      <h2 className="text-sm font-medium text-gray-300 mb-5">{title}</h2>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Custom tooltip (dark theme)
// ---------------------------------------------------------------------------

function DarkTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl px-3 py-2.5 shadow-xl text-xs">
      {label && <p className="text-gray-400 mb-1.5">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color }} className="tabular-nums">
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Custom pie label
// ---------------------------------------------------------------------------

function PieLabel({ cx, cy, midAngle, outerRadius, percent, name }) {
  const RAD = Math.PI / 180
  const r   = outerRadius + 28
  const x   = cx + r * Math.cos(-midAngle * RAD)
  const y   = cy + r * Math.sin(-midAngle * RAD)
  if (percent < 0.05) return null
  return (
    <text
      x={x} y={y}
      fill="#9ca3af"
      textAnchor={x > cx ? 'start' : 'end'}
      dominantBaseline="central"
      fontSize={11}
    >
      {name} ({Math.round(percent * 100)}%)
    </text>
  )
}

// ---------------------------------------------------------------------------
// Status badge (small)
// ---------------------------------------------------------------------------

const STATUS_STYLE = {
  approved:  'bg-green-900/50 text-green-400 border-green-800',
  escalated: 'bg-red-900/50 text-red-400 border-red-800',
  rejected:  'bg-orange-900/50 text-orange-400 border-orange-800',
  committed: 'bg-emerald-900/50 text-emerald-400 border-emerald-800',
}

function StatusBadge({ status }) {
  const cls = STATUS_STYLE[status] ?? 'bg-gray-800 text-gray-400 border-gray-700'
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${cls}`}>{status}</span>
  )
}

// ---------------------------------------------------------------------------
// Top runs table
// ---------------------------------------------------------------------------

function TopRunsTable({ entries }) {
  // Top 5 by duration descending
  const rows = useMemo(() => {
    return [...entries]
      .map(e => {
        let dur = null
        if (e.started_at && e.finished_at) {
          dur = (new Date(e.finished_at) - new Date(e.started_at)) / 1000
        }
        return { ...e, dur }
      })
      .filter(e => e.dur != null)
      .sort((a, b) => b.dur - a.dur)
      .slice(0, 5)
  }, [entries])

  if (!rows.length) return <p className="text-gray-600 text-sm">No data.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
            <th className="text-left pb-3 pr-4 font-medium">Task</th>
            <th className="text-left pb-3 pr-4 font-medium">Status</th>
            <th className="text-left pb-3 pr-4 font-medium">Duration</th>
            <th className="text-left pb-3 font-medium">Score</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e, i) => (
            <tr key={i} className="border-b border-gray-800/50">
              <td className="py-3 pr-4 max-w-xs">
                <span className="text-gray-300 line-clamp-1 leading-snug">{e.task}</span>
              </td>
              <td className="py-3 pr-4">
                <StatusBadge status={e.status} />
              </td>
              <td className="py-3 pr-4 text-gray-400 text-xs whitespace-nowrap font-mono">
                {fmtDuration(e.dur)}
              </td>
              <td className="py-3 text-xs">
                {e.review?.score != null ? (
                  <span className={`font-mono font-semibold ${
                    e.review.score >= 8 ? 'text-green-400'
                    : e.review.score >= 6 ? 'text-yellow-400'
                    : 'text-red-400'
                  }`}>
                    {e.review.score}/10
                  </span>
                ) : (
                  <span className="text-gray-600">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Chart data builders
// ---------------------------------------------------------------------------

function buildTimelineData(entries) {
  // Group by date: { date, total, approved }
  const map = {}
  for (const e of entries) {
    const d = toDateStr(e.started_at)
    if (!d) continue
    if (!map[d]) map[d] = { date: d, total: 0, approved: 0 }
    map[d].total++
    if (e.status === 'approved' || e.status === 'committed') map[d].approved++
  }
  return Object.values(map).sort((a, b) => a.date.localeCompare(b.date))
}

function buildStatusData(entries) {
  const map = {}
  for (const e of entries) {
    const s = e.status ?? 'unknown'
    map[s] = (map[s] ?? 0) + 1
  }
  return Object.entries(map).map(([name, value]) => ({ name, value }))
}

function buildScoreData(entries) {
  // Bar chart: score bucket -> count
  const map = {}
  for (let i = 1; i <= 10; i++) map[i] = 0
  for (const e of entries) {
    const s = e.review?.score
    if (s != null && s >= 1 && s <= 10) map[s]++
  }
  return Object.entries(map).map(([score, count]) => ({ score: Number(score), count }))
}

// ---------------------------------------------------------------------------
// Pie chart colors
// ---------------------------------------------------------------------------

const PIE_COLORS = {
  approved:  '#22c55e',
  committed: '#10b981',
  escalated: '#ef4444',
  rejected:  '#f97316',
  unknown:   '#6b7280',
}

const PIE_FALLBACK = ['#6366f1', '#8b5cf6', '#ec4899', '#14b8a6', '#f59e0b']

// ---------------------------------------------------------------------------
// Metrics page
// ---------------------------------------------------------------------------

export default function Metrics() {
  const [metrics,  setMetrics]  = useState(null)
  const [entries,  setEntries]  = useState([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)

  useEffect(() => {
    Promise.all([
      api.get('/api/metrics'),
      api.get('/api/history?limit=0'),
    ])
      .then(([m, h]) => {
        setMetrics(m)
        setEntries(h ?? [])
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  const timelineData = useMemo(() => buildTimelineData(entries), [entries])
  const statusData   = useMemo(() => buildStatusData(entries),   [entries])
  const scoreData    = useMemo(() => buildScoreData(entries),    [entries])

  const approvalColor = metrics?.approval_rate >= 0.7
    ? 'text-green-400'
    : metrics?.approval_rate >= 0.5
    ? 'text-yellow-400'
    : 'text-red-400'

  const scoreColor = metrics?.avg_review_score >= 8
    ? 'text-green-400'
    : metrics?.avg_review_score >= 6
    ? 'text-yellow-400'
    : 'text-red-400'

  return (
    <Layout>
      <Header title="Metrics" />

      <main className="flex-1 p-6 max-w-6xl w-full mx-auto space-y-6">

        {loading && (
          <p className="text-gray-500 text-sm py-12 text-center">Loading metrics…</p>
        )}

        {!loading && error && (
          <p className="text-red-400 text-sm py-12 text-center">{error}</p>
        )}

        {!loading && !error && metrics && (
          <>
            {/* ── KPI cards ── */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <KpiCard
                label="Total runs"
                value={metrics.total}
                sub={`${metrics.approved ?? 0} approved · ${metrics.escalated ?? 0} escalated`}
              />
              <KpiCard
                label="Approval rate"
                value={fmtPct(metrics.approval_rate)}
                sub={`${fmtPct(metrics.first_attempt_approval_rate)} on 1st attempt`}
                valueColor={approvalColor}
              />
              <KpiCard
                label="Avg review score"
                value={metrics.avg_review_score != null ? `${metrics.avg_review_score}/10` : '—'}
                sub="across all runs"
                valueColor={scoreColor}
              />
              <KpiCard
                label="Avg duration"
                value={fmtDuration(metrics.avg_duration_seconds)}
                sub={`avg ${metrics.avg_attempts ?? '—'} attempts / run`}
              />
            </div>

            {/* ── Charts row ── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

              {/* Line chart — runs per day */}
              <ChartCard title="Runs per day" className="lg:col-span-2">
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={timelineData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: '#6b7280', fontSize: 11 }}
                      tickFormatter={d => d.slice(5)} // MM-DD
                      axisLine={{ stroke: '#374151' }}
                      tickLine={false}
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fill: '#6b7280', fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip content={<DarkTooltip />} />
                    <Legend
                      wrapperStyle={{ fontSize: 11, color: '#9ca3af' }}
                    />
                    <Line
                      type="monotone"
                      dataKey="total"
                      stroke="#6366f1"
                      strokeWidth={2}
                      dot={{ r: 4, fill: '#6366f1' }}
                      activeDot={{ r: 6 }}
                      name="Total"
                    />
                    <Line
                      type="monotone"
                      dataKey="approved"
                      stroke="#22c55e"
                      strokeWidth={2}
                      dot={{ r: 4, fill: '#22c55e' }}
                      activeDot={{ r: 6 }}
                      name="Approved"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>

              {/* Pie chart — status distribution */}
              <ChartCard title="Status distribution">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={statusData}
                      cx="50%"
                      cy="50%"
                      innerRadius={55}
                      outerRadius={80}
                      paddingAngle={3}
                      dataKey="value"
                      labelLine={false}
                      label={PieLabel}
                    >
                      {statusData.map((entry, i) => (
                        <Cell
                          key={entry.name}
                          fill={PIE_COLORS[entry.name] ?? PIE_FALLBACK[i % PIE_FALLBACK.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={<DarkTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              </ChartCard>

            </div>

            {/* ── Score distribution bar chart ── */}
            <ChartCard title="Score distribution">
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={scoreData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                  <XAxis
                    dataKey="score"
                    tick={{ fill: '#6b7280', fontSize: 11 }}
                    axisLine={{ stroke: '#374151' }}
                    tickLine={false}
                    label={{ value: 'Review score', position: 'insideBottom', offset: -2, fill: '#4b5563', fontSize: 11 }}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fill: '#6b7280', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<DarkTooltip />} />
                  <Bar
                    dataKey="count"
                    name="Runs"
                    radius={[4, 4, 0, 0]}
                  >
                    {scoreData.map(entry => (
                      <Cell
                        key={entry.score}
                        fill={
                          entry.score >= 8 ? '#22c55e'
                          : entry.score >= 6 ? '#eab308'
                          : '#ef4444'
                        }
                        fillOpacity={entry.count > 0 ? 0.85 : 0.15}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            {/* ── Top 5 longest runs ── */}
            <div className="bg-gray-900 border border-gray-800 rounded-2xl px-6 py-5">
              <h2 className="text-sm font-medium text-gray-300 mb-5">
                Top 5 — longest runs
                <span className="text-gray-600 font-normal ml-2 text-xs">(by duration)</span>
              </h2>
              <TopRunsTable entries={entries} />
            </div>

          </>
        )}

      </main>
    </Layout>
  )
}
