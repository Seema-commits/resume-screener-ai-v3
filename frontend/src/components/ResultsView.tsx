import { AlertTriangle, Download, Scale } from 'lucide-react'
import { useState } from 'react'

import type { Candidate, ScreeningResult } from '../api/types'
import { candidatesCsv, downloadText } from '../lib/csv'
import { CandidateDrawer } from './CandidateDrawer'
import { DecisionBadge } from './DecisionBadge'
import { Alert, Button, Card } from './ui'

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card className="p-4">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </Card>
  )
}

function CandidateTable({ title, candidates, onOpen }: {
  title: string
  candidates: Candidate[]
  onOpen: (c: Candidate) => void
}) {
  if (!candidates.length) return null
  return (
    <section className="space-y-2">
      <h3 className="font-semibold">{title}</h3>
      <Card className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Candidate</th>
              <th className="px-4 py-3 font-medium">Score</th>
              <th className="px-4 py-3 font-medium">Decision</th>
              <th className="px-4 py-3 font-medium">Summary</th>
              <th className="px-4 py-3 font-medium">Flags</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {candidates.map(c => (
              <tr key={c.candidate_name} onClick={() => onOpen(c)}
                  className="cursor-pointer align-top hover:bg-slate-50">
                <td className="px-4 py-3">
                  <button className="font-medium text-indigo-700 hover:underline"
                          onClick={e => { e.stopPropagation(); onOpen(c) }}>
                    {c.candidate_name}
                  </button>
                  <div className="text-xs text-slate-500">{c.email}</div>
                  <div className="text-xs text-slate-500">{c.phone}</div>
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-medium">{c.score}/100</td>
                <td className="px-4 py-3">
                  <DecisionBadge decision={c.decision} />
                  <div className="mt-1 text-xs text-slate-500">{c.decision_reason}</div>
                </td>
                <td className="px-4 py-3 text-slate-700">{c.summary || c.recommendation}</td>
                <td className="px-4 py-3 text-slate-700">
                  {c.flags.length
                    ? <span className="inline-flex items-center gap-1"><AlertTriangle className="size-3.5 text-amber-500" aria-hidden />
                        {c.flags[0].description}{c.flags.length > 1 && ` (+${c.flags.length - 1} more)`}</span>
                    : <span className="text-slate-400">None</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </section>
  )
}

/** The full results of one screening - used by Screen Resumes and Scan Detail. */
export function ResultsView({ result }: { result: ScreeningResult }) {
  const [open, setOpen] = useState<Candidate | null>(null)
  const { shortlisted_candidates: shortlisted, rejected_candidates: rest, run_stats: stats } = result
  const profiles = new Map(result.parsed_profiles.map(p => [p.candidate_name, p]))
  const weights = result.criteria_weights

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Total screened" value={shortlisted.length + rest.length} />
        <Stat label="Shortlisted" value={shortlisted.length} />
        <Stat label="Not shortlisted" value={rest.length} />
      </div>

      {!!stats?.suspicious && (
        <Alert tone="warning">
          🛡 {stats.suspicious} resume(s) contain text that looks like instructions to the AI.
          They are flagged for manual review - see each candidate's Flags tab.
        </Alert>
      )}
      {!!stats?.reused && (
        <p className="text-sm text-slate-500">
          Screened {stats.screened_now} new resume(s) with AI; reused earlier results for {stats.reused}.
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        {weights && (
          <p className="inline-flex items-center gap-2 text-sm text-slate-600">
            <Scale className="size-4" aria-hidden /> Scoring weights:{' '}
            {Object.entries(weights).map(([k, v]) => `${k} ${v}`).join(' · ')}
          </p>
        )}
        <Button variant="secondary"
                onClick={() => downloadText('screening_results.csv', candidatesCsv(shortlisted, rest))}>
          <Download className="size-4" aria-hidden /> Download CSV
        </Button>
      </div>

      <CandidateTable title="Shortlisted" candidates={shortlisted} onOpen={setOpen} />
      <CandidateTable title="Not shortlisted" candidates={rest} onOpen={setOpen} />

      {open && (
        <CandidateDrawer candidate={open} profile={profiles.get(open.candidate_name)}
                         onClose={() => setOpen(null)} />
      )}
    </div>
  )
}
