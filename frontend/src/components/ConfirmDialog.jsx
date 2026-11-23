import Modal from './Modal'

export default function ConfirmDialog({ title = 'Please confirm', message, confirmLabel = 'Confirm', danger = false, busy = false, onConfirm, onCancel }) {
  return (
    <Modal
      title={title}
      onClose={onCancel}
      footer={
        <>
          <button className="btn-secondary" onClick={onCancel} disabled={busy}>Cancel</button>
          <button className={danger ? 'btn bg-red-600 text-white hover:bg-red-700' : 'btn-primary'} onClick={onConfirm} disabled={busy}>
            {busy ? 'Working…' : confirmLabel}
          </button>
        </>
      }
    >
      <div className="text-sm text-slate-600">{message}</div>
    </Modal>
  )
}
