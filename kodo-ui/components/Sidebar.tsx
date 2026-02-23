'use client'

import { useStore } from '@/lib/store'
import { BarChart3, Zap, Users, DollarSign, Menu } from 'lucide-react'

interface SidebarProps {
  activeView: string
  onViewChange: (view: any) => void
}

export default function Sidebar({ activeView, onViewChange }: SidebarProps) {
  const { toggleSidebar, theme } = useStore()

  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: BarChart3 },
    { id: 'runs', label: 'Runs', icon: Zap },
    { id: 'agents', label: 'Agents', icon: Users },
    { id: 'cost', label: 'Cost Tracker', icon: DollarSign },
  ]

  return (
    <aside className="w-64 bg-white border-r border-gray-200 p-6 space-y-8">
      {/* Logo */}
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-sm">K</span>
        </div>
        <span className="text-xl font-bold">Kodo</span>
      </div>

      {/* Menu */}
      <nav className="space-y-2">
        {menuItems.map((item) => {
          const Icon = item.icon
          const isActive = activeView === item.id
          return (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                isActive
                  ? 'bg-blue-100 text-blue-600 font-medium'
                  : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              <Icon size={20} />
              <span>{item.label}</span>
            </button>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="pt-6 border-t border-gray-200">
        <p className="text-xs text-gray-500">v1.0.0</p>
        <p className="text-xs text-gray-500 mt-1">© 2024 Kodo</p>
      </div>
    </aside>
  )
}
