import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function LogIn() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError((err as Error).message)
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="auth-card">
      <h1>Log In</h1>
      <form onSubmit={handleSubmit} noValidate>
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            maxLength={254}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={submitting || !email || !password}>
          {submitting ? 'Logging in…' : 'Log In'}
        </button>
      </form>
      <p className="auth-switch">
        New to Campus Customs? <Link to="/create-account">Create an account</Link>
      </p>
    </section>
  )
}
