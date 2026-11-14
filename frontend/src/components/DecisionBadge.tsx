import clsx from 'clsx'

import type { Decision } from '../api/types'

const STYLE: Record<Decision, string> = {
  Advance: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  Hold: 'bg-amber-50 text-amber-800 ring-amber-600/20',
  Reject: 'bg-red-50 text-red-700 ring-red-600/20',
}

const DOT: Record<Decision, string> = {
  Advance: 'bg-emerald-500', Hold: 'bg-amber-500', Reject: 'bg-red-500',
}

export function DecisionBadge({ decision }: { decision?: Decision | null }) {
  if (!decision) return <span className="text-slate-400">—</span>
  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5',
                          'text-xs font-semibold ring-1 ring-inset', STYLE[decision])}>
      <span className={clsx('size-1.5 rounded-full', DOT[decision])} aria-hidden />
      {decision}
    </span>
  )
}

const SEVERITY: Record<string, string> = {
  high: 'bg-red-50 text-red-700', medium: 'bg-orange-50 text-orange-700', low: 'bg-yellow-50 text-yellow-800',
}

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={clsx('rounded px-2 py-0.5 text-xs font-medium capitalize',
                          SEVERITY[severity] ?? 'bg-slate-100 text-slate-700')}>
      {severity}
    </span>
  )
}
