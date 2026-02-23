'use client'

import { useStore } from '@/lib/store'
import { useAuth } from '@/lib/auth'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Menu, Settings, Bell, LogOut } from 'lucide-react'

export default function Header() {
  const { toggleSidebar, currentRun } = useStore()
  const { user, logout } = useAuth()
  const router = useRouter()
  const [showMenu, setShowMenu] = useState(false)

  const handleLogout = () => {
    logout()
    document.cookie = 'kodo-auth=; path=/; max-age=0'
    router.push('/login')
  }

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

        {/* User Menu */}
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="w-10 h-10 bg-gradient-to-br from-blue-600 to-blue-700 rounded-full flex items-center justify-center hover:shadow-lg transition-shadow"
          >
            <img
              src={user?.avatar || `https://api.dicebear.com/7.x/avataaars/svg?seed=${user?.email}`}
              alt="Avatar"
              className="w-full h-full rounded-full"
            />
          </button>

          {/* Dropdown Menu */}
          {showMenu && (
            <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden z-50">
              <div className="px-4 py-3 border-b border-gray-200">
                <p className="text-sm font-medium text-gray-900">{user?.name}</p>
                <p className="text-xs text-gray-500">{user?.email}</p>
              </div>
              <button
                onClick={handleLogout}
                className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
              >
                <LogOut size={16} />
                Sign Out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
