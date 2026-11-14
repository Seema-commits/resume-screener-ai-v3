/**
 * The one place the frontend talks to the API. Every request sends the
 * httpOnly session cookie; every change also sends the CSRF token from
 * /api/auth/me. The token is kept in memory only - nothing is stored in
 * browser storage. A 401 tells the auth layer the session has ended.
 */

// Empty in development (Vite forwards /api); the API's address in production.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

let csrfToken: string | null = null
let onUnauthorized: () => void = () => {}

export function setCsrfToken(token: string | null) {
  csrfToken = token
}

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Body = FormData | object | undefined

export async function request(path: string, method = 'GET', body?: Body): Promise<Response> {
  const headers: Record<string, string> = {}
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken
  const isForm = body instanceof FormData
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'

  const response = await fetch(`${API_BASE}/api${path}`, {
    method,
    headers,
    credentials: 'include',
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  })

  if (!response.ok) {
    // /auth/me and /auth/login answer 401 as a normal 'not signed in'
    if (response.status === 401 && !/^\/auth\/(me|login)/.test(path)) onUnauthorized()
    throw new ApiError(response.status, await errorMessage(response))
  }
  return response
}

export async function api<T>(path: string, method = 'GET', body?: Body): Promise<T> {
  const response = await request(path, method, body)
  return (await response.json()) as T
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json()
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) return 'Some fields are missing or invalid.'
  } catch {
    // not JSON
  }
  return response.status >= 500 ? 'The server had a problem - try again.' : 'Request failed.'
}

/** Query string from the non-empty values. */
export function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '' && value !== false) {
      search.set(key, String(value))
    }
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}
