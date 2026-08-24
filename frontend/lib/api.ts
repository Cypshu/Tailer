const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

type ApiQueryParams = Record<string, string | number | boolean>

interface ApiOptions extends RequestInit {
  params?: ApiQueryParams
}

interface ChatCompletionPayload {
  model: string
  messages: Array<{
    role: 'system' | 'user' | 'assistant'
    content: string
  }>
  max_tokens?: number
  temperature?: number
}

export interface SubApiKey {
  id: string
  name: string
  key_prefix: string
  owner_id: string
  allowed_models: string[]
  status: 'active' | 'paused' | 'revoked' | 'expired'
  rate_limit_per_minute: number | null
  daily_request_limit: number
  monthly_token_limit: number
  monthly_budget_eur: number
  max_tokens_per_request: number | null
  created_at: string
  expires_at: string
}

export interface CreatedSubApiKey extends SubApiKey {
  /** Returned only by POST /admin/keys and never by list/detail endpoints. */
  key: string
}

function getAuthHeaders(): Record<string, string> {
  // Only available in browser
  if (typeof window === 'undefined') return {}

  const token = localStorage.getItem('access_token')
  if (!token) return {}

  return {
    Authorization: `Bearer ${token}`,
  }
}

export async function apiCall(endpoint: string, options: ApiOptions = {}) {
  const { params, ...fetchOptions } = options

  let url = `${API_BASE_URL}${endpoint}`
  if (params) {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      searchParams.append(key, String(value))
    })
    url += `?${searchParams.toString()}`
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getAuthHeaders(),
  }

  if (fetchOptions.headers instanceof Headers) {
    fetchOptions.headers.forEach((value, key) => {
      headers[key] = value
    })
  } else if (fetchOptions.headers && typeof fetchOptions.headers === 'object') {
    Object.assign(headers, fetchOptions.headers as Record<string, string>)
  }

  const response = await fetch(url, {
    ...fetchOptions,
    headers,
  })

  if (!response.ok) {
    if (response.status === 401) {
      // Token expired or invalid - clear storage and redirect
      if (typeof window !== 'undefined') {
        localStorage.clear()
        window.location.href = '/login'
      }
    }
    throw new Error(`API error: ${response.statusText}`)
  }

  return response.json()
}

export const api = {
  // Admin endpoints
  admin: {
    // Read operations
    getDashboardStats: () => apiCall('/admin/dashboard/stats'),
    getUsers: () => apiCall('/admin/users'),
    getUser: (userId: string) => apiCall(`/admin/users/${userId}`),
    getKeys: () => apiCall('/admin/keys') as Promise<SubApiKey[]>,
    getKey: (keyId: string) =>
      apiCall(`/admin/keys/${keyId}`) as Promise<SubApiKey>,
    getUsage: (params?: ApiQueryParams) =>
      apiCall('/admin/usage', { params: params || {} }),

    // Write operations
    createUser: (userData: {
      email: string
      name: string
      role: 'admin' | 'user'
    }) =>
      apiCall('/admin/users', {
        method: 'POST',
        body: JSON.stringify(userData),
      }),
    createKey: (keyData: {
      name: string
      owner_user_id: string
      allowed_models: string[]
      rate_limit_per_minute?: number | null
      daily_request_limit: number
      monthly_token_limit: number
      monthly_budget_eur: number
      max_tokens_per_request?: number | null
      expires_at: string
    }) =>
      apiCall('/admin/keys', {
        method: 'POST',
        body: JSON.stringify(keyData),
      }) as Promise<CreatedSubApiKey>,
    revokeKey: (keyId: string) =>
      apiCall(`/admin/keys/${keyId}`, { method: 'DELETE' }),
  },

  // User endpoints
  user: {
    getCurrentUser: () => apiCall('/user/me'),
    getMyKeys: () => apiCall('/user/keys') as Promise<SubApiKey[]>,
    getKey: (keyId: string) =>
      apiCall(`/user/keys/${keyId}`) as Promise<SubApiKey>,
    getMyUsage: (params?: ApiQueryParams) =>
      apiCall('/user/usage', { params: params || {} }),
    getStats: () => apiCall('/user/stats'),
  },

  // Runtime endpoints
  chat: {
    complete: (data: ChatCompletionPayload) =>
      apiCall('/v1/chat/completions', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  },
}
