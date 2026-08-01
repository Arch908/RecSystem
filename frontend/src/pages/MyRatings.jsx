import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

function extractYear(title) {
  const m = title?.match(/\((\d{4})\)$/)
  return m ? m[1] : ''
}

export default function MyRatings() {
  const [ratings, setRatings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [modal,   setModal]   = useState(null)

  useEffect(() => {
    api.myRatings()
      .then(data => setRatings(data.ratings))
      .catch(e  => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">My Ratings</h1>
        <p className="page-subtitle">
          {ratings.length} movie{ratings.length !== 1 ? 's' : ''} rated
        </p>
      </div>

      {loading &&
        <div style={{ textAlign: 'center', padding: '4rem' }}>
          <div className="spinner" style={{ margin: '0 auto' }} />
        </div>
      }

      {error &&
        <div className="empty-state">
          <div className="empty-icon">⚠️</div>
          <h3>Something went wrong</h3>
          <p>{error}</p>
        </div>
      }

      {!loading && !error && ratings.length > 0 &&
        <>
          <div className="section-label">Rated films</div>
          <table className="ratings-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Year</th>
                <th>Genres</th>
                <th>Your Rating</th>
              </tr>
            </thead>
            <tbody>
              {ratings.map(r => (
                <tr
                  key={r.movie_id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => setModal(r)}
                >
                  <td>{r.title?.replace(/\s*\(\d{4}\)\s*$/, '')}</td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                    {extractYear(r.title)}
                  </td>
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
        </>
      }

      {!loading && !error && ratings.length === 0 &&
        <div className="empty-state">
          <div className="empty-icon">⭐</div>
          <h3>No ratings yet</h3>
          <p>Head to Browse and start rating movies to personalize your feed.</p>
          <Link to="/" className="btn-gold" style={{ display: 'inline-block', marginTop: '1.5rem' }}>
            Browse Movies
          </Link>
        </div>
      }

      {/* Simple movie detail modal */}
      {modal &&
        <div className="modal-backdrop open" onClick={e => { if (e.target === e.currentTarget) setModal(null) }}>
          <div className="modal-panel">
            <button className="modal-close" onClick={() => setModal(null)}>×</button>
            <div className="modal-hero">
              {modal.poster_url
                ? <img className="modal-poster" src={modal.poster_url} alt={modal.title} />
                : <div className="modal-poster-placeholder">🎬</div>
              }
              <div className="modal-meta">
                <div className="modal-year">{extractYear(modal.title)}</div>
                <h2 className="modal-title">{modal.title?.replace(/\s*\(\d{4}\)\s*$/, '')}</h2>
                <div className="modal-genres">
                  {(modal.genres || '').split('|').filter(Boolean).map(g => (
                    <span key={g} className="genre-pill">{g}</span>
                  ))}
                </div>
                <p className="modal-overview">{modal.overview || 'No description available.'}</p>
                <div className="modal-stats">
                  <div className="modal-stat">
                    <label>Your Rating</label>
                    <span className="gold">{modal.rating}★</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      }
    </div>
  )
}
