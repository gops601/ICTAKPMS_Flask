import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { projectService, proposalService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Alert from './Alert'
import Spinner from './Spinner'
import PageHeader from './PageHeader'
import { EmptyState } from './illustrations'

/** Resolves the signed-in student's project, then renders `children(project)`. */
export default function MyProjectGate({ title, children }) {
  const [state, setState] = useState({ loading: true, project: null, error: '' })
  const [pending, setPending] = useState(null)
  useEffect(() => {
    projectService.list({ per_page: 1 })
      .then((r) => setState({ loading: false, project: r.items[0] || null, error: '' }))
      .catch((e) => setState({ loading: false, project: null, error: errorMessage(e) }))
  }, [])
  useEffect(() => {
    (async () => {
      try { const m = await proposalService.mine(); setPending((m.proposals || []).find((p) => p.status === 'pending') || null) } catch { /* optional hint */ }
    })()
  }, [])

  if (state.loading) return <Spinner />
  if (state.error) return <Alert>{state.error}</Alert>
  if (!state.project) {
    return (
      <div>
        <PageHeader title={title} />
        <div className="card">
          {pending ? (
            <EmptyState title="Your project is awaiting your mentor's approval.">“{pending.title}” is on the Project Shelf. The SRS opens as soon as your mentor approves it – you will be notified.</EmptyState>
          ) : (
            <EmptyState title="No project has been allocated to you yet.">Your mentor or Domain Lead will allocate one – or <Link className="text-brand underline" to="/student/proposal">add your own project</Link>. You will be notified.</EmptyState>
          )}
        </div>
      </div>
    )
  }
  return children(state.project)
}
