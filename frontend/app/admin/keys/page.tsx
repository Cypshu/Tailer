'use client'

import { Card } from '@/components/Card'
import { mockSubApiKeys, mockUsers } from '@/lib/mockData'
import { FiCopy, FiRotateCw, FiTrash2, FiPlus, FiEye, FiEyeOff } from 'react-icons/fi'
import { useState } from 'react'

export default function KeysPage() {
  const [revealedKey, setRevealedKey] = useState<string | null>(null)

  const maskKey = (key: string) => {
    const start = key.substring(0, 10)
    const end = key.substring(key.length - 5)
    return `${start}...${end}`
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">API Key Management</h1>
          <p className="text-gray-600 mt-2">Create and manage Sub-API Keys for users</p>
        </div>
        <button className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg flex items-center gap-2 transition-colors">
          <FiPlus /> Generate New Key
        </button>
      </div>

      <div className="space-y-4">
        {mockSubApiKeys.map((key) => {
          const owner = mockUsers.find((u) => u.id === key.owner_id)
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
                  <p className="text-sm font-semibold text-gray-900">{key.daily_request_limit}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-600 uppercase">Monthly Tokens</p>
                  <p className="text-sm font-semibold text-gray-900">
                    {(key.monthly_token_limit / 1000000).toFixed(1)}M
                  </p>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-600 uppercase">Budget</p>
                  <p className="text-sm font-semibold text-gray-900">€{key.monthly_budget_eur.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-600 uppercase">Expires</p>
                  <p className="text-sm font-semibold text-gray-900">
                    {new Date(key.expires_at).toLocaleDateString()}
                  </p>
                </div>
              </div>

              {/* Models */}
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

              {/* Actions */}
              <div className="flex items-center gap-2">
                <button className="flex items-center gap-2 px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors text-sm font-medium">
                  <FiRotateCw className="text-lg" />
                  Rotate
                </button>
                <button className="flex items-center gap-2 px-3 py-2 text-red-600 hover:text-red-900 hover:bg-red-50 rounded-lg transition-colors text-sm font-medium">
                  <FiTrash2 className="text-lg" />
                  Revoke
                </button>
              </div>
            </Card>
          )
        })}
      </div>

      {/* Placeholder for key creation */}
      <Card className="mt-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Create New API Key</h2>
        <p className="text-gray-600 text-sm italic mb-4">
          Form placeholder - will be connected to backend API
        </p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Key Name</label>
            <input
              type="text"
              placeholder="e.g., Team Alpha Hackathon"
              disabled
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Assign to User</label>
            <select disabled className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500">
              <option>Select user...</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Daily Request Limit</label>
              <input type="number" placeholder="500" disabled className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Monthly Token Limit</label>
              <input type="number" placeholder="1000000" disabled className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500" />
            </div>
          </div>
          <button disabled className="bg-gray-300 text-gray-600 font-medium py-2 px-4 rounded-lg cursor-not-allowed">
            Create Key
          </button>
        </div>
      </Card>
    </div>
  )
}
