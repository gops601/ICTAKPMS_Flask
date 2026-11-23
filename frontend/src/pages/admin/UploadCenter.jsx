import { Link, useSearchParams } from 'react-router-dom'
import { PencilLine } from 'lucide-react'
import ImportWizard from '../../components/ImportWizard'
import PageHeader from '../../components/PageHeader'

const TABS = [
  { key: 'batches', label: 'Batches', manual: { to: '/admin/batches/new', label: 'Add a batch manually' } },
  { key: 'students', label: 'Students', manual: { to: '/admin/students?add=1', label: 'Add a student manually' } },
]

/** One window for both imports: upload an Excel/CSV file, or switch to the manual form. */
export default function UploadCenter() {
  const [params, setParams] = useSearchParams()
  const tab = TABS.find((t) => t.key === params.get('tab')) || TABS[0]

  return (
    <div>
      <PageHeader title="Bulk upload" subtitle="Upload batches or students from an OU-specific Excel/CSV template, or enter them manually."
        actions={<Link to={tab.manual.to} className="btn-secondary"><PencilLine className="h-4 w-4" />{tab.manual.label}</Link>} />
      <div role="tablist" className="mb-4 flex gap-2">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={t.key === tab.key} onClick={() => setParams({ tab: t.key })}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${t.key === tab.key ? 'bg-brand text-white' : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {/* key forces a fresh wizard (state) per tab */}
      <ImportWizard key={tab.key} type={tab.key} embedded />
    </div>
  )
}
