import { useCallback, useEffect, useState } from 'react'
import { MessageSquareText, Send } from 'lucide-react'
import { feedbackService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Alert from './Alert'
import StatusBadge from './StatusBadge'

/**
 * Mentor feedback for one project. Mentors can write to the whole team or to one student;
 * students see team-wide feedback plus anything addressed to them.
 */
export default function FeedbackPanel({ project, canSend }) {
  const [items, setItems] = useState([])
  const [to, setTo] = useState('') // '' = whole team
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)

  const load = useCallback(() => feedbackService.list(project.id).then(setItems).catch((e) => setError(errorMessage(e))), [project.id])
  useEffect(() => { load() }, [load])

  const send = async (e) => {
    e.preventDefault(); setBusy(true); setError(''); setSent(false)
    try {
      await feedbackService.send(project.id, message, to ? Number(to) : null)
      setMessage(''); setSent(true); await load()
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  return (
    <section className="card space-y-3" aria-label="Mentor feedback">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500"><MessageSquareText className="h-4 w-4" />Mentor feedback</h2>
      <Alert>{error}</Alert>
      {sent && <Alert type="success">Feedback sent.</Alert>}
      {canSend && (
        <form onSubmit={send} className="space-y-2 rounded-lg bg-slate-50 p-3">
          <div>
            <label htmlFor="fb-to" className="label">Send to</label>
            <select id="fb-to" className="input" value={to} onChange={(e) => setTo(e.target.value)}>
              <option value="">{project.members.length > 1 ? 'Whole team' : 'The student'}</option>
              {project.members.length > 1 && project.members.map((m) => <option key={m.student_id} value={m.student_id}>{m.name} only</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="fb-msg" className="label">Feedback</label>
            <textarea id="fb-msg" className="input min-h-[90px]" required maxLength={5000} value={message} onChange={(e) => setMessage(e.target.value)} />
          </div>
          <div className="flex justify-end"><button className="btn-primary" disabled={busy || !message.trim()}><Send className="h-4 w-4" />{busy ? 'Sending…' : 'Send feedback'}</button></div>
        </form>
      )}
      {items.length === 0 && <p className="text-sm text-slate-500">No feedback yet.</p>}
      <ul className="divide-y divide-slate-100">
        {items.map((f) => (
          <li key={f.id} className="py-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{f.author.name}</span>
              <StatusBadge tone={f.recipient.type === 'team' ? 'green' : 'orange'}>{f.recipient.type === 'team' ? 'Whole team' : f.recipient.name}</StatusBadge>
              <span className="text-xs text-slate-500">{new Date(`${f.created_at}Z`).toLocaleString()}</span>
            </div>
            <p className="mt-1 whitespace-pre-wrap text-slate-800">{f.message}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}
