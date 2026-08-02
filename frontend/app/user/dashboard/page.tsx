'use client'

import { Card } from '@/components/Card'
import { StatCard } from '@/components/StatCard'
import { api } from '@/lib/api'
import { FiKey, FiTrendingUp, FiActivity, FiCopy } from 'react-icons/fi'
import { useEffect, useState } from 'react'

interface SubApiKey {
  id: string
  name: string
  key?: string
  owner_id?: string
  allowed_models?: string[]
  status?: string
  daily_request_limit?: number
  monthly_token_limit?: number
  monthly_budget_eur?: number
  created_at?: string
  expires_at?: string
}

interface UserStats {
  api_keys: number
  total_tokens_used: number
  estimated_cost: number
  total_requests: number
  monthly_token_limit: number
  monthly_budget: number
  token_usage_percent: number
  budget_usage_percent: number
}

interface UsageEvent {
  id: string
  timestamp: string
  model: string
  total_tokens: number
  estimated_cost_eur: number
  status: string
}

export default function UserDashboard() {
  const [stats, setStats] = useState<UserStats | null>(null)
  const [keys, setKeys] = useState<SubApiKey[]>([])
  const [usageEvents, setUsageEvents] = useState<UsageEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copiedKeyId, setCopiedKeyId] = useState<string | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        setError(null)
        const [statsData, keysData, usageData] = await Promise.all([
          api.user.getStats(),
          api.user.getMyKeys(),
          api.user.getMyUsage(),
        ])
        setStats(statsData)
        setKeys(keysData)
        setUsageEvents(usageData)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load user dashboard')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  const handleCopyKey = (key: string) => {
    navigator.clipboard.writeText(key).then(() => {
      setCopiedKeyId(Math.random().toString())
      setTimeout(() => setCopiedKeyId(null), 2000)
    })
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <p className="text-gray-600">Loading dashboard...</p>
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
        <p className="text-gray-600">No data available</p>
      </div>
    )
  }

  const totalTokensUsed = stats.total_tokens_used
  const totalCostEstimated = stats.estimated_cost
  const monthlyTokenLimit = stats.monthly_token_limit
  const monthlyBudget = stats.monthly_budget
  const tokenUsagePercent = stats.token_usage_percent
  const budgetUsagePercent = stats.budget_usage_percent

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">My Dashboard</h1>
        <p className="text-gray-600 mt-2">Monitor your API usage and manage your keys</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="API Keys"
          value={stats.api_keys}
          icon={<FiKey />}
        />
        <StatCard
          label="Tokens Used (This Month)"
          value={totalTokensUsed.toLocaleString()}
          icon={<FiTrendingUp />}
        />
        <StatCard
          label="Estimated Cost (EUR)"
          value={`€${totalCostEstimated.toFixed(2)}`}
          icon={<FiActivity />}
        />
        <StatCard
          label="Total Requests"
          value={stats.total_requests}
          icon={<FiActivity />}
        />
      </div>

      {/* Usage Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Token Usage */}
        <Card title="Token Usage">
          <div className="space-y-4">
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-gray-700">Monthly Limit</span>
                <span className="text-sm font-semibold text-gray-900">
                  {totalTokensUsed.toLocaleString()} / {monthlyTokenLimit.toLocaleString()}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-3">
                <div
                  className={`h-3 rounded-full transition-all ${
                    tokenUsagePercent > 80 ? 'bg-red-500' : tokenUsagePercent > 50 ? 'bg-yellow-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${Math.min(tokenUsagePercent, 100)}%` }}
                />
              </div>
              <p className="text-xs text-gray-600 mt-2">
                {tokenUsagePercent.toFixed(1)}% of monthly limit used
              </p>
            </div>
          </div>
        </Card>

        {/* Budget Usage */}
        <Card title="Budget Usage">
          <div className="space-y-4">
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-gray-700">Monthly Budget</span>
                <span className="text-sm font-semibold text-gray-900">
                  €{totalCostEstimated.toFixed(2)} / €{monthlyBudget.toFixed(2)}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-3">
                <div
                  className={`h-3 rounded-full transition-all ${
                    budgetUsagePercent > 80 ? 'bg-red-500' : budgetUsagePercent > 50 ? 'bg-yellow-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${Math.min(budgetUsagePercent, 100)}%` }}
                />
              </div>
              <p className="text-xs text-gray-600 mt-2">
                {budgetUsagePercent.toFixed(1)}% of monthly budget spent
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* My API Keys */}
      <Card title="My API Keys" className="mb-8">
        <div className="space-y-4">
          {keys.length > 0 ? (
            keys.map((key) => (
              <div key={key.id} className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h4 className="font-semibold text-gray-900">{key.name}</h4>
                    {key.key && (
                      <p className="text-xs text-gray-600 font-mono mt-1">
                        {key.key.substring(0, 15)}...{key.key.substring(key.key.length - 5)}
                      </p>
                    )}
                  </div>
                  <span className="inline-block bg-green-100 text-green-800 px-2 py-1 rounded text-xs font-medium">
                    {key.status || 'Active'}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-4 text-sm mb-3 pb-3 border-t border-gray-100">
                  <div>
                    <p className="text-gray-600">Allowed Models</p>
                    <p className="font-medium text-gray-900">{key.allowed_models?.length || 0}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Daily Requests</p>
                    <p className="font-medium text-gray-900">{key.daily_request_limit || '-'}</p>
                  </div>
                  <div>
                    <p className="text-gray-600">Expires</p>
                    <p className="font-medium text-gray-900">
                      {key.expires_at ? new Date(key.expires_at).toLocaleDateString() : '-'}
                    </p>
                  </div>
                </div>

                {key.key && (
                  <button
                    onClick={() => handleCopyKey(key.key!)}
                    className={`text-sm font-medium flex items-center gap-1 transition-colors ${
                      copiedKeyId ? 'text-green-600' : 'text-blue-600 hover:text-blue-800'
                    }`}
                  >
                    <FiCopy className="text-xs" /> {copiedKeyId ? 'Copied!' : 'Copy Key'}
                  </button>
                )}
              </div>
            ))
          ) : (
            <p className="text-gray-600 text-center py-4">No API keys assigned yet. Contact your organizer.</p>
          )}
        </div>
      </Card>

      {/* Recent Requests */}
      <Card title="Recent API Requests">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-3 px-4 font-semibold text-gray-700">Time</th>
                <th className="text-left py-3 px-4 font-semibold text-gray-700">Model</th>
                <th className="text-right py-3 px-4 font-semibold text-gray-700">Tokens</th>
                <th className="text-right py-3 px-4 font-semibold text-gray-700">Cost</th>
                <th className="text-center py-3 px-4 font-semibold text-gray-700">Status</th>
              </tr>
            </thead>
            <tbody>
              {usageEvents.slice(0, 10).map((event) => (
                <tr key={event.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-3 px-4 text-gray-600">
                    {new Date(event.timestamp).toLocaleTimeString()}
                  </td>
                  <td className="py-3 px-4 text-gray-900">{event.model}</td>
                  <td className="py-3 px-4 text-right text-gray-600">{event.total_tokens}</td>
                  <td className="py-3 px-4 text-right text-gray-600">
                    €{event.estimated_cost_eur.toFixed(4)}
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span className="inline-block px-2 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800">
                      {event.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
