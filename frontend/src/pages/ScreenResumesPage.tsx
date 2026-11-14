import { useQueryClient } from '@tanstack/react-query'
import { RotateCcw, Sparkles } from 'lucide-react'
import { useState } from 'react'

import { runScan } from '../api/endpoints'
import type { ScanProgress, ScreeningResult } from '../api/types'
import { FileDrop } from '../components/FileDrop'
import { ResultsView } from '../components/ResultsView'
import { Alert, Button, Card, Field, Select } from '../components/ui'
import { addFiles } from '../lib/files'

const TOP_N = ['3', '5', '10', 'All qualified']

export function ScreenResumesPage() {
  const queryClient = useQueryClient()
  const [jdText, setJdText] = useState('')
  const [jdFile, setJdFile] = useState<File | null>(null)
  const [resumes, setResumes] = useState<File[]>([])
  const [topN, setTopN] = useState('5')
  const [minScore, setMinScore] = useState(6)
  const [errors, setErrors] = useState<string[]>([])
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState<ScanProgress | null>(null)
  const [scanId, setScanId] = useState<number | null>(null)
  const [result, setResult] = useState<ScreeningResult | null>(null)

  const hasJd = !!jdFile || jdText.trim().length > 0
  const canRun = hasJd && resumes.length > 0 && !running

  async function run() {
    setErrors([]); setRunning(true); setProgress(null)
    try {
      const done = await runScan({ resumes, jdText, jdFile, topN, minScore, scanId }, setProgress)
      setScanId(done.scan_id)
      setResult(done.result)
      queryClient.invalidateQueries({ queryKey: ['scans'] })
    } catch (e) {
      setErrors([e instanceof Error ? e.message : 'Screening failed - try again.'])
    } finally {
      setRunning(false); setProgress(null)
    }
  }

  function reset() {
    setJdText(''); setJdFile(null); setResumes([]); setErrors([])
    setScanId(null); setResult(null)
  }

  const percent = progress?.total ? Math.round((progress.done / progress.total) * 100) : 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Screen resumes</h1>
          <p className="text-sm text-slate-500">
            Names, emails and phone numbers are masked before anything is sent to the AI.
          </p>
        </div>
        {(result || resumes.length > 0 || hasJd) && (
          <Button variant="secondary" onClick={reset} disabled={running}>
            <RotateCcw className="size-4" aria-hidden /> New session
          </Button>
        )}
      </div>

      <Card className="grid gap-6 p-6 lg:grid-cols-2">
        <div className="space-y-4">
          <h2 className="font-semibold">1. Job description</h2>
          <Field label="Paste the job description">
            <textarea value={jdText} onChange={e => setJdText(e.target.value)} disabled={!!jdFile}
              rows={8} maxLength={20000}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50" />
          </Field>
          <FileDrop accept=".pdf" multiple={false} label="…or upload it as a PDF"
            files={jdFile ? [jdFile] : []}
            onAdd={files => {
              const pdf = files.find(f => f.name.toLowerCase().endsWith('.pdf'))
              setJdFile(pdf ?? null)
              if (!pdf && files.length) setErrors(['The job description must be a PDF.'])
            }}
            onRemove={() => setJdFile(null)} />
        </div>

        <div className="space-y-4">
          <h2 className="font-semibold">2. Resumes</h2>
          <FileDrop accept=".pdf,.docx" label="Upload resumes (PDF or DOCX, up to 20, 5 MB each)"
            files={resumes}
            onAdd={incoming => {
              const added = addFiles(resumes, incoming)
              setResumes(added.files); setErrors(added.errors)
            }}
            onRemove={file => setResumes(resumes.filter(f => f !== file))} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Shortlist size">
              <Select value={topN} onChange={e => setTopN(e.target.value)}>
                {TOP_N.map(n => <option key={n}>{n}</option>)}
              </Select>
            </Field>
            <Field label={`Minimum score: ${minScore}/10`} hint="Candidates below this aren't shortlisted.">
              <input type="range" min={1} max={10} value={minScore}
                     onChange={e => setMinScore(Number(e.target.value))} className="w-full accent-indigo-600" />
            </Field>
          </div>
        </div>
      </Card>

      {errors.length > 0 && (
        <Alert tone="error">{errors.map((e, i) => <div key={i}>{e}</div>)}</Alert>
      )}

      <div className="space-y-3">
        <Button onClick={run} disabled={!canRun}>
          <Sparkles className="size-4" aria-hidden />
          {running ? 'Screening…' : scanId ? 'Re-screen (only new resumes go to the AI)' : 'Screen resumes'}
        </Button>
        {running && (
          <div className="space-y-1" aria-live="polite">
            <div className="h-2 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full bg-indigo-600 transition-all" style={{ width: `${percent}%` }} />
            </div>
            <p className="text-sm text-slate-500">
              {progress
                ? `${progress.stage === 'parse' ? 'Reading' : 'Scoring'} resumes: ${progress.done}/${progress.total}`
                : 'Uploading…'}
            </p>
          </div>
        )}
      </div>

      {result && <ResultsView result={result} />}
    </div>
  )
}
