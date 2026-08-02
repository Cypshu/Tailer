"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

const demoAccounts = [
  {
    label: "Admin",
    email: "organizer@hackathon.dev",
    password: "Hackathon Organizer",
  },
  {
    label: "Team Alpha",
    email: "team_alpha@hackathon.dev",
    password: "Team Alpha",
  },
  {
    label: "Team Beta",
    email: "team_beta@hackathon.dev",
    password: "Team Beta",
  },
];

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const fillDemoAccount = (account: (typeof demoAccounts)[number]) => {
    setEmail(account.email);
    setPassword(account.password);
    setError("");
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await fetch(
        `${apiBaseUrl}/api/auth/login`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        }
      );

      if (!response.ok) {
        setError("Invalid credentials");
        setLoading(false);
        return;
      }

      const data = await response.json();

      // Store token in localStorage
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("user_id", data.user_id);
      localStorage.setItem("user_name", data.name);
      localStorage.setItem("user_role", data.role);

      // Redirect based on role
      if (data.role === "admin") {
        router.push("/admin");
      } else {
        router.push("/user/dashboard");
      }
    } catch {
      setError("An error occurred. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-800">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-lg shadow-xl p-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">TAILER</h1>
          <p className="text-gray-600 mb-8">LLM API Gateway</p>

          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="username"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder:text-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="organizer@hackathon.dev"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder:text-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Hackathon Organizer"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium py-2 rounded-lg transition"
            >
              {loading ? "Logging in..." : "Login"}
            </button>
          </form>

          <div className="mt-8 p-4 bg-blue-50 border border-blue-200 rounded text-sm text-blue-700">
            <p className="font-semibold mb-2">Demo credentials:</p>
            <div className="space-y-3">
              {demoAccounts.map((account) => (
                <div
                  key={account.email}
                  className="rounded-lg border border-blue-200 bg-white p-3 text-gray-900"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold">{account.label}</p>
                      <p className="mt-1 font-mono text-xs text-gray-800">
                        {account.email}
                      </p>
                      <p className="mt-0.5 font-mono text-xs text-gray-800">
                        {account.password}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => fillDemoAccount(account)}
                      className="rounded-md bg-blue-600 px-3 py-1 text-xs font-medium text-white transition hover:bg-blue-700"
                    >
                      Use
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-6 text-center">
            <Link href="/" className="text-blue-600 hover:text-blue-700 text-sm">
              Back to home
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
