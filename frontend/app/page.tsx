'use client'

import Link from 'next/link'
import { FiArrowRight, FiShield, FiBarChart } from 'react-icons/fi'

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center px-4">
      <div className="max-w-2xl w-full">
        <div className="bg-white rounded-xl shadow-2xl p-8 md:p-12">
          <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">TAILER</h1>
          <p className="text-xl text-gray-600 mb-8">
            Development prototype for managed LLM API access
          </p>

          <p className="text-gray-700 mb-8 leading-relaxed">
            Explore a mock-backed gateway flow with dashboard authentication, managed demo Sub-API keys,
            an OpenAI-style runtime endpoint, and in-memory usage tracking.
          </p>

          {/* Demo Access */}
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-6 mb-8 border border-blue-200">
            <h3 className="font-semibold text-gray-900 mb-4">Try the Demo</h3>
            <p className="text-sm text-gray-700 mb-4">
              Login to explore both the admin and user dashboards with sample data:
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Link
                href="/login"
                className="flex items-center justify-between bg-green-600 hover:bg-green-700 text-white font-medium py-3 px-4 rounded-lg transition-colors group"
              >
                <span>Login</span>
                <FiArrowRight className="group-hover:translate-x-1 transition-transform" />
              </Link>

              <Link
                href="/admin"
                className="flex items-center justify-between bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-lg transition-colors group"
              >
                <span className="flex items-center gap-2">
                  <FiShield /> Admin
                </span>
                <FiArrowRight className="group-hover:translate-x-1 transition-transform" />
              </Link>

              <Link
                href="/user/dashboard"
                className="flex items-center justify-between bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 px-4 rounded-lg transition-colors group"
              >
                <span className="flex items-center gap-2">
                  <FiBarChart /> User
                </span>
                <FiArrowRight className="group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </div>

          {/* Features */}
          <div className="space-y-4 mb-8">
            <h3 className="font-semibold text-gray-900">Current Demo Features</h3>
            <ul className="space-y-2 text-gray-700">
              <li className="flex items-start gap-3">
                <span className="text-blue-600 font-bold mt-0.5">✓</span>
                <span>Create and revoke in-memory demo Sub-API keys</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-blue-600 font-bold mt-0.5">✓</span>
                <span>JWT login with admin and user role checks</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-blue-600 font-bold mt-0.5">✓</span>
                <span>Mock-provider usage and cost estimates</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-blue-600 font-bold mt-0.5">✓</span>
                <span>OpenAI-style chat-completions endpoint</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-blue-600 font-bold mt-0.5">✓</span>
                <span>SQLAlchemy and Alembic persistence scaffold</span>
              </li>
            </ul>
          </div>

          {/* Status */}
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-8">
            <p className="text-sm text-amber-900">
              <span className="font-semibold">Status:</span> Mock-backed prototype. Durable storage, real providers, and rate or budget enforcement are not implemented yet.
            </p>
          </div>

          <p className="text-center text-gray-600 text-sm">
            Demo credentials are displayed after you click Login. Each role has different capabilities.
          </p>
        </div>

        {/* Footer */}
        <div className="text-center mt-8 text-gray-600 text-sm">
          <p>TAILER • Hackathon 2026 • Secure LLM API Access</p>
        </div>
      </div>
    </div>
  )
}
