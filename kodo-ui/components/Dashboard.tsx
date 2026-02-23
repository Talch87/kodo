'use client'

import { Run } from '@/lib/store'
import { CheckCircle, AlertCircle, Clock, TrendingUp } from 'lucide-react'

interface DashboardProps {
  run: Run
}

export default function Dashboard({ run }: DashboardProps) {
  const statusConfig = {
    pending: { color: 'bg-gray-100', textColor: 'text-gray-800', icon: Clock },
    running: { color: 'bg-blue-100', textColor: 'text-blue-800', icon: TrendingUp },
    completed: { color: 'bg-green-100', textColor: 'text-green-800', icon: CheckCircle },
    failed: { color: 'bg-red-100', textColor: 'text-red-800', icon: AlertCircle },
  }

  const config = statusConfig[run.status]
  const Icon = config.icon

  return (
    <div className="grid grid-cols-4 gap-4">
      {/* Status Card */}
      <div className="card p-6">
        <p className="text-sm text-gray-600 mb-2">Status</p>
        <div className={`flex items-center gap-2 text-xl font-semibold ${config.textColor}`}>
          <Icon size={24} />
          <span className="capitalize">{run.status}</span>
        </div>
      </div>

      {/* Progress Card */}
      <div className="card p-6">
        <p className="text-sm text-gray-600 mb-2">Progress</p>
        <div className="space-y-3">
          <div className="text-2xl font-bold">{Math.round(run.progress)}%</div>
          <div className="progress-bar">
            <div
              className="progress-bar-fill"
              style={{ width: `${run.progress}%` }}
            ></div>
          </div>
        </div>
      </div>

      {/* Cycles Card */}
      <div className="card p-6">
        <p className="text-sm text-gray-600 mb-2">Cycles</p>
        <div className="text-2xl font-bold text-purple-600">{run.cycles}</div>
        <p className="text-xs text-gray-500 mt-1">iterations</p>
      </div>

      {/* Cost Card */}
      <div className="card p-6">
        <p className="text-sm text-gray-600 mb-2">Cost</p>
        <div className="text-2xl font-bold text-green-600">${run.cost.toFixed(2)}</div>
        <p className="text-xs text-gray-500 mt-1">API usage</p>
      </div>
    </div>
  )
}
