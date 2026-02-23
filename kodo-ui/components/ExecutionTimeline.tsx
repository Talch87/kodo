'use client'

import { Run } from '@/lib/store'
import { CheckCircle, Circle, AlertCircle } from 'lucide-react'

interface ExecutionTimelineProps {
  run: Run
}

export default function ExecutionTimeline({ run }: ExecutionTimelineProps) {
  const steps = [
    { name: 'Initialize', status: 'completed' },
    { name: 'Analyze Goal', status: 'completed' },
    { name: 'Plan Execution', status: 'completed' },
    { name: 'Generate Code', status: run.progress > 50 ? 'completed' : run.progress > 0 ? 'in_progress' : 'pending' },
    { name: 'Run Tests', status: run.progress > 75 ? 'completed' : run.progress > 50 ? 'in_progress' : 'pending' },
    { name: 'Verify Quality', status: run.progress > 90 ? 'completed' : run.progress > 75 ? 'in_progress' : 'pending' },
  ]

  const getIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle size={20} className="text-green-600" />
      case 'in_progress':
        return <Circle size={20} className="text-blue-600 animate-pulse" />
      default:
        return <Circle size={20} className="text-gray-300" />
    }
  }

  return (
    <div className="card p-6">
      <h3 className="font-semibold mb-6">Execution Timeline</h3>
      <div className="space-y-4">
        {steps.map((step, index) => (
          <div key={step.name} className="flex items-center gap-4">
            <div className="flex flex-col items-center">
              {getIcon(step.status)}
              {index < steps.length - 1 && (
                <div
                  className={`w-1 h-8 mt-2 ${
                    step.status === 'completed' ? 'bg-green-600' : 'bg-gray-300'
                  }`}
                ></div>
              )}
            </div>
            <div className="flex-1">
              <p
                className={`font-medium ${
                  step.status === 'completed'
                    ? 'text-gray-900'
                    : step.status === 'in_progress'
                    ? 'text-blue-600'
                    : 'text-gray-500'
                }`}
              >
                {step.name}
              </p>
            </div>
            <p className="text-sm text-gray-500 capitalize">{step.status.replace('_', ' ')}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
