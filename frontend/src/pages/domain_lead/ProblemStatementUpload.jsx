import ImportWizard from '../../components/ImportWizard'

export default function ProblemStatementUpload() {
  return (
    <ImportWizard type="problem_statements" title="Project Shelf bulk upload"
      subtitle="Upload an Excel/CSV file. Datasets and documents are attached afterwards on each statement (not embedded in cells)." />
  )
}
