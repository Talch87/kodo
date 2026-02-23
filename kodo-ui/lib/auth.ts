import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface User {
  id: string
  email: string
  name: string
  avatar?: string
}

interface AuthStore {
  user: User | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  setUser: (user: User | null) => void
}

export const useAuth = create<AuthStore>(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,

      login: async (email: string, password: string) => {
        // Simulate API call
        return new Promise((resolve, reject) => {
          setTimeout(() => {
            if (email && password.length >= 6) {
              const user: User = {
                id: 'user-' + Math.random().toString(36).substr(2, 9),
                email,
                name: email.split('@')[0],
                avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${email}`,
              }
              set({ user, isAuthenticated: true })
              resolve()
            } else {
              reject(new Error('Invalid credentials'))
            }
          }, 1000)
        })
      },

      logout: () => {
        set({ user: null, isAuthenticated: false })
      },

      setUser: (user) => {
        set({ user, isAuthenticated: !!user })
      },
    }),
    {
      name: 'kodo-auth',
    }
  )
)
