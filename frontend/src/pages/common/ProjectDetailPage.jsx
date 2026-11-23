import { useParams } from 'react-router-dom'
import ProjectView from '../../components/ProjectView'

export default function ProjectDetailPage() {
  const { id } = useParams()
  return <ProjectView key={id} id={id} />
}
