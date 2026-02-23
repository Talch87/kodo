'use client'

import { useStore } from '@/lib/store'
import { Activity } from 'lucide-react'

export default function AgentMonitor() {
  const { agents } = useStore()

  const mockAgents = [
    { name: 'Worker Smart', type: 'worker', status: 'working', successRate: 94, cost: 2.34 },
    { name: 'Architect', type: 'architect', status: 'waiting', successRate: 98, cost: 1.56 },
    { name: 'Tester', type: 'tester', status: 'idle', successRate: 100, cost: 0.89 },
    { name: 'Designer', type: 'designer', status: 'idle', successRate: 87, cost: 0.45 },
  ]

  const statusColors = {
    working: 'bg-green-100 text-green-800',
    waiting: 'bg-yellow-100 text-yellow-800',
    idle: 'bg-gray-100 text-gray-800',
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {mockAgents.map((agent) => (
        <div key={agent.name} className="card p-4">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h3 className="font-semibold text-sm">{agent.name}</h3>
              <p className="text-xs text-gray-500 capitalize">{agent.type}</p>
            </div>
            <div className={`px-2 py-1 rounded-full text-xs font-medium badge ${statusColors[agent.status]}`}>
              {agent.status}
            </div>
          </div>

          <div className="space-y-3">
            <div>
              <p className="text-xs text-gray-600 mb-1">Success Rate</p>
              <div className="progress-bar">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${agent.successRate}%` }}
                ></div>
              </div>
              <p className="text-xs font-semibold text-gray-900 mt-1">{agent.successRate}%</p>
            </div>

            <div>
              <p className="text-xs text-gray-600">Cost</p>
              <p className="text-sm font-semibold text-green-600">${agent.cost.toFixed(2)}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
