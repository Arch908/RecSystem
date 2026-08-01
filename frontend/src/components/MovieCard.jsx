import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

const RATINGS = [0.5,1,1.5,2,2.5,3,3.5,4,4.5,5]

// ── Skeleton card ──────────────────────────────────────────────────────────

export function MovieCardSkeleton() {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', overflow: 'hidden',
    }}>
      <div style={{
        width: '100%', aspectRatio: '2/3',
        background: 'linear-gradient(110deg, var(--surface2) 30%, var(--surface) 50%, var(--surface2) 70%)',
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.6s ease-in-out infinite',
      }} />
      <div style={{ padding: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <div style={{ height: 12, width: '80%', background: 'var(--surface2)', borderRadius: 4, animation: 'shimmer 1.6s ease-in-out infinite' }} />
        <div style={{ height: 10, width: '55%', background: 'var(--surface2)', borderRadius: 4, animation: 'shimmer 1.6s ease-in-out infinite 0.1s' }} />
        <div style={{ height: 28, background: 'var(--surface2)', borderRadius: 6, marginTop: '0.25rem', animation: 'shimmer 1.6s ease-in-out infinite 0.2s' }} />
      </div>
      <style>{`
        @keyframes shimmer {
          0%   { background-position: 200% 0 }
          100% { background-position: -200% 0 }
        }
      `}</style>
    </div>
  )
}

// ── Main card ──────────────────────────────────────────────────────────────

export default function MovieCard({ movie, onRated, onWatchlist, onNotInterested, onUndoNotInterested, showRank = false, showScore = false, showUndoNotInterested = false }) {
  const navigate = useNavigate()
  const [rating,      setRating]      = useState(movie.user_rating || '')
  const [inWatchlist, setInWatchlist] = useState(movie.in_watchlist || false)
  const [saving,      setSaving]      = useState(false)
  const [toast,       setToast]       = useState(null)
  const [hovered,     setHovered]     = useState(false)

  const genres  = (movie.genres || '').split('|').filter(Boolean)
  const year    = movie.release_date?.slice(0, 4)
               || movie.title?.match(/\((\d{4})\)$/)?.[1] || ''
  const title   = movie.title?.replace(/\s*\(\d{4}\)\s*$/, '') || ''
  const overview = movie.overview || ''

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2200)
  }

  async function submitRating(val) {
    if (!val) return
    setSaving(true)
    try {
      await api.rate(movie.movie_id, parseFloat(val))
      setRating(parseFloat(val))
      showToast(`Saved: ${val}★`)
      onRated?.(movie.movie_id, parseFloat(val))
    } catch {
      showToast('Could not save rating', 'error')
    } finally {
      setSaving(false)
    }
  }


  async function markNotInterested(e) {
    e.stopPropagation()
    if (!window.confirm('Hide this movie from future recommendations?')) return
    try {
      await api.notInterested(movie.movie_id)
      showToast('Removed from your recommendations', 'info')
      onNotInterested?.(movie.movie_id)
    } catch {
      showToast('Could not save feedback', 'error')
    }
  }

  async function undoNotInterested(e) {
    e.stopPropagation()
    try {
      await api.undoNotInterested(movie.movie_id)
      showToast('Movie restored to future recommendations', 'success')
      onUndoNotInterested?.(movie.movie_id)
    } catch {
      showToast('Could not restore movie', 'error')
    }
  }

  async function toggleWatchlist(e) {
    e.stopPropagation()
    try {
      if (inWatchlist) {
        await api.watchlistRemove(movie.movie_id)
        setInWatchlist(false)
        showToast('Removed from watchlist', 'info')
      } else {
        await api.watchlistAdd(movie.movie_id)
        setInWatchlist(true)
        showToast('Added to watchlist!')
      }
      onWatchlist?.(movie.movie_id, !inWatchlist)
    } catch {
      showToast('Could not update watchlist', 'error')
    }
  }

  return (
    <>
      <div
        className="movie-card"
        onClick={() => navigate(`/movie/${movie.movie_id}`)}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{ position: 'relative', cursor: 'pointer' }}
      >
        {/* Poster + hover overlay + badges */}
        <div style={{ position: 'relative', overflow: 'hidden' }}>
          {movie.poster_url
            ? <img className="movie-poster" src={movie.poster_url} alt={title} loading="lazy"
                style={{ transition: 'transform 0.4s ease', transform: hovered ? 'scale(1.05)' : 'scale(1)', display: 'block' }}
              />
            : <div className="movie-poster-placeholder"><span className="poster-icon">🎬</span></div>
          }

          {/* Badges sit above hover overlay */}
          {showRank && movie.rank &&
            <span className="rank-badge" style={{ zIndex: 3 }}>#{movie.rank}</span>
          }
          {showScore && movie.score != null && (
            <>
              <span className="rec-score" style={{ zIndex: 3, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.15rem', lineHeight: 1.3 }}>
                {movie.display_score
                  ? movie.display_score.split(' · ').map((part, i) => <span key={i}>{part}</span>)
                  : <span>{movie.score.toFixed(2)}</span>
                }
              </span>
              <span className={`rec-method rec-method-${movie.method}`} style={{ zIndex: 3 }}>
                {movie.method === 'collaborative' ? 'collab' : movie.method === 'content' ? 'content' : 'both'}
              </span>
            </>
          )}
          {inWatchlist && !showScore &&
            <span className="wl-saved-badge" style={{ zIndex: 3 }}>🔖</span>
          }

          {overview && (
            <div style={{
              position: 'absolute', inset: 0, zIndex: 2,
              background: 'linear-gradient(to top, rgba(0,0,0,0.96) 0%, rgba(0,0,0,0.75) 55%, rgba(0,0,0,0.15) 100%)',
              display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
              padding: '1rem 0.85rem 0.75rem',
              opacity: hovered ? 1 : 0,
              transition: 'opacity 0.3s ease',
              pointerEvents: 'none',
            }}>
              <p style={{
                fontSize: '0.72rem', color: 'rgba(255,255,255,0.85)',
                lineHeight: 1.55, margin: 0,
                display: '-webkit-box', WebkitLineClamp: 6,
                WebkitBoxOrient: 'vertical', overflow: 'hidden',
              }}>
                {overview}
              </p>
              <span style={{ marginTop: '0.5rem', fontSize: '0.68rem', color: 'var(--gold)', fontWeight: 500 }}>
                View details →
              </span>
            </div>
          )}
        </div>

        {/* Card body */}
        <div className="movie-info">
          <div className="movie-title-card">{title}</div>
          <div className="movie-genres-card">
            {genres.length ? genres.join(' · ') : 'Uncategorized'}
          </div>

          <div className="movie-meta-row">
            {movie.runtime &&
              <span style={{ fontSize: '0.67rem', color: 'var(--text-dim)' }}>
                🕐 {Math.floor(movie.runtime / 60)}h {movie.runtime % 60}m
              </span>
            }
            {movie.imdb_rating &&
              <span style={{ fontSize: '0.67rem', color: 'rgba(245,197,24,0.75)' }}>
                ⭐ {Number(movie.imdb_rating).toFixed(1)}
              </span>
            }
          </div>

          <div className="movie-stats-slot">
            {movie.rating_count > 0 &&
              <div className="trending-stats">
                <span className="ts-item">⭐ {(movie.avg_rating || 0).toFixed(1)}</span>
                <span className="ts-item">👥 {movie.rating_count}</span>
              </div>
            }
          </div>

          {showScore &&
            <div
              className="movie-explanation-slot"
              onClick={e => e.stopPropagation()}
            >
              {movie.explanation && <p>{movie.explanation}</p>}
            </div>
          }

          {showScore && (
            <button
              onClick={markNotInterested}
              title="Hide this movie from future recommendations"
              style={{
                width: '100%', marginBottom: '0.28rem', padding: '0.45rem 0.6rem',
                borderRadius: 6, border: '1px solid rgba(224,82,82,0.28)',
                background: 'rgba(224,82,82,0.08)', color: '#d98a8a',
                cursor: 'pointer', fontSize: '0.72rem', fontFamily: 'var(--font-body)',
              }}
            >
              👎 Not Interested
            </button>
          )}


          {showUndoNotInterested && (
            <button
              onClick={undoNotInterested}
              title="Allow this movie to appear in recommendations again"
              style={{
                width: '100%', marginBottom: '0.28rem', padding: '0.45rem 0.6rem',
                borderRadius: 6, border: '1px solid rgba(100,220,154,0.3)',
                background: 'rgba(100,220,154,0.08)', color: '#64dc9a',
                cursor: 'pointer', fontSize: '0.72rem', fontFamily: 'var(--font-body)',
              }}
            >
              ↩ Restore to Recommendations
            </button>
          )}

          <div className="card-actions" onClick={e => e.stopPropagation()}>
            <div className="star-rating">
              <select className="rating-select" value={rating} onChange={e => setRating(e.target.value)}>
                <option value="">Rate…</option>
                {RATINGS.map(r => <option key={r} value={r}>{r}★</option>)}
              </select>
              <button
                className={`rate-btn ${rating ? 'rate-btn-saved' : ''}`}
                disabled={saving}
                onClick={() => submitRating(rating)}
              >
                {saving ? '…' : rating ? `✓ ${rating}★` : 'Rate'}
              </button>
            </div>
            <button
              className={`wl-btn ${inWatchlist ? 'wl-active' : ''}`}
              title={inWatchlist ? 'Remove from watchlist' : 'Add to watchlist'}
              onClick={toggleWatchlist}
            >
              {inWatchlist ? '🔖' : '＋'}
            </button>
          </div>
        </div>

        {toast && (
          <div style={{
            position: 'fixed', bottom: '2rem', right: '2rem', zIndex: 9999,
            padding: '0.65rem 1.25rem', borderRadius: '10px', fontSize: '0.875rem',
            backdropFilter: 'blur(12px)',
            background: toast.type === 'error' ? 'rgba(224,82,82,0.15)' : toast.type === 'info' ? 'rgba(212,175,55,0.12)' : 'rgba(82,192,122,0.15)',
            border: `1px solid ${toast.type === 'error' ? 'rgba(224,82,82,0.35)' : toast.type === 'info' ? 'rgba(212,175,55,0.35)' : 'rgba(82,192,122,0.35)'}`,
            color: toast.type === 'error' ? '#e05252' : toast.type === 'info' ? '#d4af37' : '#52c07a',
          }}>
            {toast.msg}
          </div>
        )}
      </div>
    </>
  )
}