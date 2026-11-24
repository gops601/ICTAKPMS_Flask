import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { projectService } from '../../services/adminService'
import { errorMessage } from '../../services/api'
import ProjectView from '../../components/ProjectView'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'
import PageHeader from '../../components/PageHeader'
import { EmptyState } from '../../components/illustrations'

export default function MyProject() {
  const [state, setState] = useState({ loading: true, projects: [], error: '' })

  useEffect(() => {
    projectService.list({ per_page: 10 })
      .then((r) => setState({ loading: false, projects: r.items, error: '' }))
      .catch((e) => setState({ loading: false, projects: [], error: errorMessage(e) }))
  }, [])

  if (state.loading) return <Spinner />
  if (state.error) return <Alert>{state.error}</Alert>
  if (state.projects.length === 0) {
    return (
      <div>
        <PageHeader title="My Project" />
        <div className="card"><EmptyState title="No project has been allocated to you yet.">Your mentor or Domain Lead will allocate one &ndash; or <Link className="text-brand underline" to="/student/proposal">add your own project</Link>. You&apos;ll be notified.</EmptyState></div>
      </div>
    )
  }
  return <ProjectView id={state.projects[0].id} />
}
