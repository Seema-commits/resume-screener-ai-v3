// Shapes returned by the FastAPI backend (backend/routers).

export type Permission =
  | 'run_scan' | 'view_own_scans' | 'view_team_scans' | 'view_all_scans'
  | 'manage_users' | 'manage_orgs' | 'view_logs' | 'choose_llm_models'
  | 'manage_org_keys'

export interface CurrentUser {
  id: number
  org_id: number
  org_name: string
  name: string
  email: string
  role: string
  role_label: string
  must_change_password: boolean
}

export interface Me {
  user: CurrentUser
  permissions: Permission[]
  csrf_token: string
}

export interface Criterion {
  criterion: string
  max_score: number
  score: number
  reason: string
}

export interface Flag {
  flag_type: string
  severity: string
  description: string
  evidence?: string | null
}

export type Decision = 'Advance' | 'Hold' | 'Reject'

export interface Candidate {
  candidate_name: string
  score: number
  criteria: Criterion[]
  matched_skills: string[]
  missing_skills: string[]
  strengths: string[]
  weaknesses: string[]
  flags: Flag[]
  recommendation: string
  summary: string
  missing_must_haves: string[]
  phone_screen_questions: string[]
  decision?: Decision | null
  decision_reason?: string | null
  email?: string | null
  phone?: string | null
}

export interface Profile {
  candidate_name: string
  location?: string | null
  education: { degree?: string | null; institution?: string | null; end_year?: string | null }[]
  roles: { title?: string | null; company?: string | null; start_date?: string | null; end_date?: string | null }[]
  skills: string[]
}

export interface ScreeningResult {
  shortlisted_candidates: Candidate[]
  rejected_candidates: Candidate[]
  parsed_profiles: Profile[]
  criteria_weights?: Record<string, number> | null
  matched_weight_signals?: { category: string; phrase: string; reason: string }[]
  run_stats?: { resumes: number; screened_now: number; reused: number; suspicious?: number }
  jd_text?: string
}

export interface ScanSummary {
  id: number
  created_at: string
  run_by: string
  org: string
  jd_text: string
  resume_count: number
  shortlisted_count: number
}

export interface Page<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

export interface Org {
  id: number
  name: string
  is_active: boolean
}

export interface UserRow {
  id: number
  name: string
  email: string
  org_id: number
}

export interface ScanProgress {
  stage: 'parse' | 'score'
  done: number
  total: number
}
