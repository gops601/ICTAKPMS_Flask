/**
 * Pick the students of a group and give each a role, all in one list.
 * `students` are the candidates; `members` is [{ student_id, role, is_lead? }]. Used by the student's group proposal
 * and by the mentor / domain lead team editor, so both look and behave the same.
 */
export default function TeamPicker({ students, members, onChange, max = 12, leadable = false, idPrefix = 'team' }) {
  const byId = new Map(members.map((m) => [m.student_id, m]))
  const full = members.length >= max
  const toggle = (id) => {
    if (byId.has(id)) onChange(members.filter((m) => m.student_id !== id))
    else if (!full) onChange([...members, { student_id: id, role: '' }])
  }
  const setRole = (id, role) => onChange(members.map((m) => (m.student_id === id ? { ...m, role } : m)))
  const setLead = (id) => onChange(members.map((m) => ({ ...m, is_lead: m.student_id === id })))

  if (students.length === 0) return <p className="text-sm text-slate-500">No other students are available to add.</p>
  return (
    <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200" aria-label="Students">
      {students.map((s) => {
        const picked = byId.get(s.id)
        const disabled = !picked && full
        return (
          <li key={s.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
            <label className="flex min-w-[12rem] flex-1 cursor-pointer items-center gap-2">
              <input type="checkbox" checked={Boolean(picked)} disabled={disabled} onChange={() => toggle(s.id)} aria-label={`Select ${s.name}`} />
              <span className="font-medium">{s.name}</span><span className="text-slate-500">{s.registration_no}</span>
            </label>
            {picked && (
              <>
                <input className="input !w-44 !py-1" placeholder="Role (e.g. Backend)" maxLength={60} aria-label={`Role of ${s.name}`}
                  value={picked.role || ''} onChange={(e) => setRole(s.id, e.target.value)} />
                {leadable && (
                  <label className="flex items-center gap-1 text-xs text-slate-600">
                    <input type="radio" name={`${idPrefix}-lead`} checked={Boolean(picked.is_lead)} onChange={() => setLead(s.id)} aria-label={`${s.name} is the team lead`} />Lead
                  </label>
                )}
              </>
            )}
          </li>
        )
      })}
    </ul>
  )
}
