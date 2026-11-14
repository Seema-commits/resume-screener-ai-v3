import { fireEvent, render, screen } from '@testing-library/react'

import type { Candidate } from '../api/types'
import { CandidateDrawer } from '../components/CandidateDrawer'
import { DecisionBadge } from '../components/DecisionBadge'

const attack = '<img src=x onerror="window.hacked=1"><script>window.hacked=1</script>'

const candidate: Candidate = {
  candidate_name: attack, score: 70, criteria: [], matched_skills: [], missing_skills: [],
  strengths: [attack], weaknesses: [], recommendation: '', summary: attack,
  missing_must_haves: [], phone_screen_questions: ['Ask about X'], decision: 'Hold',
  decision_reason: 'Score 55-74', email: 'a@b.c', phone: '123',
  flags: [{ flag_type: 'prompt_injection_suspected', severity: 'high', description: 'Instruction-like text' }],
}

test('DecisionBadge shows the label', () => {
  render(<DecisionBadge decision="Advance" />)
  expect(screen.getByText('Advance')).toBeInTheDocument()
})

test('CandidateDrawer renders resume text as text, never HTML', () => {
  const { container } = render(<CandidateDrawer candidate={candidate} onClose={() => {}} />)
  expect(container.querySelector('img, script')).toBeNull()
  expect(screen.getAllByText(attack).length).toBeGreaterThan(0)
  expect((window as unknown as { hacked?: number }).hacked).toBeUndefined()
})

test('CandidateDrawer tabs and Escape', () => {
  const onClose = vi.fn()
  render(<CandidateDrawer candidate={candidate} onClose={onClose} />)
  fireEvent.click(screen.getByRole('tab', { name: 'Phone screen' }))
  expect(screen.getByText('Ask about X')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: 'Flags (1)' }))
  expect(screen.getByText('Instruction-like text')).toBeInTheDocument()
  fireEvent.keyDown(window, { key: 'Escape' })
  expect(onClose).toHaveBeenCalled()
})
