import { parseSse } from '../api/sse'
import { candidatesCsv, safeCell } from '../lib/csv'
import { addFiles, MAX_RESUMES } from '../lib/files'
import type { Candidate } from '../api/types'

describe('safeCell (CSV injection)', () => {
  it.each(['=HYPERLINK("http://x")', '+1+2', '-2+3', '@SUM(A1)', '\tcmd', '\rcmd'])(
    'neutralises %j', value => expect(safeCell(value)).toMatch(/^"'/))
  it('quotes and escapes plain text', () => expect(safeCell('a "b", c')).toBe('"a ""b"", c"'))
  it('handles empty values', () => expect(safeCell(null)).toBe('""'))
  it('guards every candidate field', () => {
    const c = { candidate_name: '=cmd|calc', email: '@x', phone: '+1', score: 50, criteria: [],
      matched_skills: [], missing_skills: [], strengths: [], weaknesses: [], flags: [],
      recommendation: '', summary: '-1', missing_must_haves: [], phone_screen_questions: [] } as Candidate
    const row = candidatesCsv([c], []).split('\n')[1]
    expect(row).toContain(`"'=cmd|calc"`)
    expect(row).toContain(`"'@x"`)
  })
})

describe('parseSse', () => {
  it('splits complete events and keeps the rest', () => {
    const { events, rest } = parseSse('event: progress\ndata: {"done":1}\n\nevent: res')
    expect(events).toEqual([{ event: 'progress', data: { done: 1 } }])
    expect(rest).toBe('event: res')
  })
})

describe('addFiles', () => {
  const file = (name: string, size = 10) => new File(['x'.repeat(size)], name)
  it('accepts PDF/DOCX and skips duplicates', () => {
    const { files, errors } = addFiles([file('a.pdf')], [file('a.pdf'), file('b.DOCX')])
    expect(files.map(f => f.name)).toEqual(['a.pdf', 'b.DOCX'])
    expect(errors).toEqual([])
  })
  it('rejects other types', () => {
    expect(addFiles([], [file('evil.html')]).errors[0]).toMatch(/only PDF and DOCX/)
  })
  it('caps the count', () => {
    const many = Array.from({ length: MAX_RESUMES + 2 }, (_, i) => file(`${i}.pdf`))
    const { files, errors } = addFiles([], many)
    expect(files).toHaveLength(MAX_RESUMES)
    expect(errors.length).toBe(1)
  })
})
