'use client'

import { Card } from '@/components/Card'
import { mockUsers, mockSubApiKeys } from '@/lib/mockData'
import { FiEdit2, FiTrash2, FiPlus } from 'react-icons/fi'

export default function UsersPage() {
  const users = mockUsers.filter((u) => u.role === 'user')

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">User Management</h1>
          <p className="text-gray-600 mt-2">Manage hackathon participants and team members</p>
        </div>
        <button className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg flex items-center gap-2 transition-colors">
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
                const userKeys = mockSubApiKeys.filter((k) => k.owner_id === user.id)
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
                        {new Date(user.createdAt).toLocaleDateString()}
                      </p>
                    </td>
                    <td className="py-4 px-4 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          title="Edit user"
                          className="text-blue-600 hover:text-blue-800 p-1.5 rounded hover:bg-blue-50 transition-colors"
                        >
                          <FiEdit2 className="text-lg" />
                        </button>
                        <button
                          title="Delete user"
                          className="text-red-600 hover:text-red-800 p-1.5 rounded hover:bg-red-50 transition-colors"
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

      {/* Placeholder for user creation form */}
      <Card className="mt-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Add New User</h2>
        <p className="text-gray-600 text-sm italic">
          Form placeholder - will be connected to backend API
        </p>
        <div className="mt-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text"
              placeholder="e.g., Team Alpha"
              disabled
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              placeholder="e.g., team@hackathon.dev"
              disabled
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500"
            />
          </div>
          <button
            disabled
            className="bg-gray-300 text-gray-600 font-medium py-2 px-4 rounded-lg cursor-not-allowed"
          >
            Create User
          </button>
        </div>
      </Card>
    </div>
  )
}
