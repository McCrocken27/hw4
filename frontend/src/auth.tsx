import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import * as api from './api'

type AuthState = {
  user: api.User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (form: api.SignupForm) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

// The session lives in an HttpOnly cookie the page cannot read, so we ask the
// server who is logged in instead of storing anything in the browser.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<api.User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .getMe()
      .then((r) => setUser(r.user))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const value: AuthState = {
    user,
    loading,
    login: async (email, password) => setUser(await api.login(email, password)),
    signup: async (form) => setUser(await api.signup(form)),
    logout: async () => {
      await api.logout().catch(() => {})
      setUser(null)
    },
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
