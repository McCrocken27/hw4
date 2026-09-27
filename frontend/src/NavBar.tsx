import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from './auth'
import { useCart } from './cart'

const pageLinks = [
  { to: '/', label: 'Home' },
  { to: '/products', label: 'Products' },
  { to: '/about', label: 'About Us' },
]

const guestLinks = [
  { to: '/login', label: 'Log In' },
  { to: '/create-account', label: 'Create Account' },
]

export default function NavBar() {
  const { user, loading, logout } = useAuth()
  const { count } = useCart()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/')
  }

  return (
    <nav className="navbar">
      <NavLink to="/" className="brand">
        Campus Customs
      </NavLink>
      <ul>
        {pageLinks.map((link) => (
          <li key={link.to}>
            <NavLink to={link.to} end>
              {link.label}
            </NavLink>
          </li>
        ))}
        {!loading && !user &&
          guestLinks.map((link) => (
            <li key={link.to}>
              <NavLink to={link.to} end>
                {link.label}
              </NavLink>
            </li>
          ))}
        {user && (
          <>
            <li className="nav-greeting">Hi, {user.first_name}</li>
            <li>
              <button type="button" className="nav-button" onClick={handleLogout}>
                Log Out
              </button>
            </li>
          </>
        )}
        <li>
          <NavLink to="/cart" className="nav-cart" aria-label={`Cart, ${count} items`}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M3 4h2l2.4 11.2a1 1 0 0 0 1 .8h9.2a1 1 0 0 0 1-.8L20 8H6.2" />
              <circle cx="9.5" cy="20" r="1.3" />
              <circle cx="17" cy="20" r="1.3" />
            </svg>
            Cart
            {count > 0 && <span className="cart-badge">{count}</span>}
          </NavLink>
        </li>
      </ul>
    </nav>
  )
}
