import { create } from 'zustand'

export interface Run {
  id: string
  goal: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number // 0-100
  cycles: number
  cost: number
  startTime: string
  endTime?: string
  result?: string
  error?: string
}

export interface Agent {
  name: string
  type: 'worker' | 'architect' | 'tester' | 'designer'
  status: 'idle' | 'working' | 'waiting'
  successRate: number // 0-100
  tokensUsed: number
  cost: number
}

export interface Message {
  id: string
  from: string
  to: string
  type: 'question' | 'feedback' | 'concern' | 'suggestion'
  content: string
  timestamp: string
  response?: string
}

interface KodoStore {
  // Runs
  runs: Run[]
  currentRun: Run | null
  addRun: (run: Run) => void
  updateRun: (id: string, updates: Partial<Run>) => void
  setCurrentRun: (run: Run | null) => void

  // Agents
  agents: Agent[]
  setAgents: (agents: Agent[]) => void

  // Messages
  messages: Message[]
  addMessage: (message: Message) => void

  // UI
  sidebarOpen: boolean
  toggleSidebar: () => void
  theme: 'light' | 'dark'
  setTheme: (theme: 'light' | 'dark') => void
}

export const useStore = create<KodoStore>((set) => ({
  // Runs
  runs: [],
  currentRun: null,
  addRun: (run) => set((state) => ({ runs: [run, ...state.runs] })),
  updateRun: (id, updates) =>
    set((state) => ({
      runs: state.runs.map((r) => (r.id === id ? { ...r, ...updates } : r)),
      currentRun:
        state.currentRun?.id === id
          ? { ...state.currentRun, ...updates }
          : state.currentRun,
    })),
  setCurrentRun: (run) => set({ currentRun: run }),

  // Agents
  agents: [],
  setAgents: (agents) => set({ agents }),

  // Messages
  messages: [],
  addMessage: (message) => set((state) => ({ messages: [message, ...state.messages] })),

  // UI
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  theme: 'light',
  setTheme: (theme) => set({ theme }),
}))
