/** Renders one OU-configured field. Nothing here knows about specific OUs or field names. */
export default function DynamicField({ field, value, onChange, error }) {
  const id = `f-${field.field_key}`
  const common = { id, className: 'input', value: value ?? '', onChange: (e) => onChange(e.target.value) }
  let input
  if (field.field_type === 'select') {
    input = (
      <select {...common}>
        <option value="">Select…</option>
        {(field.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    )
  } else {
    const type = { number: 'number', date: 'date', email: 'email' }[field.field_type] || 'text'
    input = <input type={type} {...common} />
  }
  return (
    <div>
      <label htmlFor={id} className="label">{field.label}{field.is_required && <span className="text-red-600"> *</span>}</label>
      {input}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  )
}
