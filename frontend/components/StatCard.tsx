import { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: string | number
  icon?: ReactNode
  trend?: 'up' | 'down' | 'neutral'
  trendValue?: string
}

export function StatCard({
  label,
  value,
  icon,
  trend = 'neutral',
  trendValue,
}: StatCardProps) {
  const trendColor =
    trend === 'up' ? 'text-green-600' : trend === 'down' ? 'text-red-600' : 'text-gray-600'

  return (
    <div className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-gray-600 text-sm font-medium">{label}</p>
          <p className="text-2xl font-bold text-gray-900 mt-2">{value}</p>
          {trendValue && <p className={`text-xs mt-2 ${trendColor}`}>{trendValue}</p>}
        </div>
        {icon && <div className="text-3xl opacity-20">{icon}</div>}
      </div>
    </div>
  )
}
