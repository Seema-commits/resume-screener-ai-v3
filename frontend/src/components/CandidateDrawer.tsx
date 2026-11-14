import clsx from 'clsx'
import { X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import type { Candidate, Profile } from '../api/types'
import { DecisionBadge, SeverityBadge } from './DecisionBadge'

const TABS = ['Overview', 'Scores', 'Phone screen', 'Flags', 'Profile'] as const
type Tab = (typeof TABS)[number]

function List({ items, empty = 'None' }: { items: string[]; empty?: string }) {
  if (!items.length) return <p className="text-sm italic text-slate-500">{empty}</p>
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm">
      {items.map((item, i) => <li key={i}>{item}</li>)}
    </ul>
  )
}

function Table({ head, rows }: { head: string[]; rows: (string | React.ReactNode)[][] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>{head.map(h => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row, i) => (
            <tr key={i}>{row.map((cell, j) => <td key={j} className="px-3 py-2 align-top">{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** One candidate's full details in a side panel. All values are rendered
 *  as text, so nothing from a resume can run as HTML or script. */
export function CandidateDrawer({ candidate, profile, onClose }: {
  candidate: Candidate
  profile?: Profile
  onClose: () => void
}) {
  const [tab, setTab] = useState<Tab>('Overview')
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const contact = [candidate.email, candidate.phone].filter(Boolean).join(' · ')

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30" onClick={onClose} aria-hidden />
      <section role="dialog" aria-modal="true" aria-label={`${candidate.candidate_name} details`}
               className="relative flex h-full w-full max-w-2xl flex-col bg-white shadow-xl">
        <header className="space-y-3 border-b border-slate-200 p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold">{candidate.candidate_name}</h2>
              <p className="text-sm text-slate-500">{contact || 'No contact details found'}</p>
            </div>
            <button ref={closeRef} onClick={onClose} aria-label="Close"
                    className="rounded-lg p-1 text-slate-500 hover:bg-slate-100">
              <X className="size-5" />
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-2xl font-semibold">{candidate.score}<span className="text-base text-slate-400">/100</span></span>
            <DecisionBadge decision={candidate.decision} />
            <span className="text-sm text-slate-600">{candidate.decision_reason}</span>
          </div>
          {candidate.summary && (
            <p className="rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-900">{candidate.summary}</p>
          )}
          <nav className="flex gap-1" role="tablist">
            {TABS.map(name => (
              <button key={name} role="tab" aria-selected={tab === name} onClick={() => setTab(name)}
                className={clsx('rounded-lg px-3 py-1.5 text-sm font-medium',
                  tab === name ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100')}>
                {name}{name === 'Flags' && ` (${candidate.flags.length})`}
              </button>
            ))}
          </nav>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-6" role="tabpanel">
          {tab === 'Overview' && (
            <div className="grid gap-6 sm:grid-cols-2">
              <div><h3 className="mb-2 font-semibold text-emerald-700">Strengths</h3>
                <List items={candidate.strengths} empty="None listed" /></div>
              <div><h3 className="mb-2 font-semibold text-orange-700">Gaps</h3>
                <List items={[...candidate.missing_skills, ...candidate.weaknesses]} /></div>
            </div>
          )}

          {tab === 'Scores' && (candidate.criteria.length
            ? <Table head={['Criterion', 'Points', 'Reason']}
                     rows={candidate.criteria.map(c => [c.criterion, `${c.score} / ${c.max_score}`, c.reason])} />
            : <p className="text-sm italic text-slate-500">No score breakdown returned.</p>)}

          {tab === 'Phone screen' && (
            <div>
              <h3 className="mb-2 font-semibold text-indigo-700">Ask on the phone screen</h3>
              {candidate.phone_screen_questions.length
                ? <ol className="list-decimal space-y-1 pl-5 text-sm">
                    {candidate.phone_screen_questions.map((q, i) => <li key={i}>{q}</li>)}
                  </ol>
                : <p className="text-sm italic text-slate-500">None generated</p>}
            </div>
          )}

          {tab === 'Flags' && (candidate.flags.length
            ? <Table head={['Severity', 'Issue', 'Evidence']}
                     rows={candidate.flags.map((f, i) => [<SeverityBadge key={i} severity={f.severity} />, f.description, f.evidence ?? ''])} />
            : <p className="text-sm text-emerald-700">No flags</p>)}

          {tab === 'Profile' && (profile ? (
            <div className="space-y-4 text-sm">
              <p><span className="font-medium">Location:</span> {profile.location || 'Not stated'}</p>
              <p><span className="font-medium">Education:</span>{' '}
                {profile.education.map(e => `${e.degree ?? 'Degree'} — ${e.institution ?? 'Institution'} (${e.end_year ?? 'N/A'})`).join('; ') || 'None found'}</p>
              {profile.roles.length > 0 && (
                <Table head={['Role', 'Company', 'From', 'To']}
                       rows={profile.roles.map(r => [r.title ?? '', r.company ?? '', r.start_date ?? '?', r.end_date ?? '?'])} />
              )}
              <p><span className="font-medium">Skills:</span> {profile.skills.join(', ') || 'None found'}</p>
            </div>
          ) : <p className="text-sm italic text-slate-500">Not available</p>)}
        </div>
      </section>
    </div>
  )
}
