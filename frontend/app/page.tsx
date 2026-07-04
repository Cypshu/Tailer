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
            Secure API Gateway for LLM Access Control
          </p>

          <p className="text-gray-700 mb-8 leading-relaxed">
            Split, control, and monitor LLM API usage through controlled Sub-API Keys. Perfect for hackathons,
            teams, and applications that need safe, shared access to LLM providers.
          </p>

          {/* Demo Access */}
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-6 mb-8 border border-blue-200">
            <h3 className="font-semibold text-gray-900 mb-4">Try the Demo</h3>
            <p className="text-sm text-gray-700 mb-4">
              Explore both the admin and user dashboards with sample data:
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Link
                href="/admin"
                className="flex items-center justify-between bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-lg transition-colors group"
              >
                <span className="flex items-center gap-2">
                  <FiShield /> Admin Dashboard
                </span>
                <FiArrowRight className="group-hover:translate-x-1 transition-transform" />
              </Link>

              <Link
                href="/user/dashboard"
                className="flex items-center justify-between bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 px-4 rounded-lg transition-colors group"
              >
                <span className="flex items-center gap-2">
                  <FiBarChart /> User Dashboard
                </span>
                <FiArrowRight className="group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </div>

          {/* Features */}
          <div className="space-y-4 mb-8">
            <h3 className="font-semibold text-gray-900">Platform Features</h3>
            <ul className="space-y-2 text-gray-700">
              <li className="flex items-start gap-3">
                <span className="text-blue-600 font-bold mt-0.5">✓</span>
                <span>Create and manage Sub-API Keys with custom permissions</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-blue-600 font-bold mt-0.5">✓</span>
                <span>Real-time usage monitoring and cost tracking</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-blue-600 font-bold mt-0.5">✓</span>
                <span>Rate limiting and budget enforcement</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-blue-600 font-bold mt-0.5">✓</span>
                <span>OpenAI-compatible REST API endpoints</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-blue-600 font-bold mt-0.5">✓</span>
                <span>Multi-provider support (OpenAI, Anthropic, etc.)</span>
              </li>
            </ul>
          </div>

          {/* Status */}
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-8">
            <p className="text-sm text-yellow-900">
              <span className="font-semibold">Status:</span> Frontend prototype with mock data. Backend API coming
              soon.
            </p>
          </div>

          <p className="text-center text-gray-600 text-sm">
            Use the navigation bar at the top to switch between Admin and User views.
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
