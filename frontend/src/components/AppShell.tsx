import clsx from 'clsx'
import { FolderClock, LogOut, ScanSearch, Target } from 'lucide-react'
import { NavLink, Outlet } from 'react-router'

import type { Permission } from '../api/types'
import { useAuth } from '../auth/AuthProvider'

// Shown only when the role allows it - the API checks every request too.
const NAV: { to: string; label: string; icon: typeof Target; permission: Permission }[] = [
  { to: '/screen', label: 'Screen Resumes', icon: ScanSearch, permission: 'run_scan' },
  { to: '/scans', label: 'Scan History', icon: FolderClock, permission: 'view_own_scans' },
]

export function AppShell() {
  const { me, can, logout } = useAuth()

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="flex shrink-0 flex-wrap items-center border-b border-slate-200 bg-white
                        md:w-60 md:flex-col md:flex-nowrap md:items-stretch md:border-r md:border-b-0">
        <div className="flex items-center gap-2 px-4 py-3 text-lg font-semibold md:px-5 md:py-5">
          <Target className="size-6 text-indigo-600" aria-hidden /> TalentLens AI
        </div>
        <nav className="order-last flex w-full gap-1 px-3 pb-2 md:order-none md:block md:flex-1 md:space-y-1 md:pb-0" aria-label="Main">
          {NAV.filter(item => can(item.permission)).map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to}
              className={({ isActive }) => clsx(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium',
                isActive ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100')}>
              <Icon className="size-4" aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 px-4 py-2 md:ml-0 md:block md:border-t md:border-slate-200 md:p-4">
          <div className="hidden text-sm font-medium sm:block">{me?.user.name}</div>
          <div className="hidden text-xs text-slate-500 md:block">{me?.user.role_label} · {me?.user.org_name}</div>
          <button onClick={() => logout()}
                  className="inline-flex md:mt-3 items-center gap-2 text-sm text-slate-600 hover:text-slate-900">
            <LogOut className="size-4" aria-hidden /> Sign out
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">
        <Outlet />
      </main>
    </div>
  )
}
