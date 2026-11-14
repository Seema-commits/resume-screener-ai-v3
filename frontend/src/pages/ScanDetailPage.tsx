import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { getScan } from '../api/endpoints'
import { ResultsView } from '../components/ResultsView'
import { Alert, Card, Spinner } from '../components/ui'

export function ScanDetailPage() {
  const id = Number(useParams().id)
  const valid = Number.isInteger(id) && id > 0
  const scan = useQuery({ queryKey: ['scan', id], queryFn: () => getScan(id), enabled: valid })

  return (
    <div className="space-y-6">
      <Link to="/scans" className="inline-flex items-center gap-1 text-sm text-indigo-700 hover:underline">
        <ArrowLeft className="size-4" aria-hidden /> Back to scan history
      </Link>
      {!valid && <Alert tone="error">That scan link isn't valid.</Alert>}
      {scan.isLoading && <Spinner />}
      {scan.error && <Alert tone="error">{scan.error.message}</Alert>}
      {scan.data && (
        <>
          <h1 className="text-2xl font-semibold">Scan #{id}</h1>
          {scan.data.jd_text && (
            <Card className="p-4">
              <details>
                <summary className="cursor-pointer text-sm font-medium">Job description</summary>
                <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{scan.data.jd_text}</p>
              </details>
            </Card>
          )}
          <ResultsView result={scan.data} />
        </>
      )}
    </div>
  )
}
