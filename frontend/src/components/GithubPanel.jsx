import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, Lock } from 'lucide-react'
import { githubService } from '../services/adminService'
import { errorMessage, fieldErrors } from '../services/api'
import Alert from './Alert'
import Spinner from './Spinner'

const GITHUB_RE = /^https:\/\/(www\.)?github\.com\/[A-Za-z0-9][A-Za-z0-9-]{0,38}\/[A-Za-z0-9._-]{1,100}?(\.git)?\/?$/

/** View (everyone with access) and edit (students, after SRS approval) the project's GitHub repository. */
export default function GithubPanel({ projectId }) {
  const [state, setState] = useState(null)
  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')
  const [urlError, setUrlError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const apply = useCallback((s) => {
    setState(s); setUrl(s.repository?.url || ''); setDescription(s.repository?.description || '')
  }, [])
  const load = useCallback(() => githubService.get(projectId).then(apply).catch((e) => setError(errorMessage(e))), [projectId, apply])
  useEffect(() => { load() }, [load])

  const save = async (e) => {
    e.preventDefault()
    setError(''); setUrlError(''); setNotice('')
    if (!GITHUB_RE.test(url.trim())) return setUrlError('Enter a valid GitHub repository URL, e.g. https://github.com/owner/repo')
    setBusy(true)
    try { apply(await githubService.set(projectId, url.trim(), description)); setNotice('Repository saved.') }
    catch (err) { setError(errorMessage(err)); setUrlError(fieldErrors(err).url || '') } finally { setBusy(false) }
  }

  if (!state) return error ? <Alert>{error}</Alert> : <Spinner />
  const repo = state.repository

  return (
    <section className="card space-y-3" aria-label="GitHub repository">
      <h2 className="font-semibold text-slate-900">GitHub repository</h2>
      <Alert>{error}</Alert>
      {notice && <Alert type="success">{notice}</Alert>}
      {repo && (
        <div className="text-sm">
          <a href={repo.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-brand underline">{repo.url}<ExternalLink className="h-3.5 w-3.5" /></a>
          {repo.description && <p className="mt-1 text-slate-700">{repo.description}</p>}
        </div>
      )}
      {!repo && !state.can_edit && <p className="text-sm text-slate-500">No repository has been added yet.</p>}
      {state.can_edit && !state.implementation_unlocked && (
        <p className="flex items-center gap-2 text-sm text-slate-500"><Lock className="h-4 w-4" />You can add your repository once your SRS is approved.</p>
      )}
      {state.can_edit && state.implementation_unlocked && (
        <form onSubmit={save} className="space-y-3">
          <div>
            <label htmlFor="gh-url" className="label">Repository URL</label>
            <input id="gh-url" className="input" placeholder="https://github.com/owner/repo" value={url} onChange={(e) => setUrl(e.target.value)} />
            {urlError && <p className="mt-1 text-xs text-red-600">{urlError}</p>}
          </div>
          <div>
            <label htmlFor="gh-desc" className="label">Project description</label>
            <textarea id="gh-desc" className="input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : repo ? 'Update repository' : 'Save repository'}</button>
        </form>
      )}
    </section>
  )
}
