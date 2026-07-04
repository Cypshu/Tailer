'use client'

import { Card } from '@/components/Card'
import { api } from '@/lib/api'
import { FiCopy, FiRotateCw, FiTrash2, FiPlus, FiEye, FiEyeOff, FiX } from 'react-icons/fi'
import { useState, useEffect } from 'react'

interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'user'
  created_at: string
}

interface SubApiKey {
  id: string
  name: string
  key: string
  owner_id: string
  status: string
  daily_request_limit?: number
  monthly_token_limit?: number
  monthly_budget_eur?: number
  allowed_models?: string[]
}

export default function KeysPage() {
  const [keys, setKeys] = useState<SubApiKey[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [revealedKey, setRevealedKey] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({
    name: '',
    owner_user_id: '',
    allowed_models: ['gpt-4o-mini'],
    daily_request_limit: 500,
    monthly_token_limit: 1000000,
    monthly_budget_eur: 50,
    expires_at: new Date(new Date().getFullYear() + 1, 11, 31).toISOString().split('T')[0],
  })
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [revoking, setRevoking] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        setError(null)
        const [keysData, usersData] = await Promise.all([
          api.admin.getKeys(),
          api.admin.getUsers(),
        ])
        setKeys(keysData)
        setUsers(usersData)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load keys')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setSubmitError(null)

    try {
      const newKey = await api.admin.createKey({
        name: formData.name,
        owner_user_id: formData.owner_user_id,
        allowed_models: formData.allowed_models,
        daily_request_limit: formData.daily_request_limit,
        monthly_token_limit: formData.monthly_token_limit,
        monthly_budget_eur: formData.monthly_budget_eur,
        expires_at: formData.expires_at,
      })
      setKeys([...keys, newKey])
      setFormData({
        name: '',
        owner_user_id: '',
        allowed_models: ['gpt-4o-mini'],
        daily_request_limit: 500,
        monthly_token_limit: 1000000,
        monthly_budget_eur: 50,
        expires_at: new Date(new Date().getFullYear() + 1, 11, 31).toISOString().split('T')[0],
      })
      setShowForm(false)
      setSuccessMessage(`Key "${newKey.name}" created successfully!`)
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to create key')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRevokeKey = async (keyId: string) => {
    if (!confirm('Are you sure you want to revoke this key? This cannot be undone.')) return

    setRevoking(keyId)
    try {
      await api.admin.revokeKey(keyId)
      setKeys(keys.map((k) => (k.id === keyId ? { ...k, status: 'revoked' } : k)))
      setSuccessMessage('Key revoked successfully!')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to revoke key')
    } finally {
      setRevoking(null)
    }
  }

  const maskKey = (key: string) => {
    const start = key.substring(0, 10)
    const end = key.substring(key.length - 5)
    return `${start}...${end}`
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <p className="text-gray-600">Loading keys...</p>
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

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {successMessage && (
        <div className="mb-4 bg-green-50 border border-green-200 rounded-lg p-4">
          <p className="text-green-800">{successMessage}</p>
        </div>
      )}

      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">API Key Management</h1>
          <p className="text-gray-600 mt-2">Create and manage Sub-API Keys for users</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg flex items-center gap-2 transition-colors"
        >
          <FiPlus /> Generate New Key
        </button>
      </div>

      {/* Key Creation Form */}
      {showForm && (
        <Card className="mb-8 border-blue-200 bg-blue-50">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Create New Sub-API Key</h2>
            <button
              onClick={() => setShowForm(false)}
              className="text-gray-500 hover:text-gray-700"
            >
              <FiX className="text-xl" />
            </button>
          </div>

          {submitError && (
            <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-red-800 text-sm">{submitError}</p>
            </div>
          )}

          <form onSubmit={handleCreateKey} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Key Name</label>
              <input
                type="text"
                placeholder="e.g., Team Alpha Hackathon Key"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Owner</label>
              <select
                value={formData.owner_user_id}
                onChange={(e) => setFormData({ ...formData, owner_user_id: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select a user...</option>
                {users
                  .filter((u) => u.role === 'user')
                  .map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.name} ({user.email})
                    </option>
                  ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Daily Request Limit
                </label>
                <input
                  type="number"
                  value={formData.daily_request_limit}
                  onChange={(e) =>
                    setFormData({ ...formData, daily_request_limit: parseInt(e.target.value) })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Monthly Budget (EUR)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.monthly_budget_eur}
                  onChange={(e) =>
                    setFormData({ ...formData, monthly_budget_eur: parseFloat(e.target.value) })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Expires At</label>
              <input
                type="date"
                value={formData.expires_at}
                onChange={(e) => setFormData({ ...formData, expires_at: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="flex gap-2">
              <button
                type="submit"
                disabled={submitting}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium py-2 px-4 rounded-lg transition-colors"
              >
                {submitting ? 'Creating...' : 'Create Key'}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="bg-gray-200 hover:bg-gray-300 text-gray-900 font-medium py-2 px-4 rounded-lg transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </Card>
      )}

      <div className="space-y-4">
        {keys.map((key) => {
          const owner = users.find((u) => u.id === key.owner_id)
          const isRevealed = revealedKey === key.id

          return (
            <Card key={key.id}>
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-gray-900">{key.name}</h3>
                  <p className="text-sm text-gray-600">Owner: {owner?.name || 'Unknown'}</p>
                </div>
                <span
                  className={`inline-block px-3 py-1 rounded-full text-sm font-semibold ${
                    key.status === 'active'
                      ? 'bg-green-100 text-green-800'
                      : key.status === 'paused'
                        ? 'bg-yellow-100 text-yellow-800'
                        : 'bg-red-100 text-red-800'
                  }`}
                >
                  {key.status.charAt(0).toUpperCase() + key.status.slice(1)}
                </span>
              </div>

              {/* Key Display */}
              <div className="bg-gray-100 rounded-lg p-3 mb-4 flex items-center justify-between gap-2">
                <code className="font-mono text-sm text-gray-700 break-all">
                  {isRevealed ? key.key : maskKey(key.key)}
                </code>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setRevealedKey(isRevealed ? null : key.id)}
                    className="text-gray-600 hover:text-gray-900 p-1.5 rounded hover:bg-gray-200 transition-colors"
                    title={isRevealed ? 'Hide' : 'Show'}
                  >
                    {isRevealed ? <FiEyeOff /> : <FiEye />}
                  </button>
                  <button
                    className="text-gray-600 hover:text-gray-900 p-1.5 rounded hover:bg-gray-200 transition-colors"
                    title="Copy to clipboard"
                  >
                    <FiCopy />
                  </button>
                </div>
              </div>

              {/* Configuration */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 pb-4 border-b border-gray-200">
                <div>
                  <p className="text-xs font-medium text-gray-600 uppercase">Daily Limit</p>
                  <p className="text-sm font-semibold text-gray-900">{key.daily_request_limit || '-'}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-600 uppercase">Monthly Tokens</p>
                  <p className="text-sm font-semibold text-gray-900">
                    {key.monthly_token_limit ? (key.monthly_token_limit / 1000000).toFixed(1) : '-'}M
                  </p>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-600 uppercase">Budget</p>
                  <p className="text-sm font-semibold text-gray-900">€{key.monthly_budget_eur?.toFixed(2) || '-'}</p>
                </div>
              </div>

              {/* Models */}
              {key.allowed_models && key.allowed_models.length > 0 && (
                <div className="mb-4 pb-4 border-b border-gray-200">
                  <p className="text-xs font-medium text-gray-600 uppercase mb-2">Allowed Models</p>
                  <div className="flex flex-wrap gap-2">
                    {key.allowed_models.map((model) => (
                      <span
                        key={model}
                        className="inline-block bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs font-medium"
                      >
                        {model}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex items-center gap-2">
                <button
                  disabled
                  className="flex items-center gap-2 px-3 py-2 text-gray-400 cursor-not-allowed text-sm font-medium"
                  title="Rotation coming soon"
                >
                  <FiRotateCw className="text-lg" />
                  Rotate
                </button>
                {key.status === 'active' && (
                  <button
                    onClick={() => handleRevokeKey(key.id)}
                    disabled={revoking === key.id}
                    className="flex items-center gap-2 px-3 py-2 text-red-600 hover:text-red-900 hover:bg-red-50 rounded-lg transition-colors text-sm font-medium disabled:text-red-400"
                  >
                    <FiTrash2 className="text-lg" />
                    {revoking === key.id ? 'Revoking...' : 'Revoke'}
                  </button>
                )}
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
