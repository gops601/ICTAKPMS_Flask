const STYLES = {
  error: 'bg-red-50 text-red-700 ring-red-200',
  success: 'bg-green-50 text-green-700 ring-green-200',
  warning: 'bg-orange-50 text-orange-700 ring-orange-200',
  info: 'bg-amber-50 text-amber-800 ring-amber-200',
}

export default function Alert({ type = 'error', children }) {
  if (!children) return null
  return (
    <div role={type === 'error' ? 'alert' : 'status'} className={`rounded-lg px-3 py-2 text-sm ring-1 ${STYLES[type]}`}>
      {children}
    </div>
  )
}
