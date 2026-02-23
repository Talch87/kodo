'use client'

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

export default function Home() {
  const { currentRun, sidebarOpen } = useStore()
  const [activeView, setActiveView] = useState<'dashboard' | 'runs' | 'agents' | 'cost'>('dashboard')

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
              <div className="space-y-6">
                {currentRun ? (
                  <>
                    <Dashboard run={currentRun} />
                    <ExecutionTimeline run={currentRun} />
                    <AgentMonitor />
                  </>
                ) : (
                  <div className="text-center py-12">
                    <p className="text-gray-500 text-lg">Submit a goal to get started</p>
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
