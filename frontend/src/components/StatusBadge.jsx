const TONES = {
  green: 'bg-green-100 text-green-700',
  orange: 'bg-orange-100 text-orange-700',
  red: 'bg-red-100 text-red-700',
  blue: 'bg-yellow-100 text-yellow-800',
  grey: 'bg-slate-200 text-slate-700',
}
const MAP = {
  active: 'green', valid: 'green', confirmed: 'green', completed: 'green',
  closed: 'grey', inactive: 'grey',
  error: 'red', failed: 'red',
  previewed: 'blue', pending: 'orange',
}

export default function StatusBadge({ status, tone, children }) {
  const t = TONES[tone || MAP[status] || 'grey']
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${t}`}>{children || status}</span>
}
