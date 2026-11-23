import { useEffect, useState } from 'react'
import { projectService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Alert from './Alert'
import Spinner from './Spinner'
import PageHeader from './PageHeader'
import { EmptyState } from './illustrations'

/** Resolves the signed-in student's project, then renders `children(project)`. */
export default function MyProjectGate({ title, children }) {
  const [state, setState] = useState({ loading: true, project: null, error: '' })
  useEffect(() => {
    projectService.list({ per_page: 1 })
      .then((r) => setState({ loading: false, project: r.items[0] || null, error: '' }))
      .catch((e) => setState({ loading: false, project: null, error: errorMessage(e) }))
  }, [])

  if (state.loading) return <Spinner />
  if (state.error) return <Alert>{state.error}</Alert>
  if (!state.project) {
    return (
      <div>
        <PageHeader title={title} />
        <div className="card"><EmptyState title="No project has been allocated to you yet.">Your Domain Lead will allocate one soon – you will be notified.</EmptyState></div>
      </div>
    )
  }
  return children(state.project)
}
