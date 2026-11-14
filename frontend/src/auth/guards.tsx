import { Navigate, useLocation } from 'react-router'
import type { ReactNode } from 'react'

import type { Permission } from '../api/types'
import { Alert, Spinner } from '../components/ui'
import { useAuth } from './AuthProvider'

/** Signed-in users only; a temporary password must be changed first. */
export function RequireAuth({ children, passwordChangePage = false }: {
  children: ReactNode
  passwordChangePage?: boolean
}) {
  const { me, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return <div className="p-8"><Spinner /></div>
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (me.user.must_change_password && !passwordChangePage) {
    return <Navigate to="/change-password" replace />
  }
  if (!me.user.must_change_password && passwordChangePage) return <Navigate to="/" replace />
  return <>{children}</>
}

/** Hides a page the role can't use - the API refuses it anyway. */
export function RequirePermission({ permission, children }: {
  permission: Permission
  children: ReactNode
}) {
  const { can } = useAuth()
  if (!can(permission)) {
    return <div className="p-8"><Alert tone="error">You don't have access to this page.</Alert></div>
  }
  return <>{children}</>
}
