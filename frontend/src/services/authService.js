import api from './api'

export const authService = {
  login: (email, password) => api.post('/auth/login', { email, password }).then((r) => r.data.data),
  me: () => api.get('/auth/me').then((r) => r.data.data),
  changePassword: (current_password, new_password) =>
    api.post('/auth/change-password', { current_password, new_password }).then((r) => r.data),
  forgotPassword: (email) => api.post('/auth/forgot-password', { email }).then((r) => r.data),
  resetPassword: (token, new_password) =>
    api.post('/auth/reset-password', { token, new_password }).then((r) => r.data),
}
