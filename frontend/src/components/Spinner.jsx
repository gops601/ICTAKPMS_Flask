import { Loader2 } from 'lucide-react'

export default function Spinner({ full = false, label = 'Loading…' }) {
  return (
    <div role="status" className={`flex items-center justify-center gap-2 text-slate-500 ${full ? 'min-h-screen' : 'py-10'}`}>
      <Loader2 className="h-5 w-5 animate-spin" aria-hidden />
      <span className="text-sm">{label}</span>
    </div>
  )
}
