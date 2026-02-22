import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import Logo from '../components/Logo'

const GRID_STYLE: React.CSSProperties = {
  backgroundImage: [
    'linear-gradient(rgba(59,130,246,0.08) 1px, transparent 1px)',
    'linear-gradient(90deg, rgba(59,130,246,0.08) 1px, transparent 1px)',
  ].join(','),
  backgroundSize: '48px 48px',
}

function BrandPanel() {
  return (
    <div className="relative lg:w-[58%] flex flex-col items-center justify-center px-10 py-14 lg:py-0 lg:min-h-screen overflow-hidden bg-gradient-to-br from-[#0b1d3e] via-[#061120] to-[#030712]">
      <div className="absolute inset-0 opacity-100" style={GRID_STYLE} />
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[480px] h-[220px] rounded-full bg-blue-500/10 blur-[90px]" />
      <div className="absolute top-0 right-0 w-64 h-64 rounded-full bg-blue-600/5 blur-[80px]" />

      <div className="relative z-10 flex flex-col items-center text-center gap-7 max-w-md">
        <Logo size="xl" />

        <div>
          <p className="text-gray-300 text-lg leading-relaxed">
            AI-powered technical analysis for smarter swing trading decisions.
          </p>
        </div>

        <div className="flex items-center gap-5 mt-2">
          {[
            { value: '6Y',  label: 'Historical data' },
            { value: '12+', label: 'TA signals' },
            { value: 'AI',  label: 'Synthesis' },
          ].map(({ value, label }, i, arr) => (
            <div key={label} className="flex items-center gap-5">
              <div className="text-center">
                <div className="text-xl font-bold text-blue-400 tabular-nums">{value}</div>
                <div className="text-xs text-gray-500 mt-0.5">{label}</div>
              </div>
              {i < arr.length - 1 && <div className="w-px h-8 bg-white/10" />}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function SignupPage() {
  const { login: authLogin } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }

    setIsLoading(true)
    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data?.detail ?? 'Registration failed')
      }
      await authLogin(username.trim(), password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      {/* Left: brand */}
      <BrandPanel />

      {/* Right: form */}
      <div className="lg:w-[42%] flex flex-col items-center justify-center px-6 py-12 lg:px-16 lg:min-h-screen">
        <div className="w-full max-w-sm">

          {/* Mobile-only logo */}
          <div className="flex justify-center mb-8 lg:hidden">
            <Logo size="lg" />
          </div>

          <div className="mb-8">
            <h1 className="text-2xl font-bold text-white tracking-tight">Create your account</h1>
            <p className="mt-1.5 text-sm text-gray-500">Start analyzing markets with AI assistance</p>
          </div>

          {/* Card */}
          <div className="glass rounded-2xl p-7 border border-white/10 shadow-xl">
            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-400 uppercase tracking-widest">
                  Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  required
                  minLength={3}
                  placeholder="At least 3 characters"
                  className="
                    px-4 py-3 rounded-xl bg-white/5 border border-white/12
                    text-gray-100 placeholder-gray-600 text-sm
                    focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20
                    hover:border-white/20 transition-all
                  "
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-400 uppercase tracking-widest">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                  minLength={8}
                  placeholder="At least 8 characters"
                  className="
                    px-4 py-3 rounded-xl bg-white/5 border border-white/12
                    text-gray-100 placeholder-gray-600 text-sm
                    focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20
                    hover:border-white/20 transition-all
                  "
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-gray-400 uppercase tracking-widest">
                  Confirm Password
                </label>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  autoComplete="new-password"
                  required
                  placeholder="Re-enter your password"
                  className="
                    px-4 py-3 rounded-xl bg-white/5 border border-white/12
                    text-gray-100 placeholder-gray-600 text-sm
                    focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20
                    hover:border-white/20 transition-all
                  "
                />
              </div>

              {error && (
                <div className="flex items-start gap-2.5 text-sm text-red-400 bg-red-500/8 border border-red-500/20 rounded-xl px-4 py-3">
                  <span className="shrink-0 mt-px">⚠</span>
                  <span>{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={isLoading || !username.trim() || !password || !confirm}
                className="
                  mt-1 w-full py-3 rounded-xl font-semibold text-sm tracking-wide
                  bg-blue-600 hover:bg-blue-500 active:bg-blue-700
                  text-white transition-all duration-150
                  disabled:opacity-40 disabled:cursor-not-allowed
                  shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30
                "
              >
                {isLoading ? 'Creating account…' : 'Create account'}
              </button>
            </form>
          </div>

          <p className="text-center text-sm text-gray-600 mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
