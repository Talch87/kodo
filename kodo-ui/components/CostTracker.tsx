'use client'

import { useStore } from '@/lib/store'
import { TrendingDown, TrendingUp } from 'lucide-react'

export default function CostTracker() {
  const { runs } = useStore()

  const totalCost = runs.reduce((sum, run) => sum + run.cost, 0)
  const avgCost = runs.length > 0 ? (totalCost / runs.length).toFixed(2) : '0.00'

  const costByAgent = {
    'Worker Smart': 12.45,
    'Architect': 8.92,
    'Tester': 6.34,
    'Designer': 3.21,
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* Summary */}
      <div className="card p-6">
        <p className="text-sm text-gray-600 mb-2">Total Cost</p>
        <div className="text-3xl font-bold text-green-600">${totalCost.toFixed(2)}</div>
        <p className="text-xs text-gray-500 mt-1">{runs.length} runs</p>
      </div>

      <div className="card p-6">
        <p className="text-sm text-gray-600 mb-2">Average per Run</p>
        <div className="text-3xl font-bold text-blue-600">${avgCost}</div>
        <p className="text-xs text-gray-500 mt-1">API usage</p>
      </div>

      <div className="card p-6">
        <p className="text-sm text-gray-600 mb-2">Budget</p>
        <div className="text-3xl font-bold text-purple-600">$100.00</div>
        <p className="text-xs text-gray-500 mt-1">{((totalCost / 100) * 100).toFixed(1)}% used</p>
      </div>

      {/* Cost by Agent */}
      <div className="lg:col-span-3 card p-6">
        <h3 className="font-semibold mb-4">Cost by Agent</h3>
        <div className="space-y-4">
          {Object.entries(costByAgent).map(([agent, cost]) => (
            <div key={agent}>
              <div className="flex justify-between mb-2">
                <p className="text-sm font-medium">{agent}</p>
                <p className="text-sm font-semibold">${cost.toFixed(2)}</p>
              </div>
              <div className="progress-bar">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${(cost / 35) * 100}%` }}
                ></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
