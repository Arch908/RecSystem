import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { api } from '../api'
import MovieCard from '../components/MovieCard'

function extractYear(title) {
  const m = title?.match(/\((\d{4})\)$/)
  return m ? m[1] : ''
}

export default function Profile() {
  const { logout }          = useAuth()
  const navigate            = useNavigate()
  const [data,    setData]  = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError] = useState(null)

  useEffect(() => {
    api.profile()
      .then(d  => setData(d))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '4rem' }}>
      <div className="spinner" style={{ margin: '0 auto' }} />
    </div>
  )

  if (error) return (
    <div className="empty-state">
      <div className="empty-icon">⚠️</div>
      <h3>Something went wrong</h3>
      <p>{error}</p>
    </div>
  )

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">My Profile</h1>
        <p className="page-subtitle">{data.username}</p>
      </div>

      {/* Stats chips */}
      <div className="stats-row" style={{ marginBottom: '2.5rem' }}>
        <div className="stat-chip">
          <strong>{data.ratings.length}</strong>
          movies rated
        </div>
        <div className="stat-chip">
          <strong>{data.watchlist.length}</strong>
          in watchlist
        </div>
        <div className="stat-chip">
          <strong>{data.avg_rating ?? '—'}</strong>
          avg rating
        </div>
      </div>

      {/* Recent ratings */}
      <div className="section-label">Recent ratings</div>
      {data.ratings.length > 0
        ? <>
            <table className="ratings-table" style={{ marginBottom: '2rem' }}>
              <thead>
                <tr><th>Title</th><th>Genres</th><th>Rating</th></tr>
              </thead>
              <tbody>
                {data.ratings.slice(0, 10).map(r => (
                  <tr key={r.movie_id}>
                    <td>{r.title?.replace(/\s*\(\d{4}\)\s*$/, '')}</td>
                    <td>
                      <span className="genre-tag">
                        {r.genres ? r.genres.replace(/\|/g, ' · ') : '—'}
                      </span>
                    </td>
                    <td><span className="rating-star">{r.rating} ★</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.ratings.length > 10 &&
              <Link to="/my-ratings" className="page-btn"
                    style={{ display: 'inline-block', marginBottom: '2rem', textDecoration: 'none' }}>
                View all {data.ratings.length} ratings →
              </Link>
            }
          </>
        : <p style={{ color: 'var(--text-muted)', marginBottom: '2rem' }}>No ratings yet.</p>
      }

      {/* Watchlist preview */}
      <div className="section-label">Watchlist preview</div>
      {data.watchlist.length > 0
        ? <>
            <div className="movies-grid" style={{ marginBottom: '2rem' }}>
              {data.watchlist.slice(0, 6).map(m => (
                <MovieCard
                  key={m.movie_id}
                  movie={{ ...m, in_watchlist: true }}
                />
              ))}
            </div>
            <Link to="/watchlist" className="page-btn"
                  style={{ display: 'inline-block', textDecoration: 'none' }}>
              View full watchlist →
            </Link>
          </>
        : <p style={{ color: 'var(--text-muted)' }}>Nothing in watchlist yet.</p>
      }

      {/* Sign out */}
      <div style={{ marginTop: '3rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border)' }}>
        <button
          onClick={handleLogout}
          className="page-btn"
          style={{ color: 'var(--red)', borderColor: 'rgba(224,82,82,0.3)', background: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
        >
          Sign out
        </button>
      </div>
    </div>
  )
}
