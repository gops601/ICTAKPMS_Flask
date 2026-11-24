import { useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleDot, Table2 } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, LabelList, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

/** Validated reference palette (categorical slots 1-3 pass the all-pairs gate; status colours are reserved for state). */
export const COLORS = {
  series: ['#07546a', '#d97706', '#57534e'],
  good: '#0ca30c', critical: '#d03b3b', neutral: '#898781',
  grid: '#e1e0d9', axis: '#c3c2b7', ink: '#0b0b0b', inkSecondary: '#52514e', muted: '#898781',
}
const tick = { fill: COLORS.inkSecondary, fontSize: 12 }

/** Card with a chart and an always-available table view (the accessible, exact-values alternative). */
export function ChartCard({ title, subtitle, summary, table, empty, children, height = 260 }) {
  const [asTable, setAsTable] = useState(false)
  return (
    <section className="card" aria-label={title}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
        {table && !empty && (
          <button type="button" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-100" aria-pressed={asTable} onClick={() => setAsTable(!asTable)}>
            <Table2 className="h-3.5 w-3.5" aria-hidden />{asTable ? 'View chart' : 'View as table'}
          </button>
        )}
      </div>
      {empty ? (
        <p className="py-10 text-center text-sm text-slate-500">No data yet.</p>
      ) : asTable ? (
        <div className="max-h-72 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase text-slate-500"><tr>{table.columns.map((c) => <th key={c.key} className="px-2 py-1.5 font-medium">{c.label}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">{table.rows.map((r, i) => <tr key={i}>{table.columns.map((c) => <td key={c.key} className="px-2 py-1.5">{r[c.key] ?? '—'}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : (
        <div role="img" aria-label={summary || title} style={{ height }}>{children}</div>
      )}
    </section>
  )
}

/** Bars for one or more series. `horizontal` puts long category names on the Y axis. Legend only for ≥ 2 series. */
export function Bars({ data, categoryKey, series, horizontal = false, stacked = false, domain, unit = '' }) {
  const multi = series.length > 1
  const common = { data, margin: { top: 8, right: 24, bottom: 4, left: horizontal ? 8 : -8 } }
  const bars = series.map((s, i) => (
    <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color || COLORS.series[i]} stackId={stacked ? 'a' : undefined}
      barSize={horizontal ? 14 : 22} radius={stacked ? 0 : horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} stroke="#fff" strokeWidth={stacked ? 2 : 0} isAnimationActive={false}>
      {!multi && <LabelList dataKey={s.key} position={horizontal ? 'right' : 'top'} fill={COLORS.inkSecondary} fontSize={12} formatter={(v) => `${v}${unit}`} />}
    </Bar>
  ))
  return (
    <ResponsiveContainer width="100%" height="100%">
      {horizontal ? (
        <BarChart {...common} layout="vertical">
          <CartesianGrid stroke={COLORS.grid} horizontal={false} />
          <XAxis type="number" domain={domain} tick={tick} axisLine={{ stroke: COLORS.axis }} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey={categoryKey} tick={tick} width={110} axisLine={{ stroke: COLORS.axis }} tickLine={false} />
          <Tooltip cursor={{ fill: 'rgba(0,0,0,0.04)' }} formatter={(v) => `${v}${unit}`} />
          {multi && <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />}
          {bars}
        </BarChart>
      ) : (
        <BarChart {...common}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          <XAxis dataKey={categoryKey} tick={tick} axisLine={{ stroke: COLORS.axis }} tickLine={false} />
          <YAxis domain={domain} tick={tick} axisLine={false} tickLine={false} allowDecimals={false} />
          <Tooltip cursor={{ fill: 'rgba(0,0,0,0.04)' }} formatter={(v) => `${v}${unit}`} />
          {multi && <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />}
          {bars}
        </BarChart>
      )}
    </ResponsiveContainer>
  )
}

/** Donut for a part-to-whole of ≤ 3 named slices. Status slices carry an icon + label in the legend, never colour alone. */
export function Donut({ slices }) {
  const total = slices.reduce((s, x) => s + x.value, 0)
  return (
    <div className="flex h-full items-center gap-4">
      <div className="h-full min-w-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={slices.filter((s) => s.value > 0)} dataKey="value" nameKey="label" innerRadius="58%" outerRadius="85%" paddingAngle={2} stroke="#fff" strokeWidth={2} isAnimationActive={false}>
              {slices.filter((s) => s.value > 0).map((s) => <Cell key={s.label} fill={s.color} />)}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="space-y-2 text-sm" aria-label="Legend">
        {slices.map((s) => (
          <li key={s.label} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} aria-hidden />
            {s.icon}<span className="text-slate-700">{s.label}</span><span className="font-semibold text-slate-900">{s.value}</span>
            <span className="text-xs text-slate-400">{total ? `${Math.round((s.value * 100) / total)}%` : '0%'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Status split used across dashboards: Completed (good) / Ongoing (blue) / Delayed (critical), each with an icon. */
export function statusSlices(split) {
  return [
    { label: 'Completed', value: split.completed, color: COLORS.good, icon: <CheckCircle2 className="h-4 w-4 text-green-700" aria-hidden /> },
    { label: 'Ongoing', value: split.ongoing, color: COLORS.series[0], icon: <CircleDot className="h-4 w-4 text-rose-700" aria-hidden /> },
    { label: 'Delayed', value: split.delayed, color: COLORS.critical, icon: <AlertTriangle className="h-4 w-4 text-red-700" aria-hidden /> },
  ]
}

const TONES = { default: 'text-slate-900', good: 'text-green-700', critical: 'text-red-700', warning: 'text-orange-700' }

/** Headline number. A critical/warning tile always shows an icon + label, never colour alone. */
export function StatCard({ label, value, tone = 'default', hint }) {
  const Icon = tone === 'critical' ? AlertTriangle : tone === 'good' ? CheckCircle2 : null
  return (
    <div className="card !p-4" role="group" aria-label={label}>
      <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">{Icon && <Icon className={`h-3.5 w-3.5 ${TONES[tone]}`} aria-hidden />}{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${TONES[tone]}`}>{value}</div>
      {hint && <div className="text-xs text-slate-500">{hint}</div>}
    </div>
  )
}

export function StatGrid({ children }) {
  return <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">{children}</div>
}
