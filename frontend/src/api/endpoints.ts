import { ApiError, api, query, request } from './client'
import { readSse } from './sse'
import type {
  Me, Org, Page, ScanProgress, ScanSummary, ScreeningResult, UserRow,
} from './types'

// ---------- auth ----------

export const fetchMe = () => api<Me>('/auth/me')

export const login = (email: string, password: string) =>
  api<Me>('/auth/login', 'POST', { email, password })

export const logout = () => api<{ ok: boolean }>('/auth/logout', 'POST')

export const changePassword = (current_password: string, new_password: string) =>
  api<Me>('/auth/change-password', 'POST', { current_password, new_password })

// ---------- scans ----------

export interface ScanFilters {
  org_id?: number | null
  user_id?: number | null
  date_from?: string
  date_to?: string
  jd?: string
}

export const listScans = (filters: ScanFilters, page: number) =>
  api<Page<ScanSummary>>(`/scans${query({ ...filters, page })}`)

export const getScan = (id: number) => api<ScreeningResult>(`/scans/${id}`)

export interface ScanRequest {
  resumes: File[]
  jdText: string
  jdFile: File | null
  topN: string
  minScore: number
  scanId: number | null
}

/** Uploads and screens; calls onProgress as batches finish. */
export async function runScan(
  scan: ScanRequest,
  onProgress: (progress: ScanProgress) => void,
): Promise<{ scan_id: number; result: ScreeningResult }> {
  const form = new FormData()
  scan.resumes.forEach(file => form.append('resumes', file))
  if (scan.jdFile) form.append('jd_file', scan.jdFile)
  else form.append('jd_text', scan.jdText)
  form.append('top_n', scan.topN)
  form.append('min_score', String(scan.minScore))
  if (scan.scanId) form.append('scan_id', String(scan.scanId))

  const response = await request('/scans', 'POST', form)

  for await (const { event, data } of readSse(response)) {
    if (event === 'progress') onProgress(data as ScanProgress)
    else if (event === 'result') return data as { scan_id: number; result: ScreeningResult }
    else if (event === 'error') throw new ApiError(400, (data as { detail: string }).detail)
  }
  throw new ApiError(500, 'The screening stopped before finishing - try again.')
}

// ---------- orgs and users (for history filters) ----------

export const listOrgs = () => api<Org[]>('/orgs')

/** Every user the caller may see, reading all pages. */
export async function listAllUsers(): Promise<UserRow[]> {
  const users: UserRow[] = []
  for (let page = 1; ; page++) {
    const result = await api<Page<UserRow>>(`/users${query({ page })}`)
    users.push(...result.items)
    if (users.length >= result.total || result.items.length === 0) return users
  }
}
