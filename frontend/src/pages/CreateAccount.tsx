import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { SignupForm } from '../api'
import { useAuth } from '../auth'

const EMPTY: SignupForm = {
  first_name: '',
  last_name: '',
  email: '',
  password: '',
  confirm_password: '',
}

const FIELDS: {
  name: keyof SignupForm
  label: string
  type: string
  autoComplete: string
  maxLength: number
}[] = [
  { name: 'first_name', label: 'First Name', type: 'text', autoComplete: 'given-name', maxLength: 50 },
  { name: 'last_name', label: 'Last Name', type: 'text', autoComplete: 'family-name', maxLength: 50 },
  { name: 'email', label: 'Email', type: 'email', autoComplete: 'email', maxLength: 254 },
  { name: 'password', label: 'Password', type: 'password', autoComplete: 'new-password', maxLength: 128 },
  { name: 'confirm_password', label: 'Confirm Password', type: 'password', autoComplete: 'new-password', maxLength: 128 },
]

// Quick checks so shoppers see mistakes right away. The server repeats every check.
function validate(form: SignupForm): string {
  if (FIELDS.some((f) => !form[f.name].trim())) return 'Please fill in every field'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) return 'Please enter a valid email address'
  if (form.password.length < 8) return 'Password must be at least 8 characters'
  if (!/[A-Za-z]/.test(form.password) || !/\d/.test(form.password))
    return 'Password must include at least one letter and one number'
  if (form.password !== form.confirm_password) return 'Passwords do not match'
  return ''
}

export default function CreateAccount() {
  const { signup } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState<SignupForm>(EMPTY)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const problem = validate(form)
    setError(problem)
    if (problem) return

    setSubmitting(true)
    try {
      await signup(form)
      navigate('/')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="auth-card">
      <h1>Create Account</h1>
      <form onSubmit={handleSubmit} noValidate>
        {FIELDS.map((f) => (
          <label key={f.name}>
            {f.label}
            <input
              type={f.type}
              autoComplete={f.autoComplete}
              maxLength={f.maxLength}
              value={form[f.name]}
              onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}
              required
            />
          </label>
        ))}
        <p className="form-hint">At least 8 characters, with a letter and a number.</p>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create Account'}
        </button>
      </form>
      <p className="auth-switch">
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </section>
  )
}
