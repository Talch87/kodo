'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { ArrowRight, Zap, BarChart3, Users, DollarSign } from 'lucide-react'

export default function Home() {
  const router = useRouter()
  const { isAuthenticated } = useAuth()

  useEffect(() => {
    if (isAuthenticated) {
      router.push('/dashboard')
    }
  }, [isAuthenticated, router])

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-600 via-blue-700 to-blue-900">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-blue-400 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob"></div>
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-purple-400 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob animation-delay-2000"></div>
      </div>

      {/* Navigation */}
      <nav className="relative z-10 flex items-center justify-between p-6">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 bg-white bg-opacity-20 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-xl">K</span>
          </div>
          <span className="text-white text-xl font-bold">Kodo</span>
        </div>
        <a
          href="/login"
          className="px-6 py-2 bg-white text-blue-600 font-medium rounded-lg hover:bg-opacity-90 transition-all"
        >
          Sign In
        </a>
      </nav>

      {/* Hero Section */}
      <div className="relative z-10 flex flex-col items-center justify-center min-h-[calc(100vh-100px)] px-4 text-center">
        <h1 className="text-5xl md:text-6xl font-bold text-white mb-6 leading-tight">
          Autonomous Code Generation
          <br />
          <span className="bg-gradient-to-r from-blue-200 to-blue-100 bg-clip-text text-transparent">
            That Just Works
          </span>
        </h1>

        <p className="text-xl text-blue-100 mb-8 max-w-2xl">
          Kodo is an autonomous AI agent that builds, tests, and improves code 24/7. Submit a goal and let it work while you sleep.
        </p>

        <div className="flex gap-4 mb-12">
          <a
            href="/login"
            className="px-8 py-3 bg-white text-blue-600 font-bold rounded-lg hover:shadow-lg transition-all flex items-center gap-2"
          >
            Get Started <ArrowRight size={20} />
          </a>
          <button
            onClick={() => router.push('/login')}
            className="px-8 py-3 bg-white bg-opacity-10 text-white font-bold rounded-lg border border-white border-opacity-20 hover:bg-opacity-20 transition-all"
          >
            Try Demo
          </button>
        </div>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-20 max-w-5xl">
          {[
            { icon: Zap, title: 'Instant Execution', desc: 'Submit goals and get working code' },
            { icon: BarChart3, title: 'Real-time Tracking', desc: 'Monitor progress and performance' },
            { icon: Users, title: 'Multi-Agent', desc: 'Specialized agents for each task' },
            { icon: DollarSign, title: 'Cost Transparent', desc: 'Track spending per run' },
          ].map((feature, i) => {
            const Icon = feature.icon
            return (
              <div
                key={i}
                className="bg-white bg-opacity-10 backdrop-blur-lg border border-white border-opacity-20 rounded-lg p-6 text-white hover:bg-opacity-20 transition-all"
              >
                <Icon size={32} className="mb-3 text-blue-200" />
                <h3 className="font-bold mb-2">{feature.title}</h3>
                <p className="text-sm text-blue-100">{feature.desc}</p>
              </div>
            )
          })}
        </div>
      </div>

      <style jsx>{`
        @keyframes blob {
          0%, 100% {
            transform: translate(0, 0) scale(1);
          }
          33% {
            transform: translate(30px, -50px) scale(1.1);
          }
          66% {
            transform: translate(-20px, 20px) scale(0.9);
          }
        }
        .animate-blob {
          animation: blob 7s infinite;
        }
        .animation-delay-2000 {
          animation-delay: 2s;
        }
      `}</style>
    </div>
  )
}
