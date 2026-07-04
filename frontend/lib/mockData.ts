export interface User {
  id: string
  email: string
  name: string
  role: 'admin' | 'user'
  createdAt: string
}

export interface SubApiKey {
  id: string
  name: string
  key: string
  owner_id: string
  allowed_models: string[]
  status: 'active' | 'paused' | 'revoked' | 'expired'
  daily_request_limit: number
  monthly_token_limit: number
  monthly_budget_eur: number
  created_at: string
  expires_at: string
}

export interface UsageEvent {
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

export interface Project {
  id: string
  name: string
  description: string
  created_at: string
  status: 'active' | 'paused' | 'archived'
}

// Mock Users
export const mockUsers: User[] = [
  {
    id: 'user_1',
    email: 'team_alpha@hackathon.dev',
    name: 'Team Alpha',
    role: 'user',
    createdAt: '2026-07-01T10:00:00Z',
  },
  {
    id: 'user_2',
    email: 'team_beta@hackathon.dev',
    name: 'Team Beta',
    role: 'user',
    createdAt: '2026-07-01T11:00:00Z',
  },
  {
    id: 'user_3',
    email: 'organizer@hackathon.dev',
    name: 'Hackathon Organizer',
    role: 'admin',
    createdAt: '2026-06-30T09:00:00Z',
  },
]

// Mock Projects
export const mockProjects: Project[] = [
  {
    id: 'proj_hackathon_2026',
    name: 'Hackathon 2026',
    description: 'Main hackathon event with OpenAI API access',
    created_at: '2026-06-30T09:00:00Z',
    status: 'active',
  },
]

// Mock Sub-API Keys
export const mockSubApiKeys: SubApiKey[] = [
  {
    id: 'subkey_1',
    name: 'Team Alpha Hackathon Key',
    key: 'tailer_sub_xxxxxxxxxxxxx1',
    owner_id: 'user_1',
    allowed_models: ['gpt-4o-mini', 'gpt-4-turbo'],
    status: 'active',
    daily_request_limit: 500,
    monthly_token_limit: 1000000,
    monthly_budget_eur: 50.0,
    created_at: '2026-07-01T10:30:00Z',
    expires_at: '2026-12-31T23:59:59Z',
  },
  {
    id: 'subkey_2',
    name: 'Team Beta Hackathon Key',
    key: 'tailer_sub_xxxxxxxxxxxxx2',
    owner_id: 'user_2',
    allowed_models: ['gpt-4o-mini'],
    status: 'active',
    daily_request_limit: 300,
    monthly_token_limit: 500000,
    monthly_budget_eur: 25.0,
    created_at: '2026-07-01T11:15:00Z',
    expires_at: '2026-12-31T23:59:59Z',
  },
  {
    id: 'subkey_3',
    name: 'Organizer Full Access',
    key: 'tailer_sub_xxxxxxxxxxxxx3',
    owner_id: 'user_3',
    allowed_models: ['gpt-4o-mini', 'gpt-4-turbo', 'gpt-4-preview'],
    status: 'active',
    daily_request_limit: 10000,
    monthly_token_limit: 10000000,
    monthly_budget_eur: 500.0,
    created_at: '2026-06-30T09:30:00Z',
    expires_at: '2026-12-31T23:59:59Z',
  },
]

// Mock Usage Events
export const mockUsageEvents: UsageEvent[] = [
  {
    id: 'usage_1',
    timestamp: '2026-07-04T10:15:00Z',
    sub_key_id: 'subkey_1',
    user_id: 'user_1',
    model: 'gpt-4o-mini',
    input_tokens: 120,
    output_tokens: 85,
    total_tokens: 205,
    estimated_cost_eur: 0.0012,
    latency_ms: 750,
    status: 'success',
  },
  {
    id: 'usage_2',
    timestamp: '2026-07-04T09:45:00Z',
    sub_key_id: 'subkey_1',
    user_id: 'user_1',
    model: 'gpt-4o-mini',
    input_tokens: 250,
    output_tokens: 180,
    total_tokens: 430,
    estimated_cost_eur: 0.0026,
    latency_ms: 920,
    status: 'success',
  },
  {
    id: 'usage_3',
    timestamp: '2026-07-04T08:30:00Z',
    sub_key_id: 'subkey_2',
    user_id: 'user_2',
    model: 'gpt-4o-mini',
    input_tokens: 180,
    output_tokens: 95,
    total_tokens: 275,
    estimated_cost_eur: 0.0017,
    latency_ms: 650,
    status: 'success',
  },
  {
    id: 'usage_4',
    timestamp: '2026-07-04T07:20:00Z',
    sub_key_id: 'subkey_1',
    user_id: 'user_1',
    model: 'gpt-4-turbo',
    input_tokens: 1500,
    output_tokens: 500,
    total_tokens: 2000,
    estimated_cost_eur: 0.045,
    latency_ms: 1200,
    status: 'success',
  },
]

// Helper functions
export const getTotalTokensUsed = () => {
  return mockUsageEvents.reduce((sum, event) => sum + event.total_tokens, 0)
}

export const getTotalCostEstimated = () => {
  return mockUsageEvents.reduce((sum, event) => sum + event.estimated_cost_eur, 0)
}

export const getActiveKeysCount = () => {
  return mockSubApiKeys.filter((key) => key.status === 'active').length
}

export const getUserUsageEvents = (userId: string) => {
  return mockUsageEvents.filter((event) => event.user_id === userId)
}

export const getUserKeys = (userId: string) => {
  return mockSubApiKeys.filter((key) => key.owner_id === userId)
}
