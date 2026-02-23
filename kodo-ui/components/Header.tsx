'use client'

import { useStore } from '@/lib/store'
import { Menu, Settings, Bell } from 'lucide-react'

export default function Header() {
  const { toggleSidebar, currentRun } = useStore()

  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <button onClick={toggleSidebar} className="text-gray-600 hover:text-gray-900">
          <Menu size={24} />
        </button>
        <h1 className="text-2xl font-bold">
          {currentRun ? `Run: ${currentRun.goal.substring(0, 50)}...` : 'Kodo Dashboard'}
        </h1>
      </div>

      <div className="flex items-center gap-4">
        <button className="relative text-gray-600 hover:text-gray-900">
          <Bell size={24} />
          <span className="absolute top-0 right-0 w-2 h-2 bg-red-500 rounded-full"></span>
        </button>
        <button className="text-gray-600 hover:text-gray-900">
          <Settings size={24} />
        </button>
        <div className="w-10 h-10 bg-blue-600 rounded-full flex items-center justify-center">
          <span className="text-white font-bold text-sm">V</span>
        </div>
      </div>
    </header>
  )
}
