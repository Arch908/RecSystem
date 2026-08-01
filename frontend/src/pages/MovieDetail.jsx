import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../api'
import MovieCard from '../components/MovieCard'

const RATINGS = [0.5,1,1.5,2,2.5,3,3.5,4,4.5,5]

// ── Helpers ────────────────────────────────────────────────────────────────

function formatRuntime(mins) {
  if (!mins) return null
  const h = Math.floor(mins / 60), m = mins % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function formatLanguage(code) {
  if (!code) return null
  try { return new Intl.DisplayNames(['en'], { type: 'language' }).of(code) }
  catch { return code.toUpperCase() }
}

function formatDate(d) {
  if (!d) return null
  try { return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }) }
  catch { return d }
}

// ── Sub-components ─────────────────────────────────────────────────────────

function StatBadge({ label, value, accent }) {
  if (!value) return null
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: '0.2rem',
      background: 'var(--surface2)', border: `1px solid ${accent || 'var(--border)'}`,
      borderRadius: 'var(--radius)', padding: '0.6rem 1rem',
    }}>
      <span style={{ fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)' }}>{label}</span>
      <span style={{ fontSize: '0.95rem', fontWeight: 600, color: accent || 'var(--text)' }}>{value}</span>
    </div>
  )
}

function CastPill({ name }) {
  return (
    <div style={{
      background: 'var(--surface2)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '0.5rem 0.85rem',
      fontSize: '0.8rem', color: 'var(--text-muted)',
      transition: 'border-color 0.2s, color 0.2s', cursor: 'default',
    }}
      onMouseOver={e => { e.currentTarget.style.borderColor = 'var(--border-gold)'; e.currentTarget.style.color = 'var(--text)' }}
      onMouseOut={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-muted)' }}
    >
      {name}
    </div>
  )
}

function SectionHeading({ children }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '0.75rem',
      fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.12em',
      color: 'var(--gold)', fontWeight: 500, marginBottom: '1rem',
    }}>
      {children}
      <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
    </div>
  )
}

function TrailerEmbed({ trailerKey, title }) {
  const [open, setOpen] = useState(false)
  if (!trailerKey) return null
  return (
    <div>
      <SectionHeading>Trailer</SectionHeading>
      {!open ? (
        <button onClick={() => setOpen(true)} style={{
          display: 'flex', alignItems: 'center', gap: '0.75rem',
          background: 'rgba(255,50,50,0.08)', border: '1px solid rgba(255,50,50,0.25)',
          borderRadius: 'var(--radius-lg)', padding: '0',
          cursor: 'pointer', fontFamily: 'var(--font-body)',
          overflow: 'hidden', width: '100%', textAlign: 'left',
          transition: 'border-color 0.2s',
        }}
          onMouseOver={e => e.currentTarget.style.borderColor = 'rgba(255,50,50,0.5)'}
          onMouseOut={e => e.currentTarget.style.borderColor = 'rgba(255,50,50,0.25)'}
        >
          <img
            src={`https://img.youtube.com/vi/${trailerKey}/hqdefault.jpg`}
            alt="Trailer thumbnail"
            style={{ width: 160, height: 90, objectFit: 'cover', flexShrink: 0 }}
          />
          <div style={{ padding: '0 1rem', flex: 1 }}>
            <div style={{ color: '#ff4444', fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.2rem' }}>
              ▶ Watch Trailer
            </div>
            <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>{title}</div>
          </div>
        </button>
      ) : (
        <div style={{
          position: 'relative', paddingBottom: '56.25%', height: 0,
          borderRadius: 'var(--radius-lg)', overflow: 'hidden',
          border: '1px solid var(--border)',
        }}>
          <iframe
            src={`https://www.youtube.com/embed/${trailerKey}?autoplay=1`}
            title={`${title} Trailer`}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', border: 'none' }}
          />
        </div>
      )}
    </div>
  )
}

// ── Skeleton ───────────────────────────────────────────────────────────────

function DetailSkeleton() {
  return (
    <div style={{ animation: 'pulse 1.5s ease-in-out infinite' }}>
      <style>{`
        @keyframes pulse {
          0%,100% { opacity: 1 }
          50% { opacity: 0.4 }
        }
      `}</style>
      {/* backdrop placeholder */}
      <div style={{ height: 360, background: 'var(--surface)', borderRadius: 'var(--radius-lg)', marginBottom: '2rem' }} />
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: '2.5rem' }}>
        <div style={{ aspectRatio: '2/3', background: 'var(--surface2)', borderRadius: 'var(--radius-lg)' }} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {[200, 120, 300, 80, 80, 80].map((w, i) => (
            <div key={i} style={{ height: i === 0 ? 40 : 16, width: w, background: 'var(--surface2)', borderRadius: 6 }} />
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function MovieDetail() {
  const { id }        = useParams()
  const navigate      = useNavigate()
  const [movie, setMovie]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [rating, setRating]   = useState('')
  const [inWatchlist, setInWatchlist] = useState(false)
  const [saving, setSaving]   = useState(false)
  const [toast, setToast]     = useState(null)
  const [similar, setSimilar] = useState([])
  const [similarLoading, setSimilarLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.get(`/api/movies/${id}`),
      api.similarMovies(id, 12).catch(() => ({ movies: [] })),
    ])
      .then(([data, similarData]) => {
        setMovie(data.movie)
        setRating(data.movie.user_rating || '')
        setInWatchlist(data.movie.in_watchlist || false)
        setSimilar(similarData.movies || [])
      })
      .catch(e => setError(e.message))
      .finally(() => { setLoading(false); setSimilarLoading(false) })
  }, [id])

  function showToast(msg, type = 'success') {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 2500)
  }

  async function submitRating() {
    if (!rating) return
    setSaving(true)
    try {
      await api.rate(parseInt(id), parseFloat(rating))
      showToast(`Rated ${rating}★`)
    } catch { showToast('Could not save', 'error') }
    finally { setSaving(false) }
  }

  async function toggleWatchlist() {
    try {
      if (inWatchlist) {
        await api.watchlistRemove(parseInt(id))
        setInWatchlist(false)
        showToast('Removed from watchlist', 'info')
      } else {
        await api.watchlistAdd(parseInt(id))
        setInWatchlist(true)
        showToast('Added to watchlist!')
      }
    } catch { showToast('Could not update watchlist', 'error') }
  }

  if (loading) return (
    <div className="main-content" style={{ maxWidth: 1100 }}>
      <DetailSkeleton />
    </div>
  )

  if (error || !movie) return (
    <div className="main-content">
      <div className="empty-state">
        <div className="empty-icon">⚠️</div>
        <h3>Movie not found</h3>
        <p>{error || 'This movie could not be loaded.'}</p>
        <button className="btn-gold" style={{ border: 'none', cursor: 'pointer', marginTop: '1rem' }} onClick={() => navigate(-1)}>
          ← Go Back
        </button>
      </div>
    </div>
  )

  const title  = movie.title?.replace(/\s*\(\d{4}\)\s*$/, '') || ''
  const year   = movie.release_date?.slice(0, 4) || movie.title?.match(/\((\d{4})\)$/)?.[1] || ''
  const genres = (movie.genres || '').split('|').filter(Boolean)
  const cast   = movie.cast ? movie.cast.split(',').map(s => s.trim()).filter(Boolean) : []

  return (
    <div className="movie-detail-page">

      {/* ── Back nav ── */}
      <button onClick={() => navigate(-1)} style={{
        display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
        background: 'none', border: 'none', color: 'var(--text-muted)',
        fontSize: '0.875rem', cursor: 'pointer', fontFamily: 'var(--font-body)',
        padding: '1.5rem 0', transition: 'color 0.2s',
      }}
        onMouseOver={e => e.currentTarget.style.color = 'var(--text)'}
        onMouseOut={e => e.currentTarget.style.color = 'var(--text-muted)'}
      >
        ← Back
      </button>

      {/* ── Cinematic backdrop ── */}
      {movie.poster_url && (
        <div className="movie-detail-backdrop" style={{
          position: 'relative', height: 340, borderRadius: 'var(--radius-lg)',
          overflow: 'hidden', marginBottom: '2.5rem',
        }}>
          {/* blurred poster as backdrop */}
          <img src={movie.poster_url} alt=""
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', filter: 'blur(32px) saturate(1.4) brightness(0.35)', transform: 'scale(1.1)' }}
          />
          {/* gradient overlay */}
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(10,10,10,0.1) 0%, rgba(10,10,10,0.85) 100%)' }} />
          {/* Centered title in backdrop */}
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', padding: '2rem', textAlign: 'center' }}>
            <h1 style={{
              fontFamily: 'var(--font-display)', fontSize: 'clamp(1.8rem, 5vw, 3rem)',
              fontWeight: 700, color: '#fff', margin: 0, lineHeight: 1.1,
              textShadow: '0 2px 20px rgba(0,0,0,0.8)',
            }}>{title}</h1>
            {year && <span style={{ color: 'var(--gold)', fontSize: '0.9rem', marginTop: '0.35rem', letterSpacing: '0.08em' }}>{year}</span>}
          </div>
        </div>
      )}

      {/* ── Main layout: poster + content ── */}
      <div className="movie-detail-layout">

        {/* ── Left column: poster + actions ── */}
        <div className="movie-detail-poster-col">
          {movie.poster_url
            ? <img src={movie.poster_url} alt={title}
                style={{ width: '100%', aspectRatio: '2/3', objectFit: 'cover', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-card)', display: 'block' }}
              />
            : <div style={{ width: '100%', aspectRatio: '2/3', background: 'var(--surface)', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '3rem' }}>🎬</div>
          }

          {/* IMDb badge */}
          {movie.imdb_rating && (
            <a
              href={movie.imdb_id ? `https://www.imdb.com/title/${movie.imdb_id}` : undefined}
              target="_blank" rel="noopener noreferrer"
              style={{
                display: 'flex', alignItems: 'center', gap: '0.6rem',
                marginTop: '1rem', padding: '0.65rem 1rem',
                background: 'rgba(245,197,24,0.08)', border: '1px solid rgba(245,197,24,0.25)',
                borderRadius: 'var(--radius)', textDecoration: 'none',
                transition: 'border-color 0.2s',
              }}
              onMouseOver={e => e.currentTarget.style.borderColor = 'rgba(245,197,24,0.5)'}
              onMouseOut={e => e.currentTarget.style.borderColor = 'rgba(245,197,24,0.25)'}
            >
              <span style={{ background: '#f5c518', color: '#000', fontWeight: 800, fontSize: '0.68rem', padding: '0.15rem 0.45rem', borderRadius: 3 }}>IMDb</span>
              <span style={{ color: '#f5c518', fontWeight: 700, fontSize: '1.05rem' }}>{Number(movie.imdb_rating).toFixed(1)}</span>
              <span style={{ color: 'rgba(245,197,24,0.4)', fontSize: '0.78rem', marginLeft: 'auto' }}>/10</span>
            </a>
          )}

          {/* Community rating */}
          {movie.avg_rating > 0 && (
            <div style={{
              marginTop: '0.5rem', padding: '0.65rem 1rem',
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', display: 'flex', alignItems: 'center', gap: '0.6rem',
            }}>
              <span style={{ color: 'var(--gold)', fontSize: '0.95rem' }}>⭐</span>
              <span style={{ color: 'var(--text)', fontWeight: 600 }}>{movie.avg_rating?.toFixed(1)}</span>
              <span style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>community · {movie.rating_count} ratings</span>
            </div>
          )}

          {/* Rate widget */}
          <div style={{ marginTop: '1rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '1rem' }}>
            <div style={{ fontSize: '0.68rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', marginBottom: '0.6rem' }}>
              {rating ? `Your rating: ${rating}★` : 'Rate this film'}
            </div>
            <select value={rating} onChange={e => setRating(e.target.value)}
              style={{ width: '100%', background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--gold)', padding: '0.55rem 0.75rem', borderRadius: 'var(--radius)', fontSize: '0.875rem', outline: 'none', marginBottom: '0.5rem', fontFamily: 'var(--font-body)' }}>
              <option value="">Select rating…</option>
              {RATINGS.map(r => <option key={r} value={r}>{r}★</option>)}
            </select>
            <button onClick={submitRating} disabled={saving || !rating}
              style={{
                width: '100%', background: rating ? 'var(--gold)' : 'var(--surface2)',
                border: '1px solid var(--border-gold)', color: rating ? '#000' : 'var(--text-dim)',
                padding: '0.6rem', borderRadius: 'var(--radius)', fontWeight: 500,
                fontSize: '0.875rem', cursor: rating ? 'pointer' : 'default',
                fontFamily: 'var(--font-body)', transition: 'background 0.2s, color 0.2s',
              }}>
              {saving ? 'Saving…' : rating ? `Save ${rating}★` : 'Pick a rating'}
            </button>
          </div>

          {/* Watchlist button */}
          <button onClick={toggleWatchlist}
            style={{
              width: '100%', marginTop: '0.5rem',
              background: inWatchlist ? 'var(--gold-dim)' : 'var(--surface)',
              border: `1px solid ${inWatchlist ? 'var(--border-gold)' : 'var(--border)'}`,
              color: inWatchlist ? 'var(--gold)' : 'var(--text-muted)',
              padding: '0.65rem', borderRadius: 'var(--radius)', fontWeight: 500,
              fontSize: '0.875rem', cursor: 'pointer',
              fontFamily: 'var(--font-body)', transition: 'all 0.2s',
            }}>
            {inWatchlist ? '🔖 In Watchlist' : '＋ Add to Watchlist'}
          </button>
        </div>

        {/* ── Right column: all details ── */}
        <div>
          {/* Title (shown here if no backdrop) */}
          {!movie.poster_url && (
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '2.4rem', fontWeight: 700, margin: '0 0 0.25rem', lineHeight: 1.1 }}>
              {title}
            </h1>
          )}

          {/* Genre pills */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '1.25rem' }}>
            {genres.map(g => (
              <Link key={g} to={`/?genre=${encodeURIComponent(g)}`}
                style={{
                  background: 'var(--surface2)', border: '1px solid var(--border)',
                  color: 'var(--text-muted)', fontSize: '0.75rem',
                  padding: '0.25rem 0.75rem', borderRadius: 20, textDecoration: 'none',
                  transition: 'border-color 0.2s, color 0.2s',
                }}
                onMouseOver={e => { e.currentTarget.style.borderColor = 'var(--border-gold)'; e.currentTarget.style.color = 'var(--gold)' }}
                onMouseOut={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-muted)' }}
              >{g}</Link>
            ))}
          </div>

          {/* Meta strip */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1.5rem' }}>
            <StatBadge label="Runtime"  value={formatRuntime(movie.runtime)} />
            <StatBadge label="Released" value={formatDate(movie.release_date)} />
            <StatBadge label="Language" value={formatLanguage(movie.language)} />
          </div>

          {/* Director */}
          {movie.director && (
            <div style={{ marginBottom: '1.5rem' }}>
              <div style={{ fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-dim)', marginBottom: '0.3rem' }}>Directed by</div>
              <div style={{ fontSize: '1rem', color: 'var(--text)', fontWeight: 500 }}>{movie.director}</div>
            </div>
          )}

          {/* Overview */}
          <div style={{ marginBottom: '2rem' }}>
            <SectionHeading>Overview</SectionHeading>
            <p style={{ color: 'var(--text-muted)', lineHeight: 1.8, fontSize: '0.95rem', margin: 0 }}>
              {movie.overview || 'No description available for this title.'}
            </p>
          </div>

          {/* Cast */}
          {cast.length > 0 && (
            <div style={{ marginBottom: '2rem' }}>
              <SectionHeading>Cast</SectionHeading>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {cast.map(name => <CastPill key={name} name={name} />)}
              </div>
            </div>
          )}

          {/* Trailer */}
          <div style={{ marginBottom: '2rem' }}>
            <TrailerEmbed trailerKey={movie.trailer_key} title={title} />
          </div>
        </div>
      </div>

      <div style={{ marginTop: '3rem' }}>
        <SectionHeading>Similar Movies</SectionHeading>
        {similarLoading ? (
          <div style={{ textAlign: 'center', padding: '2rem' }}><div className="spinner" style={{ margin: '0 auto' }} /></div>
        ) : similar.length > 0 ? (
          <div className="movies-grid">
            {similar.map(item => (
              <MovieCard key={item.movie_id} movie={item} showScore onNotInterested={(movieId) => setSimilar(prev => prev.filter(m => m.movie_id !== movieId))} />
            ))}
          </div>
        ) : (
          <p style={{ color: 'var(--text-dim)', fontSize: '0.85rem' }}>No similar movies are available yet.</p>
        )}
      </div>

      {/* ── Toast ── */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: '2rem', right: '2rem', zIndex: 9999,
          padding: '0.65rem 1.25rem', borderRadius: 'var(--radius)', fontSize: '0.875rem',
          backdropFilter: 'blur(12px)',
          background: toast.type === 'error' ? 'rgba(224,82,82,0.15)' : toast.type === 'info' ? 'rgba(212,175,55,0.12)' : 'rgba(82,192,122,0.15)',
          border: `1px solid ${toast.type === 'error' ? 'rgba(224,82,82,0.35)' : toast.type === 'info' ? 'rgba(212,175,55,0.35)' : 'rgba(82,192,122,0.35)'}`,
          color: toast.type === 'error' ? '#e05252' : toast.type === 'info' ? '#d4af37' : '#52c07a',
        }}>
          {toast.msg}
        </div>
      )}
    </div>
  )
}