'use client'

import { useAuth } from '@/lib/auth'
import { useState, useEffect } from 'react'
import { useStore } from '@/lib/store'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import GoalInput from '@/components/GoalInput'
import RunsList from '@/components/RunsList'
import Dashboard from '@/components/Dashboard'
import AgentMonitor from '@/components/AgentMonitor'
import CostTracker from '@/components/CostTracker'
import ExecutionTimeline from '@/components/ExecutionTimeline'

export default function DashboardPage() {
  const { user, isAuthenticated } = useAuth()
  const { currentRun, sidebarOpen } = useStore()
  const [activeView, setActiveView] = useState<'dashboard' | 'runs' | 'agents' | 'cost'>('dashboard')
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    setIsReady(true)
  }, [])

  if (!isReady || !isAuthenticated) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-blue-100 rounded-full mb-4">
            <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      {sidebarOpen && <Sidebar activeView={activeView} onViewChange={setActiveView} />}

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <Header />

        <div className="flex-1 overflow-auto">
          <div className="max-w-7xl mx-auto p-6 space-y-6">
            {/* Goal Input */}
            <GoalInput />

            {/* Main Content Views */}
            {activeView === 'dashboard' && (
              <div className="space-y-6 animate-fade-in">
                {currentRun ? (
                  <>
                    <Dashboard run={currentRun} />
                    <ExecutionTimeline run={currentRun} />
                    <AgentMonitor />
                  </>
                ) : (
                  <div className="card p-12 text-center">
                    <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mb-4">
                      <span className="text-2xl">✨</span>
                    </div>
                    <p className="text-gray-600 text-lg">Submit a goal above to get started</p>
                    <p className="text-gray-500 text-sm mt-2">Your agent will run autonomously and handle the work</p>
                  </div>
                )}
              </div>
            )}

            {activeView === 'runs' && <RunsList />}
            {activeView === 'agents' && <AgentMonitor />}
            {activeView === 'cost' && <CostTracker />}
          </div>
        </div>
      </main>
    </div>
  )
}
