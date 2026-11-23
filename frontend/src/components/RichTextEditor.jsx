import { useEffect, useRef } from 'react'
import { Bold, Heading2, Italic, Link2, List, ListOrdered, Underline } from 'lucide-react'

const BUTTONS = [
  { cmd: 'bold', label: 'Bold', icon: Bold },
  { cmd: 'italic', label: 'Italic', icon: Italic },
  { cmd: 'underline', label: 'Underline', icon: Underline },
  { cmd: 'formatBlock', arg: 'h3', label: 'Heading', icon: Heading2 },
  { cmd: 'insertUnorderedList', label: 'Bullet list', icon: List },
  { cmd: 'insertOrderedList', label: 'Numbered list', icon: ListOrdered },
]

/**
 * Lightweight rich-text editor (no extra dependency). Emits HTML; the backend sanitises it
 * before storing, so the client never needs to be trusted.
 */
export default function RichTextEditor({ id, label, value, onChange, error }) {
  const ref = useRef(null)

  // Sync external value changes (e.g. loading an existing record) without resetting the caret while typing.
  useEffect(() => {
    if (ref.current && ref.current.innerHTML !== (value || '')) ref.current.innerHTML = value || ''
  }, [value])

  const run = (cmd, arg) => {
    ref.current?.focus()
    if (cmd === 'link') {
      const url = window.prompt('Link URL (https://…)')
      if (url) document.execCommand('createLink', false, url)
    } else {
      document.execCommand(cmd, false, arg)
    }
    onChange(ref.current.innerHTML)
  }

  return (
    <div>
      <label htmlFor={id} className="label">{label}</label>
      <div className="rounded-lg border border-slate-300 bg-white focus-within:ring-2 focus-within:ring-brand/30">
        <div className="flex gap-1 border-b border-slate-200 p-1">
          {BUTTONS.map(({ cmd, arg, label: l, icon: Icon }) => (
            <button key={l} type="button" title={l} aria-label={`${l} (${label})`} className="rounded p-1.5 text-slate-600 hover:bg-slate-100"
              onMouseDown={(e) => e.preventDefault()} onClick={() => run(cmd, arg)}>
              <Icon className="h-4 w-4" />
            </button>
          ))}
          <button type="button" title="Link" aria-label={`Link (${label})`} className="rounded p-1.5 text-slate-600 hover:bg-slate-100"
            onMouseDown={(e) => e.preventDefault()} onClick={() => run('link')}>
            <Link2 className="h-4 w-4" />
          </button>
        </div>
        <div id={id} ref={ref} role="textbox" aria-multiline="true" aria-label={label} contentEditable suppressContentEditableWarning
          className="rich-content min-h-[110px] px-3 py-2 text-sm focus:outline-none"
          onInput={(e) => onChange(e.currentTarget.innerHTML)} />
      </div>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  )
}
