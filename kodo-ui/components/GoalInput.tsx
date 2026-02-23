'use client'

import { useState } from 'react'
import { useStore } from '@/lib/store'
import { Send, Zap } from 'lucide-react'

export default function GoalInput() {
  const [goal, setGoal] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const { addRun, setCurrentRun } = useStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!goal.trim()) return

    setIsLoading(true)

    const newRun = {
      id: `run-${Date.now()}`,
      goal,
      status: 'running' as const,
      progress: 0,
      cycles: 0,
      cost: 0,
      startTime: new Date().toISOString(),
    }

    addRun(newRun)
    setCurrentRun(newRun)
    setGoal('')

    // Simulate progress updates
    const interval = setInterval(() => {
      setCurrentRun({
        ...newRun,
        progress: Math.min(100, newRun.progress + Math.random() * 20),
        cycles: Math.floor(Math.random() * 5),
        cost: Number((Math.random() * 10).toFixed(2)),
      })
    }, 2000)

    setTimeout(() => {
      clearInterval(interval)
      setCurrentRun({
        ...newRun,
        status: 'completed' as const,
        progress: 100,
        endTime: new Date().toISOString(),
        result: 'Code generation completed successfully',
      })
      setIsLoading(false)
    }, 15000)
  }

  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold mb-4">Create a New Goal</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Describe what you want Kodo to build... e.g., 'Create a REST API for managing todo items with authentication and tests'"
          className="input resize-none h-24"
          disabled={isLoading}
        />
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={!goal.trim() || isLoading}
            className="btn btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Zap size={18} />
            {isLoading ? 'Running...' : 'Run Kodo'}
          </button>
          <p className="text-sm text-gray-500 self-center">
            {goal.length} characters
          </p>
        </div>
      </form>
    </div>
  )
}
