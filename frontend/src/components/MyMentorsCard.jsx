import { useEffect, useState } from 'react'
import { UserCheck } from 'lucide-react'
import { mentorService } from '../services/adminService'

/** The mentors of the student's project, by name - only once a project has been allocated. Renders nothing while loading, on error, or with none. */
export default function MyMentorsCard() {
  const [mentors, setMentors] = useState([])
  useEffect(() => { mentorService.mine().then(setMentors).catch(() => {}) }, [])
  if (mentors.length === 0) return null
  return (
    <section className="card" aria-label="My mentors">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500"><UserCheck className="h-4 w-4" aria-hidden />My mentor{mentors.length > 1 ? 's' : ''}</h2>
      <ul className="flex flex-wrap gap-2">
        {mentors.map((m) => <li key={m.id} className="rounded-full bg-brand-light px-3 py-1 text-sm font-medium text-brand-dark">{m.name}</li>)}
      </ul>
    </section>
  )
}
