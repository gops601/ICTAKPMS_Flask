import { useCallback, useEffect, useRef, useState } from 'react'
import { Calendar, GripVertical, MessageSquare, Plus, Upload } from 'lucide-react'
import { scrumService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Alert from './Alert'
import Spinner from './Spinner'
import StatusBadge from './StatusBadge'
import TaskModal from './TaskModal'
import BulkTasksModal from './BulkTasksModal'

const PRIORITY_TONE = { low: 'grey', medium: 'blue', high: 'orange', critical: 'red' }

/** Move a task inside a board object (optimistic update, mirrors the server's resequencing). */
export function applyMove(board, taskId, status, index) {
  let moved
  const columns = board.columns.map((c) => {
    const rest = c.tasks.filter((t) => { if (t.id === taskId) { moved = t; return false } return true })
    return { ...c, tasks: rest }
  })
  if (!moved) return board
  return {
    ...board,
    columns: columns.map((c) => {
      if (c.status !== status) return { ...c, tasks: c.tasks.map((t, i) => ({ ...t, position: i })) }
      const at = index == null ? c.tasks.length : Math.max(0, Math.min(index, c.tasks.length))
      const next = [...c.tasks]
      next.splice(at, 0, { ...moved, status })
      return { ...c, tasks: next.map((t, i) => ({ ...t, position: i })) }
    }),
  }
}

function TaskCard({ task, canMove, columns, onOpen, onDragStart, onDropOn, onMoveSelect }) {
  return (
    <li
      draggable={canMove}
      onDragStart={(e) => onDragStart(e, task)}
      onDragOver={(e) => canMove && e.preventDefault()}
      onDrop={(e) => onDropOn(e, task)}
      data-testid={`task-${task.id}`}
      className={`rounded-lg border bg-white p-3 shadow-sm ${task.is_overdue ? 'border-red-300' : 'border-slate-200'} ${canMove ? 'cursor-grab' : ''}`}
    >
      <div className="flex items-start gap-2">
        {canMove && <GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden />}
        <button className="min-w-0 flex-1 text-left" onClick={() => onOpen(task)} aria-label={`Open task ${task.title}`}>
          <span className="block text-sm font-medium text-slate-900">{task.title}</span>
        </button>
        <StatusBadge tone={PRIORITY_TONE[task.priority]}>{task.priority}</StatusBadge>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
        <span>#{task.id}</span>
        {(task.assignees?.length ? task.assignees : task.assignee ? [task.assignee] : []).length > 0 && <span>{(task.assignees?.length ? task.assignees : [task.assignee]).map((a) => a.name).join(', ')}</span>}
        {task.due_date && (
          <span className={`inline-flex items-center gap-1 ${task.is_overdue ? 'font-medium text-red-600' : ''}`}>
            <Calendar className="h-3 w-3" />{task.due_date}{task.is_overdue ? ' · overdue' : ''}
          </span>
        )}
        {task.comment_count > 0 && <span className="inline-flex items-center gap-1"><MessageSquare className="h-3 w-3" />{task.comment_count}</span>}
      </div>
      {canMove && (
        <select aria-label={`Move ${task.title} to column`} className="mt-2 w-full rounded border border-slate-200 bg-slate-50 px-1.5 py-1 text-xs"
          value={task.status} onChange={(e) => onMoveSelect(task, e.target.value)}>
          {columns.map((c) => <option key={c.status} value={c.status}>{c.label}</option>)}
        </select>
      )}
    </li>
  )
}

/** Jira-style board. Drag & drop uses native HTML5 events; every card also has a "move to" select for keyboard/touch use. */
export default function ScrumBoard({ projectId }) {
  const [board, setBoard] = useState(null)
  const [error, setError] = useState('')
  const [modal, setModal] = useState(null) // { taskId } | 'new' | 'bulk'
  const dragId = useRef(null)

  const load = useCallback(async () => {
    try { setBoard(await scrumService.board(projectId)); setError('') } catch (e) { setError(errorMessage(e)) }
  }, [projectId])
  useEffect(() => { load() }, [load])

  const moveTo = async (taskId, status, index) => {
    const before = board
    setBoard((b) => applyMove(b, taskId, status, index))          // optimistic
    try { setBoard(await scrumService.move(taskId, status, index)); setError('') }
    catch (e) { setBoard(before); setError(errorMessage(e)) }
  }

  const onDragStart = (e, task) => {
    dragId.current = task.id
    if (e.dataTransfer) { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(task.id)) }
  }
  const dropOnCard = (e, task) => {
    e.preventDefault(); e.stopPropagation()
    const id = dragId.current; dragId.current = null
    if (!id || id === task.id) return
    // Insert before the card that was dropped on, counting positions without the dragged card
    // (the same convention the server uses when it resequences the column).
    const rest = board.columns.find((c) => c.status === task.status).tasks.filter((t) => t.id !== id)
    const index = rest.findIndex((t) => t.id === task.id)
    moveTo(id, task.status, index)
  }
  const dropOnColumn = (e, status) => {
    e.preventDefault()
    const id = dragId.current; dragId.current = null
    if (id) moveTo(id, status, null)
  }

  if (!board) return error ? <Alert>{error}</Alert> : <Spinner />
  const { permissions: perms, stats } = board

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-600" aria-label="Board summary">
          <span>{stats.total} tasks</span><span>{stats.completed} done ({stats.completion_pct}%)</span>
          <span className={stats.overdue ? 'font-medium text-red-600' : ''}>{stats.overdue} overdue</span>
        </div>
        {perms.can_create && (
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary" onClick={() => setModal('bulk')}><Upload className="h-4 w-4" />Bulk upload</button>
            <button className="btn-primary" onClick={() => setModal('new')}><Plus className="h-4 w-4" />New task</button>
          </div>
        )}
      </div>
      <Alert>{error}</Alert>
      {perms.reason && <Alert type="info">{perms.reason}</Alert>}

      <div className="grid gap-3 overflow-x-auto pb-2 md:grid-cols-5" style={{ minWidth: 0 }}>
        {board.columns.map((c) => (
          <section key={c.status} aria-label={c.label} className="flex min-h-[200px] min-w-[220px] flex-col rounded-xl bg-slate-200/60 p-2"
            onDragOver={(e) => perms.can_move && e.preventDefault()} onDrop={(e) => dropOnColumn(e, c.status)} data-testid={`col-${c.status}`}>
            <h3 className="mb-2 flex items-center justify-between px-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
              {c.label}<span className="rounded-full bg-white px-2 py-0.5 text-[11px]">{c.tasks.length}</span>
            </h3>
            <ul className="flex-1 space-y-2">
              {c.tasks.map((t) => (
                <TaskCard key={t.id} task={t} canMove={perms.can_move} columns={board.columns}
                  onOpen={(task) => setModal({ taskId: task.id })} onDragStart={onDragStart} onDropOn={dropOnCard}
                  onMoveSelect={(task, status) => moveTo(task.id, status, null)} />
              ))}
              {c.tasks.length === 0 && <li className="px-1 py-4 text-center text-xs text-slate-500">No tasks</li>}
            </ul>
          </section>
        ))}
      </div>

      {modal === 'bulk' && <BulkTasksModal projectId={projectId} onClose={() => setModal(null)} onDone={(b) => b && setBoard(b)} />}
      {modal && modal !== 'bulk' && (
        <TaskModal projectId={projectId} taskId={modal === 'new' ? null : modal.taskId} members={board.members} permissions={perms}
          onClose={() => setModal(null)} onChanged={load} />
      )}
    </div>
  )
}
