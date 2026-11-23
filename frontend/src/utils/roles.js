import {
  Bell, Briefcase, Building2, ClipboardCheck, FileSpreadsheet, FileText, FileUp, FolderKanban, Github, KanbanSquare, ListChecks, Star, BarChart3, CalendarClock, GraduationCap, KeyRound, Layers,
  LayoutDashboard, Network, Upload, UserCheck, UserCircle, UserCog, Users,
} from 'lucide-react'

export const ROLE_HOME = {
  admin: '/admin',
  domain_lead: '/lead',
  mentor: '/mentor',
  student: '/student',
}

export const ROLE_LABEL = {
  admin: 'Administrator',
  domain_lead: 'Domain Lead',
  mentor: 'Mentor',
  student: 'Student',
}

/**
 * Sidebar menus per role. Only routes that exist are listed; later phases append entries here
 * so navigation never contains dead links.
 */
export const ROLE_MENU = {
  admin: [
    { to: '/admin', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/admin/ous', label: 'Organisational Units', icon: Building2 },
    { to: '/admin/domains', label: 'Domains', icon: Network },
    { to: '/admin/batches', label: 'Batches', icon: Layers },
    { to: '/admin/students', label: 'Students', icon: GraduationCap },
    { to: '/admin/domain-leads', label: 'Domain Leads', icon: UserCog },
    { to: '/admin/mentors', label: 'Mentors', icon: UserCheck },
    { to: '/admin/problem-statements', label: 'Problem Statements', icon: FileText },
    { to: '/admin/projects', label: 'Projects', icon: FolderKanban },
    { to: '/admin/srs', label: 'SRS Queue', icon: ClipboardCheck },
    { to: '/admin/scrum', label: 'Scrum Monitoring', icon: KanbanSquare },
    { to: '/admin/evaluations', label: 'Evaluations', icon: ListChecks },
    { to: '/admin/date-requests', label: 'Date Approvals', icon: CalendarClock },
    { to: '/admin/reports', label: 'Reports', icon: BarChart3 },
    { to: '/admin/uploads', label: 'Bulk Upload', icon: FileSpreadsheet },
    { to: '/admin/users', label: 'All Users', icon: Users },
  ],
  domain_lead: [
    { to: '/lead', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/lead/batches', label: 'My Batches', icon: Layers },
    { to: '/lead/mentors', label: 'Mentors', icon: UserCheck },
    { to: '/lead/projects', label: 'Projects', icon: FolderKanban },
    { to: '/lead/srs', label: 'SRS Status', icon: ClipboardCheck },
    { to: '/lead/scrum', label: 'Scrum Monitoring', icon: KanbanSquare },
    { to: '/lead/evaluations', label: 'Review Monitoring', icon: ListChecks },
    { to: '/lead/date-requests', label: 'Date Approvals', icon: CalendarClock },
    { to: '/lead/reports', label: 'Reports', icon: BarChart3 },
    { to: '/lead/problem-statements', label: 'Problem Statements', icon: FileText, end: true },
    { to: '/lead/problem-statements/upload', label: 'Bulk Upload', icon: Upload },
  ],
  mentor: [
    { to: '/mentor', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/mentor/batches', label: 'My Batches', icon: Layers },
    { to: '/mentor/projects', label: 'My Projects', icon: FolderKanban },
    { to: '/mentor/srs', label: 'SRS Review', icon: ClipboardCheck },
    { to: '/mentor/scrum', label: 'Scrum Monitoring', icon: KanbanSquare },
    { to: '/mentor/evaluations', label: 'Weekly Evaluations', icon: ListChecks },
    { to: '/mentor/date-requests', label: 'Date Requests', icon: CalendarClock },
    { to: '/mentor/templates', label: 'Evaluation Templates', icon: Star },
    { to: '/mentor/reports', label: 'Project Reports', icon: BarChart3 },
  ],
  student: [
    { to: '/student', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/student/project', label: 'My Project', icon: Briefcase },
    { to: '/student/srs', label: 'SRS Submission', icon: FileUp },
    { to: '/student/github', label: 'GitHub Repository', icon: Github },
    { to: '/student/scrum', label: 'Scrum Board', icon: KanbanSquare },
    { to: '/student/reviews', label: 'Weekly Reviews', icon: ListChecks },
  ],
}

export const COMMON_MENU = [
  { to: '/notifications', label: 'Notifications', icon: Bell },
  { to: '/profile', label: 'Profile', icon: UserCircle },
  { to: '/change-password', label: 'Change Password', icon: KeyRound },
]
