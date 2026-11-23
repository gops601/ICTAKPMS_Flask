import { downloadTextFile } from '../services/adminService'

const HEADERS = ['Name', 'Login ID (email)', 'Temporary password', 'Registration number', 'Phone', 'Batch code', 'Batch name', 'Login URL']

// Spreadsheet apps execute cells that start with = + - @ ; neutralise them (names come from uploaded files).
const cell = (v) => {
  let s = String(v ?? '')
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`
  return `"${s.replace(/"/g, '""')}"`
}

/** CSV the admin can open in Excel and share: one row per student with the login and temporary password. */
export function credentialsCsv(rows, loginUrl = window.location.origin) {
  const lines = rows.map((r) => [r.name, r.email, r.temporary_password, r.registration_no, r.phone, r.batch_code, r.batch_name, loginUrl].map(cell).join(','))
  return `﻿${[HEADERS.map(cell).join(','), ...lines].join('\r\n')}\r\n`
}

export function downloadCredentials(rows, filename = 'student_credentials.csv') {
  downloadTextFile(credentialsCsv(rows), filename)
}

/** Build a credential row from the response of creating a single student. */
export function rowFromStudent(student) {
  return {
    name: student.name, email: student.email, phone: student.phone || '', registration_no: student.registration_no,
    batch_code: student.batch.code, batch_name: student.batch.name, temporary_password: student.temporary_password,
  }
}

const STAFF_HEADERS = ['Name', 'Login ID (email)', 'Temporary password', 'Role', 'Designation', 'Company', 'Details', 'Phone', 'Login URL']
const ROLE_NAME = { mentor: 'Mentor', domain_lead: 'Domain Lead' }

/** CSV of mentor / domain lead logins (one row each) with their one-time temporary passwords. */
export function staffCredentialsCsv(rows, loginUrl = window.location.origin) {
  const lines = rows.map((r) => [r.name, r.email, r.temporary_password, ROLE_NAME[r.role] || r.role, r.designation, r.company, r.details, r.phone, loginUrl].map(cell).join(','))
  return `\uFEFF${[STAFF_HEADERS.map(cell).join(','), ...lines].join('\r\n')}\r\n`
}

export function downloadStaffCredentials(rows, filename = 'credentials.csv') {
  downloadTextFile(staffCredentialsCsv(rows), filename)
}
