'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { FiHome, FiUsers, FiKey, FiLogOut } from 'react-icons/fi'

export function Navigation() {
  const pathname = usePathname()

  const isAdmin = pathname.startsWith('/admin')
  const isUser = pathname.startsWith('/user')

  const adminLinks = [
    { href: '/admin', label: 'Dashboard', icon: FiHome },
    { href: '/admin/users', label: 'Users', icon: FiUsers },
    { href: '/admin/keys', label: 'API Keys', icon: FiKey },
  ]

  const userLinks = [{ href: '/user/dashboard', label: 'My Dashboard', icon: FiHome }]

  const links = isAdmin ? adminLinks : isUser ? userLinks : []

  return (
    <nav className="bg-gradient-to-r from-blue-600 to-blue-700 shadow-lg">
      <div className="max-w-7xl mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/" className="text-white font-bold text-2xl">
              TAILER
            </Link>

            <div className="flex gap-6">
              {links.map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  className={`flex items-center gap-2 px-3 py-2 rounded-md transition-colors ${
                    pathname === href
                      ? 'bg-blue-800 text-white'
                      : 'text-blue-100 hover:text-white hover:bg-blue-700'
                  }`}
                >
                  <Icon className="text-lg" />
                  <span>{label}</span>
                </Link>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-4">
            {isAdmin ? (
              <button className="text-blue-100 hover:text-white text-sm flex items-center gap-2">
                <FiLogOut />
                Logout
              </button>
            ) : isUser ? (
              <button className="text-blue-100 hover:text-white text-sm flex items-center gap-2">
                <FiLogOut />
                Logout
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </nav>
  )
}
