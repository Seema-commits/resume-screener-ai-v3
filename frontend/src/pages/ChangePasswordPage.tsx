import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { useAuth } from '../auth/AuthProvider'
import { Alert, Button, Field, Input } from '../components/ui'
import { AuthLayout } from './LoginPage'

const MIN_LENGTH = 10      // matches auth_service.MIN_PASSWORD_LENGTH

export function ChangePasswordPage() {
  const { changePassword, logout } = useAuth()
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (next !== confirm) return setError("The new passwords don't match.")
    if (next.length < MIN_LENGTH) return setError(`Use at least ${MIN_LENGTH} characters.`)
    setBusy(true)
    setError(null)
    try {
      await changePassword(current, next)
      navigate('/', { replace: true })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not change the password.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout title="Set a new password">
      <p className="mb-4 text-sm text-slate-600">
        You're using a temporary password. Choose your own to continue.
      </p>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Temporary password">
          <Input type="password" autoComplete="current-password" required value={current}
                 onChange={e => setCurrent(e.target.value)} />
        </Field>
        <Field label="New password" hint={`At least ${MIN_LENGTH} characters.`}>
          <Input type="password" autoComplete="new-password" required value={next}
                 onChange={e => setNext(e.target.value)} />
        </Field>
        <Field label="Confirm new password">
          <Input type="password" autoComplete="new-password" required value={confirm}
                 onChange={e => setConfirm(e.target.value)} />
        </Field>
        {error && <Alert tone="error">{error}</Alert>}
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? 'Saving…' : 'Save password'}
        </Button>
        <Button type="button" variant="ghost" className="w-full" onClick={() => logout()}>
          Sign out
        </Button>
      </form>
    </AuthLayout>
  )
}
