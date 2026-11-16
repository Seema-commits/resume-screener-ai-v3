import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'

import { forgotPassword, resetPassword } from '../api/endpoints'
import { Alert, Button, Field, Input } from '../components/ui'
import { AuthLayout } from './LoginPage'

const MIN_LENGTH = 10
const SENT = "If that email belongs to an active account, we've sent a link to reset the " +
  'password. It works once, for 30 minutes - check your spam folder too.'

function BackToSignIn() {
  return (
    <Link to="/login" className="block text-center text-sm text-indigo-700 hover:underline">
      Back to sign in
    </Link>
  )
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true); setError(null)
    try {
      await forgotPassword(email)
      setSent(true)                  // the same message for any email
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong - try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout title="Forgot password">
      <form onSubmit={submit} className="space-y-4">
        {sent ? <Alert tone="success">{SENT}</Alert> : (
          <Field label="Your account email">
            <Input type="email" autoComplete="username" required maxLength={320} value={email}
                   onChange={e => setEmail(e.target.value)} />
          </Field>
        )}
        {error && <Alert tone="error">{error}</Alert>}
        {!sent && (
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? 'Sending…' : 'Email me a reset link'}
          </Button>
        )}
        <BackToSignIn />
      </form>
    </AuthLayout>
  )
}

/** Opened from the emailed link: /reset-password#token=... */
export function ResetPasswordPage() {
  const navigate = useNavigate()
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Take the token out of the address bar so it isn't left in history
  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
    }
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (password.length < MIN_LENGTH) return setError(`Use at least ${MIN_LENGTH} characters.`)
    if (password !== confirm) return setError("The new passwords don't match.")
    setBusy(true)
    try {
      await resetPassword(token, password)
      navigate('/login', { replace: true, state: { passwordReset: true } })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong - try again.')
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return (
      <AuthLayout title="Reset password">
        <div className="space-y-4">
          <Alert tone="error">This reset link is incomplete. Request a new one.</Alert>
          <Link to="/forgot-password" className="block text-center text-sm text-indigo-700 hover:underline">
            Request a new link
          </Link>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Choose a new password">
      <form onSubmit={submit} className="space-y-4">
        <Field label={`New password (at least ${MIN_LENGTH} characters)`}>
          <Input type="password" autoComplete="new-password" required maxLength={200} value={password}
                 onChange={e => setPassword(e.target.value)} />
        </Field>
        <Field label="Confirm new password">
          <Input type="password" autoComplete="new-password" required maxLength={200} value={confirm}
                 onChange={e => setConfirm(e.target.value)} />
        </Field>
        {error && <Alert tone="error">{error}</Alert>}
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? 'Saving…' : 'Save password'}
        </Button>
        <BackToSignIn />
      </form>
    </AuthLayout>
  )
}
