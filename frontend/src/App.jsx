import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import RoleRoute from './routes/RoleRoute'
import AppLayout from './layouts/AppLayout'
import Login from './pages/common/Login'
import ForgotPassword from './pages/common/ForgotPassword'
import ResetPassword from './pages/common/ResetPassword'
import Profile from './pages/common/Profile'
import ChangePassword from './pages/common/ChangePassword'
import Spinner from './components/Spinner'
import DateRequestsPage from './pages/common/DateRequestsPage'

// Charts pull in Recharts (large); load dashboards and reports on demand to keep the first paint light.
const AdminDashboard = lazy(() => import('./pages/common/Dashboards').then((m) => ({ default: m.AdminDashboard })))
const LeadDashboard = lazy(() => import('./pages/common/Dashboards').then((m) => ({ default: m.LeadDashboard })))
const MentorDashboard = lazy(() => import('./pages/common/Dashboards').then((m) => ({ default: m.MentorDashboard })))
const StudentDashboard = lazy(() => import('./pages/common/Dashboards').then((m) => ({ default: m.StudentDashboard })))
const ReportsPage = lazy(() => import('./pages/common/ReportsPage'))
import OUManagement from './pages/admin/OUManagement'
import DomainManagement from './pages/admin/DomainManagement'
import BatchList from './pages/admin/BatchList'
import BatchForm from './pages/admin/BatchForm'
import UploadCenter from './pages/admin/UploadCenter'
import StudentManagement from './pages/admin/StudentManagement'
import UserManagement from './pages/admin/UserManagement'
import ProblemStatementList from './pages/domain_lead/ProblemStatementList'
import ProblemStatementForm from './pages/domain_lead/ProblemStatementForm'
import ProblemStatementDetail from './pages/domain_lead/ProblemStatementDetail'
import ProblemStatementUpload from './pages/domain_lead/ProblemStatementUpload'
import Notifications from './pages/common/Notifications'
import ProjectDetailPage from './pages/common/ProjectDetailPage'
import ProjectList from './pages/common/ProjectList'
import MyBatches from './pages/common/MyBatches'
import BatchDetail from './pages/common/BatchDetail'
import AllocatePage from './pages/common/AllocatePage'
import MentorWorkload from './pages/common/MentorWorkload'
import MyProject from './pages/student/MyProject'
import MyProposal from './pages/student/MyProposal'
import ProposalApprovals from './pages/mentor/ProposalApprovals'
import { SrsProjectPage, SrsQueuePage, StudentGithubPage, StudentSrsPage } from './pages/common/SrsPages'
import { ScrumOverviewPage, ScrumProjectPage, StudentScrumPage } from './pages/common/ScrumPages'
import { EvaluationQueuePage, ProjectReviewsPage, ReviewPage, StudentReviewsPage, TemplatesPage } from './pages/common/ReviewPages'
import { ROLE_HOME } from './utils/roles'

/** Project Shelf pages are shared by admins and domain leads (access is enforced by the API). */
const psRoutes = (base) => (
  <>
    <Route path={`${base}/project-shelf`} element={<ProblemStatementList />} />
    <Route path={`${base}/project-shelf/new`} element={<ProblemStatementForm />} />
    <Route path={`${base}/project-shelf/upload`} element={<ProblemStatementUpload />} />
    <Route path={`${base}/project-shelf/:id`} element={<ProblemStatementDetail />} />
    <Route path={`${base}/project-shelf/:id/edit`} element={<ProblemStatementForm />} />
  </>
)

function RootRedirect() {
  const { user, loading } = useAuth()
  if (loading) return null
  return <Navigate to={user ? ROLE_HOME[user.role] : '/login'} replace />
}

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password/:token" element={<ResetPassword />} />

      <Route element={<RoleRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/profile" element={<Profile />} />
          <Route path="/change-password" element={<ChangePassword />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
          <Route path="/srs/:projectId" element={<SrsProjectPage />} />
          <Route path="/scrum/:projectId" element={<ScrumProjectPage />} />
          <Route path="/reviews/project/:projectId" element={<ProjectReviewsPage />} />
          <Route path="/reviews/:reviewId" element={<ReviewPage />} />
          <Route path="/project-shelf/:id" element={<ProblemStatementDetail />} />

          <Route element={<RoleRoute roles={['admin']} />}>
            <Route path="/admin" element={<AdminDashboard />} />
            <Route path="/admin/reports" element={<ReportsPage />} />
            <Route path="/admin/ous" element={<OUManagement />} />
            <Route path="/admin/domains" element={<DomainManagement />} />
            <Route path="/admin/batches" element={<BatchList />} />
            <Route path="/admin/batches/new" element={<BatchForm />} />
            <Route path="/admin/batches/upload" element={<Navigate to="/admin/uploads?tab=batches" replace />} />
            <Route path="/admin/uploads" element={<UploadCenter />} />
            <Route path="/admin/domain-leads" element={<UserManagement fixedRole="domain_lead" title="Domain Leads" subtitle="Create domain lead accounts, then assign them to domains under Domains." addLabel="Add domain lead" />} />
            <Route path="/admin/mentors" element={<UserManagement fixedRole="mentor" title="Mentors" subtitle="Create mentor accounts. Batch assignment is done by the Domain Lead." addLabel="Add mentor" />} />
            <Route path="/admin/batches/:id" element={<BatchForm />} />
            <Route path="/admin/students" element={<StudentManagement />} />
            <Route path="/admin/students/upload" element={<Navigate to="/admin/uploads?tab=students" replace />} />
            <Route path="/admin/users" element={<UserManagement />} />
            <Route path="/admin/batches/:id/overview" element={<BatchDetail />} />
            <Route path="/admin/batches/:id/allocate" element={<AllocatePage />} />
            <Route path="/admin/srs" element={<SrsQueuePage />} />
            <Route path="/admin/scrum" element={<ScrumOverviewPage />} />
            <Route path="/admin/evaluations" element={<EvaluationQueuePage />} />
            <Route path="/admin/date-requests" element={<DateRequestsPage />} />
            <Route path="/admin/projects" element={<ProjectList title="All Projects" subtitle="Every project across OUs and domains." />} />
            {psRoutes('/admin')}
          </Route>
          <Route element={<RoleRoute roles={['domain_lead']} />}>
            <Route path="/lead" element={<LeadDashboard />} />
            <Route path="/lead/reports" element={<ReportsPage />} />
            <Route path="/lead/batches" element={<MyBatches />} />
            <Route path="/lead/batches/:id" element={<BatchDetail />} />
            <Route path="/lead/batches/:id/allocate" element={<AllocatePage />} />
            <Route path="/lead/srs" element={<SrsQueuePage />} />
            <Route path="/lead/scrum" element={<ScrumOverviewPage />} />
            <Route path="/lead/evaluations" element={<EvaluationQueuePage />} />
            <Route path="/lead/date-requests" element={<DateRequestsPage />} />
            <Route path="/lead/mentors" element={<MentorWorkload />} />
            <Route path="/lead/projects" element={<ProjectList title="Project Monitoring" subtitle="Student-wise progress, SRS status and delays in your domain." />} />
            {psRoutes('/lead')}
          </Route>
          <Route element={<RoleRoute roles={['mentor']} />}>
            <Route path="/mentor" element={<MentorDashboard />} />
            <Route path="/mentor/reports" element={<ReportsPage title="Project Reports" />} />
            <Route path="/mentor/batches" element={<MyBatches />} />
            <Route path="/mentor/batches/:id" element={<BatchDetail />} />
            <Route path="/mentor/batches/:id/allocate" element={<AllocatePage />} />
            <Route path="/mentor/proposals" element={<ProposalApprovals />} />
            <Route path="/mentor/project-shelf" element={<ProblemStatementList />} />
            <Route path="/mentor/project-shelf/:id" element={<ProblemStatementDetail />} />
            <Route path="/mentor/srs" element={<SrsQueuePage />} />
            <Route path="/mentor/scrum" element={<ScrumOverviewPage />} />
            <Route path="/mentor/evaluations" element={<EvaluationQueuePage />} />
            <Route path="/mentor/date-requests" element={<DateRequestsPage />} />
            <Route path="/mentor/templates" element={<TemplatesPage />} />
            <Route path="/mentor/projects" element={<ProjectList title="My Projects" subtitle="Projects you mentor." />} />
          </Route>
          <Route element={<RoleRoute roles={['student']} />}>
            <Route path="/student" element={<StudentDashboard />} />
            <Route path="/student/project" element={<MyProject />} />
            <Route path="/student/proposal" element={<MyProposal />} />
            <Route path="/student/feedback" element={<Navigate to="/student/project" replace />} />
            <Route path="/student/srs" element={<StudentSrsPage />} />
            <Route path="/student/scrum" element={<StudentScrumPage />} />
            <Route path="/student/reviews" element={<StudentReviewsPage />} />
            <Route path="/student/github" element={<StudentGithubPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<RootRedirect />} />
    </Routes>
    </Suspense>
  )
}
