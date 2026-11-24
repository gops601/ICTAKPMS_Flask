import api from './api'

const d = (r) => r.data.data
const withMeta = (r) => ({ items: r.data.data, meta: r.data.meta })

export const ouService = {
  list: (params) => api.get('/ous', { params }).then(d),
  get: (id) => api.get(`/ous/${id}`).then(d),
  create: (body) => api.post('/ous', body).then(d),
  update: (id, body) => api.put(`/ous/${id}`, body).then(d),
  remove: (id) => api.delete(`/ous/${id}`).then(d),
  setActive: (id, is_active) => api.patch(`/ous/${id}/active`, { is_active }).then(d),
  fields: (id, params) => api.get(`/ous/${id}/fields`, { params }).then(d),
  addField: (id, body) => api.post(`/ous/${id}/fields`, body).then(d),
  updateField: (fieldId, body) => api.put(`/ous/fields/${fieldId}`, body).then(d),
}

export const domainService = {
  list: (params) => api.get('/domains', { params }).then(d),
  create: (body) => api.post('/domains', body).then(d),
  update: (id, body) => api.put(`/domains/${id}`, body).then(d),
  setActive: (id, is_active) => api.patch(`/domains/${id}/active`, { is_active }).then(d),
  setLeads: (id, user_ids) => api.put(`/domains/${id}/leads`, { user_ids }).then(d),
  remove: (id) => api.delete(`/domains/${id}`).then(d),
  removeSubdomain: (subId) => api.delete(`/domains/subdomains/${subId}`).then(d),
  addSubdomain: (id, name) => api.post(`/domains/${id}/subdomains`, { name }).then(d),
  updateSubdomain: (subId, body) => api.patch(`/domains/subdomains/${subId}`, body).then(d),
}

export const batchService = {
  list: (params) => api.get('/batches', { params }).then(withMeta),
  get: (id) => api.get(`/batches/${id}`).then(d),
  create: (body) => api.post('/batches', body).then(d),
  update: (id, body) => api.put(`/batches/${id}`, body).then(d),
  setStatus: (id, status) => api.patch(`/batches/${id}/status`, { status }).then(d),
  remove: (id, withStudents = false) => api.delete(`/batches/${id}`, { params: withStudents ? { with_students: 1 } : undefined }).then(d),
  setProjectDates: (id, project_start_date, project_end_date) => api.put(`/batches/${id}/project-dates`, { project_start_date, project_end_date }).then(d),
}

export const studentService = {
  list: (params) => api.get('/students', { params }).then(withMeta),
  credentials: (batch_id, student_ids) => api.post('/students/credentials', { batch_id, student_ids }).then(d),
  create: (body) => api.post('/students', body).then(d),
}

export const portalService = {
  list: () => api.get('/admin/portals').then(d),
  create: (body) => api.post('/admin/portals', body).then(d),
  update: (id, body) => api.put(`/admin/portals/${id}`, body).then(d),
  rotateSecret: (id) => api.post(`/admin/portals/${id}/rotate-secret`).then(d),
  sync: (id) => api.post(`/admin/portals/${id}/sync`).then(d),
  remove: (id) => api.delete(`/admin/portals/${id}`).then(d),
  guide: () => downloadFile('/admin/portals/integration-guide', undefined, 'ICTAK-portal-integration-guide.md'),
  /** Configuration file for the other portal. When the one-time `secret` is passed it is written into the file. */
  config: async (portal, format = 'json', secret = null) => {
    const res = await api.get(`/admin/portals/${portal.id}/config`, { params: { format }, responseType: 'text', transformResponse: (x) => x })
    const text = secret ? res.data.replace('<PASTE_SHARED_SECRET_HERE>', secret) : res.data
    downloadTextFile(text, format === 'env' ? `${portal.slug}-ictak.env` : `${portal.slug}-ictak-config.json`, format === 'env' ? 'text/plain' : 'application/json')
  },
}

export const userService = {
  list: (params) => api.get('/admin/users', { params }).then(withMeta),
  create: (body) => api.post('/admin/users', body).then(d),
  resetPassword: (id) => api.post(`/admin/users/${id}/reset-password`, {}).then(d),
  credentials: (role, user_ids, include_active = false) => api.post('/admin/users/credentials', { role, user_ids, include_active }).then(d),
  remove: (id) => api.delete(`/admin/users/${id}`).then(d),
  setDomains: (id, domain_ids) => api.put(`/admin/users/${id}/domains`, { domain_ids }).then(d),
  setActive: (id, is_active) => api.patch(`/admin/users/${id}/active`, { is_active }).then(d),
  mentors: (params) => api.get('/mentors', { params }).then(withMeta),
}

export const importService = {
  upload: (type, ouId, file) => {
    const form = new FormData()
    if (ouId) form.append('ou_id', ouId)
    form.append('file', file)
    return api.post(`/imports/${type}`, form).then(d)
  },
  get: (id) => api.get(`/imports/${id}`).then(d),
  confirm: (id, import_valid_only = false) => api.post(`/imports/${id}/confirm`, { import_valid_only }).then(d),
}

/** Download an authenticated file (template / error report) through axios so the JWT is sent. */
export async function downloadFile(url, params, fallbackName) {
  const res = await api.get(url, { params, responseType: 'blob' })
  const match = /filename="?([^";]+)"?/.exec(res.headers['content-disposition'] || '')
  const link = document.createElement('a')
  link.href = URL.createObjectURL(res.data)
  link.download = match ? match[1] : fallbackName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(link.href)
}

export function downloadTextFile(text, filename, mime = 'text/csv') {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([text], { type: mime }))
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(link.href)
}

export const psService = {
  list: (params) => api.get('/problem-statements', { params }).then(withMeta),
  get: (id) => api.get(`/problem-statements/${id}`).then(d),
  create: (body) => api.post('/problem-statements', body).then(d),
  update: (id, body) => api.put(`/problem-statements/${id}`, body).then(d),
  setStatus: (id, status) => api.patch(`/problem-statements/${id}/status`, { status }).then(d),
  remove: (id) => api.delete(`/problem-statements/${id}`).then(d),
  industries: () => api.get('/problem-statements/industries').then(d),
  upload: (id, kind, file, description) => {
    const form = new FormData()
    form.append('file', file)
    if (description) form.append('description', description)
    return api.post(`/problem-statements/${id}/${kind}`, form).then(d)
  },
  removeFile: (id, kind, linkId) => api.delete(`/problem-statements/${id}/${kind}/${linkId}`).then(d),
  download: (id, kind, link) =>
    downloadFile(`/problem-statements/${id}/${kind}/${link.id}/download`, undefined, link.name),
}

export const proposalService = {
  mine: () => api.get('/proposals/mine').then(d),
  list: (params) => api.get('/proposals', { params }).then(withMeta),
  submit: (title, summary, file, datasets = [], subdomainId = null, dataSheet = null) => {
    const form = new FormData()
    form.append('title', title)
    if (summary) form.append('summary', summary)
    if (subdomainId) form.append('subdomain_id', subdomainId)
    form.append('file', file)
    datasets.forEach((f) => form.append('datasets', f))
    if (dataSheet) form.append('data_sheet', dataSheet)
    return api.post('/proposals', form).then(d)
  },
  projectTemplate: (format = 'xlsx') => downloadFile('/proposals/project-template', { format }, `project_template.${format}`),
  dataTemplate: () => downloadFile('/proposals/data-template', undefined, 'data-collection-template.xlsx'),
  downloadDataset: (p, ds) => downloadFile(`/proposals/${p.id}/datasets/${ds.id}/download`, undefined, ds.name),
  review: (id, decision, remarks) => api.post(`/proposals/${id}/review`, { decision, remarks }).then(d),
  download: (p) => downloadFile(`/proposals/${p.id}/download`, undefined, p.file.name),
}

export const projectService = {
  list: (params) => api.get('/projects', { params }).then(withMeta),
  get: (id) => api.get(`/projects/${id}`).then(d),
  timeline: (id) => api.get(`/projects/${id}/timeline`).then(d),
  allocate: (body) => api.post('/project-allocation', body).then(d),
  transition: (id, to, reason) => api.post(`/projects/${id}/transition`, { to, reason }).then(d),
  close: (id) => api.post(`/projects/${id}/close`).then(d),
  reopen: (id, to, reason) => api.post(`/projects/${id}/reopen`, { to, reason }).then(d),
  setMentors: (id, mentor_ids, reason) => api.put(`/projects/${id}/mentors`, { mentor_ids, reason: reason || null }).then(d),
  setMentor: (id, mentor_id, reason) => api.put(`/projects/${id}/mentor`, { mentor_id, reason: reason || null }).then(d),
  remove: (id) => api.delete(`/projects/${id}`).then(d),
  setBoardPermission: (id, mentor_can_edit_board) => api.patch(`/projects/${id}/settings`, { mentor_can_edit_board }).then(d),
  reassignProblem: (id, problem_statement_id) => api.post(`/projects/${id}/reassign-problem`, { problem_statement_id }).then(d),
}

export const feedbackService = {
  list: (projectId) => api.get(`/projects/${projectId}/feedback`).then(d),
  send: (projectId, message, student_id) => api.post(`/projects/${projectId}/feedback`, { message, student_id }).then(d),
}

export const batchMentorService = {
  list: (batchId) => api.get(`/batches/${batchId}/mentors`).then(d),
  assign: (batchId, mentor_id) => api.post(`/batches/${batchId}/mentors`, { mentor_id }).then(d),
  assignDomain: (batchId) => api.post(`/batches/${batchId}/mentors/assign-domain`).then(d),
  remove: (batchId, mentorId) => api.delete(`/batches/${batchId}/mentors/${mentorId}`).then(d),
  reassign: (batchId, mentorId, to_mentor_id) => api.post(`/batches/${batchId}/mentors/${mentorId}/reassign`, { to_mentor_id }).then(d),
}

export const notificationService = {
  list: (params) => api.get('/notifications', { params }).then(withMeta),
  unreadCount: () => api.get('/notifications/unread-count').then((r) => r.data.data.count),
  markRead: (id) => api.post(`/notifications/${id}/read`).then(d),
  readAll: () => api.post('/notifications/read-all').then(d),
}

export const srsService = {
  get: (projectId) => api.get(`/srs/projects/${projectId}`).then(d),
  submit: (projectId, file, description) => {
    const form = new FormData()
    form.append('file', file)
    if (description) form.append('description', description)
    return api.post(`/srs/projects/${projectId}`, form).then(d)
  },
  review: (submissionId, decision, remarks) => api.post(`/srs/submissions/${submissionId}/review`, { decision, remarks }).then(d),
  queue: (params) => api.get('/srs/queue', { params }).then(withMeta),
  download: (submission) => downloadFile(`/srs/submissions/${submission.id}/download`, undefined, submission.file.name),
}

export const githubService = {
  get: (projectId) => api.get(`/github/projects/${projectId}`).then(d),
  set: (projectId, url, description) => api.put(`/github/projects/${projectId}`, { url, description }).then(d),
}

export const scrumService = {
  board: (projectId) => api.get(`/scrum/projects/${projectId}/board`).then(d),
  task: (id) => api.get(`/scrum/tasks/${id}`).then(d),
  create: (projectId, body) => api.post(`/scrum/projects/${projectId}/tasks`, body).then(d),
  update: (id, body) => api.put(`/scrum/tasks/${id}`, body).then(d),
  move: (id, status, position) => api.patch(`/scrum/tasks/${id}/move`, { status, position }).then(d),
  remove: (id) => api.delete(`/scrum/tasks/${id}`).then(d),
  comment: (id, body) => api.post(`/scrum/tasks/${id}/comments`, { body }).then(d),
  overview: (params) => api.get('/scrum/overview', { params }).then(withMeta),
}

export const reviewService = {
  forProject: (projectId) => api.get(`/reviews/projects/${projectId}`).then(d),
  get: (id) => api.get(`/reviews/${id}`).then(d),
  save: (id, body) => api.put(`/reviews/${id}`, body).then(d),
  submit: (id, body) => api.post(`/reviews/${id}/submit`, body).then(d),
  reopen: (id, reason) => api.post(`/reviews/${id}/reopen`, { reason }).then(d),
  revisions: (id) => api.get(`/reviews/${id}/revisions`).then(d),
  applyTemplate: (id, template_id) => api.post(`/reviews/${id}/apply-template`, { template_id }).then(d),
  signoff: (projectId, remarks) => api.post(`/reviews/projects/${projectId}/final-signoff`, { remarks }).then(d),
  queue: (params) => api.get('/reviews/queue', { params }).then(withMeta),
}

export const templateService = {
  list: (params) => api.get('/evaluation-criteria/templates', { params }).then(d),
  create: (body) => api.post('/evaluation-criteria/templates', body).then(d),
  update: (id, body) => api.put(`/evaluation-criteria/templates/${id}`, body).then(d),
  remove: (id) => api.delete(`/evaluation-criteria/templates/${id}`).then(d),
  samples: () => api.post('/evaluation-criteria/templates/samples').then(d),
}

export const dashboardService = {
  get: (params) => api.get('/dashboard', { params }).then(d),
}

export const reportService = {
  list: () => api.get('/reports').then(d),
  get: (type, params) => api.get(`/reports/${type}`, { params }).then((r) => ({ ...r.data.data, meta: r.data.meta })),
  download: (type, format, params) => downloadFile(`/reports/${type}`, { ...params, format }, `${type}.${format}`),
  /** Detailed single-batch report: format 'xlsx' (all sheets) or 'csv' with sheet students|weekly|criteria. */
  batchDetailed: (batchId, format = 'xlsx', sheet) => downloadFile(`/reports/batch-detailed/${batchId}`, { format, sheet }, `batch_${batchId}_detailed_report.${format}`),
}

export const reviewDateService = {
  list: (params) => api.get('/review-date-requests', { params }).then(withMeta),
  history: (reviewId) => api.get(`/reviews/${reviewId}/date-requests`).then(d),
  create: (reviewId, new_date, reason) => api.post(`/reviews/${reviewId}/date-requests`, { new_date, reason }).then(d),
  decide: (id, decision, note) => api.post(`/review-date-requests/${id}/decision`, { decision, note }).then(d),
  cancel: (id) => api.post(`/review-date-requests/${id}/cancel`).then(d),
}
