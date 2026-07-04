'use client'

import { Card } from '@/components/Card'
import { StatCard } from '@/components/StatCard'
import { api } from '@/lib/api'
import { FiKey, FiUsers, FiTrendingUp, FiActivity } from 'react-icons/fi'
import { useEffect, useState } from 'react'

interface DashboardStats {
  active_keys: number
  total_tokens_used: number
  total_cost_estimated: number
  active_users: number
  total_requests: number
}

interface UsageEvent {
  id: string
  timestamp: string
  sub_key_id: string
  user_id: string
  model: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  estimated_cost_eur: number
  latency_ms: number
  status: 'success' | 'failed'
}

interface SubApiKey {
  id: string
  name: string
  owner_id?: string
}

interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'user'
  created_at: string
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [usageEvents, setUsageEvents] = useState<UsageEvent[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [keys, setKeys] = useState<SubApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        setError(null)
        const [statsData, usageData, usersData, keysData] = await Promise.all([
          api.admin.getDashboardStats(),
          api.admin.getUsage(),
          api.admin.getUsers(),
          api.admin.getKeys(),
        ])
        setStats(statsData)
        setUsageEvents(usageData)
        setUsers(usersData)
        setKeys(keysData)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard data')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="text-center">
          <p className="text-gray-600">Loading dashboard...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">Error: {error}</p>
        </div>
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <div className="text-center">
          <p className="text-gray-600">No data available</p>
        </div>
      </div>
    )
  }

  const totalTokens = stats.total_tokens_used
  const totalCost = stats.total_cost_estimated
  const activeKeys = stats.active_keys
  const totalUsers = stats.active_users
  const totalRequests = stats.total_requests

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Admin Dashboard</h1>
        <p className="text-gray-600 mt-2">Overview of TAILER platform usage and management</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <StatCard
          label="Active API Keys"
          value={activeKeys}
          icon={<FiKey />}
          trendValue="+2 this week"
          trend="up"
        />
        <StatCard
          label="Total Tokens Used"
          value={totalTokens.toLocaleString()}
          icon={<FiTrendingUp />}
        />
        <StatCard
          label="Est. Cost (EUR)"
          value={`€${totalCost.toFixed(2)}`}
          icon={<FiActivity />}
        />
        <StatCard
          label="Active Users"
          value={totalUsers}
          icon={<FiUsers />}
        />
        <StatCard
          label="Total Requests"
          value={totalRequests}
          icon={<FiActivity />}
        />
      </div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Recent Usage */}
        <Card title="Recent API Requests" className="lg:col-span-2">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-3 px-4 font-semibold text-gray-700">Time</th>
                  <th className="text-left py-3 px-4 font-semibold text-gray-700">User</th>
                  <th className="text-left py-3 px-4 font-semibold text-gray-700">Model</th>
                  <th className="text-right py-3 px-4 font-semibold text-gray-700">Tokens</th>
                  <th className="text-right py-3 px-4 font-semibold text-gray-700">Cost</th>
                  <th className="text-center py-3 px-4 font-semibold text-gray-700">Status</th>
                </tr>
              </thead>
              <tbody>
                {usageEvents.slice(0, 5).map((event) => (
                  <tr key={event.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-3 px-4 text-gray-600">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="py-3 px-4 text-gray-900">
                      {keys.find((k) => k.id === event.sub_key_id)?.name}
                    </td>
                    <td className="py-3 px-4 text-gray-600">{event.model}</td>
                    <td className="py-3 px-4 text-right text-gray-600">{event.total_tokens}</td>
                    <td className="py-3 px-4 text-right text-gray-600">
                      €{event.estimated_cost_eur.toFixed(4)}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${
                          event.status === 'success'
                            ? 'bg-green-100 text-green-800'
                            : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {event.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 pt-4 border-t border-gray-200">
            <a href="/admin/keys" className="text-blue-600 hover:text-blue-800 text-sm font-medium">
              View all requests →
            </a>
          </div>
        </Card>

        {/* Quick Actions */}
        <Card title="Quick Actions">
          <div className="space-y-3">
            <a
              href="/admin/keys"
              className="block w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg transition-colors text-center"
            >
              + Create Sub-API Key
            </a>
            <a
              href="/admin/users"
              className="block w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg transition-colors text-center"
            >
              + Add User
            </a>
            <button
              disabled
              className="w-full bg-gray-200 text-gray-600 font-medium py-2 px-4 rounded-lg cursor-not-allowed text-sm"
              title="Coming soon"
            >
              📊 Export Usage Report
            </button>
            <button
              disabled
              className="w-full bg-gray-200 text-gray-600 font-medium py-2 px-4 rounded-lg cursor-not-allowed text-sm"
              title="Coming soon"
            >
              ⚙️ Provider Settings
            </button>
          </div>
        </Card>
      </div>

      {/* Active Users Section */}
      <Card title="Active Users">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {users
            .filter((u) => u.role === 'user')
            .map((user) => {
              const userKeys = keys.filter((k) => k.owner_id === user.id)
              const userUsage = usageEvents.filter((e) => e.user_id === user.id)
              return (
                <div key={user.id} className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
                  <h4 className="font-semibold text-gray-900">{user.name}</h4>
                  <p className="text-sm text-gray-600">{user.email}</p>
                  <div className="mt-3 space-y-2 text-sm">
                    <p className="text-gray-700">
                      <span className="font-medium">Keys:</span> {userKeys.length}
                    </p>
                    <p className="text-gray-700">
                      <span className="font-medium">Requests:</span> {userUsage.length}
                    </p>
                    <p className="text-gray-700">
                      <span className="font-medium">Total Tokens:</span>{' '}
                      {userUsage.reduce((sum, e) => sum + e.total_tokens, 0)}
                    </p>
                  </div>
                  <button className="mt-3 text-blue-600 hover:text-blue-800 text-sm font-medium">
                    View Details →
                  </button>
                </div>
              )
            })}
        </div>
      </Card>
    </div>
  )
}
