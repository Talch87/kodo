'use client'

import { useStore } from '@/lib/store'

export default function RunsList() {
  const { runs, setCurrentRun } = useStore()

  if (runs.length === 0) {
    return (
      <div className="card p-12 text-center">
        <p className="text-gray-500">No runs yet. Submit a goal to get started.</p>
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      <table className="w-full">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-600">Goal</th>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-600">Status</th>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-600">Progress</th>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-600">Cost</th>
            <th className="px-6 py-3 text-left text-sm font-semibold text-gray-600">Started</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {runs.map((run) => (
            <tr
              key={run.id}
              onClick={() => setCurrentRun(run)}
              className="hover:bg-gray-50 cursor-pointer transition-colors"
            >
              <td className="px-6 py-4 text-sm text-gray-900 max-w-xs truncate">
                {run.goal}
              </td>
              <td className="px-6 py-4">
                <span className={`badge badge-${run.status === 'completed' ? 'success' : run.status === 'failed' ? 'error' : 'info'}`}>
                  {run.status}
                </span>
              </td>
              <td className="px-6 py-4 text-sm">{Math.round(run.progress)}%</td>
              <td className="px-6 py-4 text-sm font-medium">${run.cost.toFixed(2)}</td>
              <td className="px-6 py-4 text-sm text-gray-500">
                {new Date(run.startTime).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
