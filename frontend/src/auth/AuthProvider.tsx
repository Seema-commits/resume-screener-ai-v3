/**
 * Who is signed in, and what their role allows. The session lives in an
 * httpOnly cookie (JavaScript can't read it), so on every page load the
 * app asks /api/auth/me - which is why a reload keeps you signed in.
 * Permissions only decide what the UI shows; the API checks every request.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo } from 'react'
import type { ReactNode } from 'react'

import { ApiError, setCsrfToken, setUnauthorizedHandler } from '../api/client'
import * as endpoints from '../api/endpoints'
import type { Me, Permission } from '../api/types'

interface AuthState {
  me: Me | null
  isLoading: boolean
  can: (permission: Permission) => boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  changePassword: (current: string, next: string) => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)
const ME = ['me']

async function loadMe(): Promise<Me | null> {
  try {
    return await endpoints.fetchMe()
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ME, queryFn: loadMe, retry: false })
  const me = data ?? null

  // Keep the CSRF token in memory, in step with the session
  useEffect(() => setCsrfToken(me?.csrf_token ?? null), [me])

  const signedOut = useCallback(() => {
    setCsrfToken(null)
    // Drop every cached result, then mark signed out (removing 'me'
    // itself would just refetch it)
    queryClient.removeQueries({ predicate: q => q.queryKey[0] !== ME[0] })
    queryClient.setQueryData(ME, null)
  }, [queryClient])

  useEffect(() => setUnauthorizedHandler(signedOut), [signedOut])

  const value = useMemo<AuthState>(() => ({
    me,
    isLoading,
    can: permission => !!me?.permissions.includes(permission),
    login: async (email, password) => {
      const result = await endpoints.login(email, password)
      setCsrfToken(result.csrf_token)
      queryClient.setQueryData(ME, result)
    },
    logout: async () => {
      try {
        await endpoints.logout()
      } finally {
        signedOut()
      }
    },
    changePassword: async (current, next) => {
      queryClient.setQueryData(ME, await endpoints.changePassword(current, next))
    },
  }), [me, isLoading, queryClient, signedOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside AuthProvider')
  return auth
}
