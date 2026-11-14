import type { Candidate } from '../api/types'

/**
 * A CSV cell that spreadsheet apps can't run as a formula: text starting
 * with = + - @ (or a tab/carriage return) is prefixed with ' (OWASP
 * "CSV injection"), then quoted.
 */
export function safeCell(value: unknown): string {
  let text = value === null || value === undefined ? '' : String(value)
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return `"${text.replace(/"/g, '""')}"`
}

const COLUMNS: [string, (c: Candidate & { status: string }) => unknown][] = [
  ['Candidate', c => c.candidate_name],
  ['Email', c => c.email],
  ['Phone', c => c.phone],
  ['Status', c => c.status],
  ['Score', c => c.score],
  ['Decision', c => c.decision],
  ['Decision Reason', c => c.decision_reason],
  ['Summary', c => c.summary],
  ['Flags', c => c.flags.map(f => f.description).join('; ')],
  ['Matched Skills', c => c.matched_skills.join(', ')],
  ['Missing Skills', c => c.missing_skills.join(', ')],
  ['Phone-Screen Questions', c => c.phone_screen_questions.join(' | ')],
]

export function candidatesCsv(shortlisted: Candidate[], notShortlisted: Candidate[]): string {
  const rows = [
    ...shortlisted.map(c => ({ ...c, status: 'Shortlisted' })),
    ...notShortlisted.map(c => ({ ...c, status: 'Not Shortlisted' })),
  ]
  return [
    COLUMNS.map(([name]) => safeCell(name)).join(','),
    ...rows.map(row => COLUMNS.map(([, get]) => safeCell(get(row))).join(',')),
  ].join('\r\n')
}

export function downloadText(filename: string, text: string, type = 'text/csv') {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
