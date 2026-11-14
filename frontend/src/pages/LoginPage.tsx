import { Target } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'

import { useAuth } from '../auth/AuthProvider'
import { Alert, Button, Card, Field, Input } from '../components/ui'

export function AuthLayout({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center justify-center gap-2 text-2xl font-semibold">
          <Target className="size-7 text-indigo-600" aria-hidden /> TalentLens AI
        </div>
        <Card className="p-6">
          <h1 className="mb-4 text-lg font-semibold">{title}</h1>
          {children}
        </Card>
      </div>
    </main>
  )
}

export function LoginPage() {
  const { me, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (me) return <Navigate to="/" replace />

  // Only ever return to a path inside this app
  const from = (location.state as { from?: string } | null)?.from
  const next = from && from.startsWith('/') && !from.startsWith('//') ? from : '/'

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
      navigate(next, { replace: true })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout title="Sign in">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email">
          <Input type="email" autoComplete="username" required value={email}
                 onChange={e => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={password}
                 onChange={e => setPassword(e.target.value)} />
        </Field>
        {error && <Alert tone="error">{error}</Alert>}
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </AuthLayout>
  )
}
