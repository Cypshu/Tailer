'use client'

import { Card } from '@/components/Card'
import { api } from '@/lib/api'
import { FiEdit2, FiTrash2, FiPlus, FiX } from 'react-icons/fi'
import { useEffect, useState } from 'react'

interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'user'
  created_at: string
}

interface SubApiKey {
  id: string
  owner_id: string
}

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [keys, setKeys] = useState<SubApiKey[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({ email: '', name: '', role: 'user' as const })
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        setError(null)
        const [usersData, keysData] = await Promise.all([
          api.admin.getUsers(),
          api.admin.getKeys(),
        ])
        setUsers(usersData.filter((u: User) => u.role === 'user'))
        setKeys(keysData)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load users')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setSubmitError(null)
    setSuccessMessage(null)

    try {
      const newUser = await api.admin.createUser({
        email: formData.email,
        name: formData.name,
        role: 'user',
      })
      setUsers([...users, newUser])
      setFormData({ email: '', name: '', role: 'user' })
      setShowForm(false)
      setSuccessMessage(`User "${newUser.name}" created successfully!`)
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to create user')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        <p className="text-gray-600">Loading users...</p>
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
          <h1 className="text-3xl font-bold text-gray-900">User Management</h1>
          <p className="text-gray-600 mt-2">Manage hackathon participants and team members</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg flex items-center gap-2 transition-colors"
        >
          <FiPlus /> Add User
        </button>
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-3 px-4 font-semibold text-gray-700">Name</th>
                <th className="text-left py-3 px-4 font-semibold text-gray-700">Email</th>
                <th className="text-center py-3 px-4 font-semibold text-gray-700">API Keys</th>
                <th className="text-left py-3 px-4 font-semibold text-gray-700">Joined</th>
                <th className="text-center py-3 px-4 font-semibold text-gray-700">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => {
                const userKeys = keys.filter((k) => k.owner_id === user.id)
                return (
                  <tr key={user.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="py-4 px-4">
                      <p className="font-medium text-gray-900">{user.name}</p>
                    </td>
                    <td className="py-4 px-4">
                      <p className="text-gray-600 text-sm">{user.email}</p>
                    </td>
                    <td className="py-4 px-4 text-center">
                      <span className="inline-block bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-medium">
                        {userKeys.length}
                      </span>
                    </td>
                    <td className="py-4 px-4">
                      <p className="text-gray-600 text-sm">
                        {new Date(user.created_at).toLocaleDateString()}
                      </p>
                    </td>
                    <td className="py-4 px-4 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          disabled
                          title="Edit user (coming soon)"
                          className="text-gray-400 cursor-not-allowed p-1.5 rounded transition-colors"
                        >
                          <FiEdit2 className="text-lg" />
                        </button>
                        <button
                          disabled
                          title="Delete user (coming soon)"
                          className="text-gray-400 cursor-not-allowed p-1.5 rounded transition-colors"
                        >
                          <FiTrash2 className="text-lg" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* User creation form */}
      {showForm && (
        <Card className="mt-8 border-blue-200 bg-blue-50">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Add New User</h2>
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

          <form onSubmit={handleCreateUser} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                placeholder="e.g., Team Alpha"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                placeholder="e.g., team@hackathon.dev"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={submitting}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium py-2 px-4 rounded-lg transition-colors"
              >
                {submitting ? 'Creating...' : 'Create User'}
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
    </div>
  )
}
