import { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'

export default function Navbar() {
  const { user, logout } = useAuth()
  const location          = useLocation()
  const navigate          = useNavigate()
  const [dropOpen, setDropOpen]     = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  // Close both menus any time the logged-in user changes
  useEffect(() => {
    setDropOpen(false)
    setMobileOpen(false)
  }, [user])

  // Close the mobile menu on every route change
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  const isActive = (path) => location.pathname === path ? 'active' : ''
  const closeMenus = () => { setDropOpen(false); setMobileOpen(false) }

  async function handleLogout() {
    closeMenus()
    await logout()
    navigate('/login')
  }

  return (
    <nav className="site-nav">
      <div className="nav-inner">
        <Link className="nav-logo" to="/" onClick={closeMenus}>
          <span className="logo-icon">▶</span>
          <span className="logo-text">MovieSpan</span>
        </Link>

        {user && (
          <button
            className="nav-hamburger"
            aria-label="Toggle menu"
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen(o => !o)}
          >
            <span /><span /><span />
          </button>
        )}

        <div className={`nav-links ${mobileOpen ? 'nav-links-open' : ''}`}>
          {user ? (
            <>
              <Link to="/"            className={`nav-link ${isActive('/')}`} onClick={closeMenus}>Browse</Link>
              <Link to="/trending"    className={`nav-link ${isActive('/trending')}`} onClick={closeMenus}>🔥 Trending</Link>
              <Link to="/recommendations" className={`nav-link ${isActive('/recommendations')}`} onClick={closeMenus}>
                <span className="for-you-dot"></span>For You
              </Link>
              <Link to="/watchlist"   className={`nav-link ${isActive('/watchlist')}`} onClick={closeMenus}>🔖 Watchlist</Link>
              <Link to="/my-ratings"  className={`nav-link ${isActive('/my-ratings')}`} onClick={closeMenus}>My Ratings</Link>

              {user.is_admin &&
                <Link to="/admin"
                  className={`nav-link ${isActive('/admin')}`}
                  onClick={closeMenus}
                  style={{ color: '#e05252', border: '1px solid rgba(224,82,82,0.25)', borderRadius: '6px', padding: '0.4rem 0.9rem' }}>
                  ⚙ Admin
                </Link>
              }

              <div className="nav-divider" />

              <div className="user-menu" id="userMenu" style={{ position: 'relative' }}>
                <button className="nav-user-btn" onClick={() => setDropOpen(o => !o)}>
                  <span className="avatar">{user.username[0].toUpperCase()}</span>
                  <span className="nav-username">{user.username}</span>
                  <span className="chevron">▾</span>
                </button>
                {dropOpen &&
                  <div className="user-dropdown open">
                    <Link to="/profile"    className="dropdown-item" onClick={closeMenus}><span className="di-icon">👤</span> My Profile</Link>
                    <Link to="/my-ratings" className="dropdown-item" onClick={closeMenus}><span className="di-icon">⭐</span> My Ratings</Link>
                    <Link to="/watchlist"  className="dropdown-item" onClick={closeMenus}><span className="di-icon">🔖</span> Watchlist</Link>
                    <Link to="/not-interested" className="dropdown-item" onClick={closeMenus}><span className="di-icon">👎</span> Not Interested</Link>
                    {user.is_admin && <>
                      <div className="dropdown-divider" />
                      <Link to="/admin" className="dropdown-item" style={{ color: '#e05252' }} onClick={closeMenus}><span className="di-icon">⚙</span> Admin Panel</Link>
                    </>}
                    <div className="dropdown-divider" />
                    <button className="dropdown-item dropdown-item-danger" style={{ width: '100%', background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer' }} onClick={handleLogout}>
                      <span className="di-icon">→</span> Sign Out
                    </button>
                  </div>
                }
              </div>
            </>
          ) : (
            <>
              <Link to="/login"    className="nav-link" onClick={closeMenus}>Login</Link>
              <Link to="/register" className="btn-gold" onClick={closeMenus}>Get Started</Link>
            </>
          )}
        </div>
      </div>
    </nav>
  )
}