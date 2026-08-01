import { useState, useEffect, useCallback } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { api } from '../api'
import MovieCard from '../components/MovieCard'

export default function Recommendations() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [data,        setData]        = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [error,       setError]       = useState(null)

  const method = searchParams.get('method') || 'all'
  const page   = parseInt(searchParams.get('page') || '1')

  const fetchRecs = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.recommendations({ method, page })
      setData(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [method, page])

  useEffect(() => { fetchRecs() }, [fetchRecs])

  function setMethod(m) {
    const p = new URLSearchParams()
    p.set('method', m)
    setSearchParams(p)
  }

  function setPage(p) {
    const params = new URLSearchParams(searchParams)
    params.set('page', p)
    setSearchParams(params)
  }

  // ── Not enough ratings ──────────────────────────────────────────────────
  if (!loading && data?.no_ratings) {
    const pct = Math.min((data.rating_count / 10) * 100, 100)
    return (
      <div>
        <div className="page-header">
          <h1 className="page-title">Picked For You</h1>
          <p className="page-subtitle">Personalized recommendations based on your ratings</p>
        </div>
        <div className="empty-state">
          <div className="empty-icon">🎬</div>
          <h3>Rate some movies first</h3>
          <p>
            You've rated <strong style={{ color: 'var(--gold)' }}>{data.rating_count}</strong> movie{data.rating_count !== 1 ? 's' : ''} so far.
            Rate at least <strong style={{ color: 'var(--gold)' }}>{data.ratings_needed}</strong> more to unlock personalized recommendations.
          </p>
          <div className="rating-progress">
            <div className="rating-progress-bar" style={{ width: `${pct}%` }} />
          </div>
          <p className="progress-label">{data.rating_count} / 10 movies rated</p>
          <Link to="/" className="btn-gold" style={{ display: 'inline-block', marginTop: '1.75rem' }}>
            Browse &amp; Rate Movies
          </Link>
          <br />
          <Link to="/trending" style={{ display: 'inline-block', marginTop: '1rem', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Or explore Trending movies →
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Picked For You</h1>
        <p className="page-subtitle">Personalized recommendations based on your ratings</p>
      </div>

      {data?.is_fallback && <div className="empty-state" style={{padding:'1rem 1.25rem', marginBottom:'1.25rem'}}>
        <strong style={{color:'var(--gold)'}}>Starter recommendations</strong>
        <span style={{marginLeft:'0.5rem', color:'var(--text-muted)'}}>Rate {data.ratings_needed} more movie{data.ratings_needed===1?'':'s'} to unlock fully personalized CF/CBF recommendations.</span>
      </div>}

      {/* Stats row */}
      {data && !data.no_ratings &&
        <div className="stats-row">
          <div className="stat-chip"><strong>{data.total}</strong> total</div>
          <div className="stat-chip"><strong>{data.cf_count}</strong> collaborative</div>
          <div className="stat-chip"><strong>{data.cb_count}</strong> content-based</div>
          <div className="stat-chip"><strong>{data.total_pages}</strong> pages</div>
          {data.hybrid_weights && <div className="stat-chip"><strong>{Math.round(data.hybrid_weights.collaborative*100)}/{Math.round(data.hybrid_weights.content_based*100)}</strong> tuned CF/CBF</div>}
        </div>
      }

      {/* Method tabs — use <a> tags to match style.css .method-tab rules */}
      {data && !data.no_ratings && !data.is_fallback &&
        <div className="method-tabs">
          {[
            { key: 'all',           label: 'All',                   count: data.total_all },
            { key: 'collaborative', label: 'Users Like You',        count: data.cf_count  },
            { key: 'content',       label: 'Similar to Your Taste', count: data.cb_count  },
          ].map(tab => (
            <a
              key={tab.key}
              href="#"
              className={`method-tab ${method === tab.key ? 'active' : ''}`}
              onClick={e => { e.preventDefault(); setMethod(tab.key) }}
              style={{ cursor: 'pointer' }}
            >
              <span className="tab-label">{tab.label}</span>
              <span className="tab-count">{tab.count}</span>
            </a>
          ))}
        </div>
      }

      {/* Method explanation */}
      {data && !data.no_ratings &&
        <div className="method-explain">
          {method === 'collaborative'
            ? <><span className="explain-dot dot-cf" />Movies predicted from users with similar taste to yours</>
            : method === 'content'
            ? <><span className="explain-dot dot-cb" />Movies similar in genre and style to ones you've rated highly</>
            : <><span className="explain-dot dot-all" />All unique recommendations ranked by predicted score</>
          }
        </div>
      }

      {/* Section label */}
      {data && !data.no_ratings &&
        <div className="section-label">
          {method === 'all' ? 'All picks' : method === 'collaborative' ? 'Users Like You' : 'Similar to Your Taste'}
          {' '}— page {data.page} of {data.total_pages}
        </div>
      }

      {/* Loading */}
      {loading &&
        <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>
          <div className="spinner" style={{ margin: '0 auto' }} />
        </div>
      }

      {/* Error */}
      {error &&
        <div className="empty-state">
          <div className="empty-icon">⚠️</div>
          <h3>Something went wrong</h3>
          <p>{error}</p>
          <button
            className="btn-gold"
            style={{ marginTop: '1rem', border: 'none', cursor: 'pointer' }}
            onClick={fetchRecs}
          >
            Try Again
          </button>
        </div>
      }

      {/* Movie grid */}
      {!loading && !error && data?.recommendations?.length > 0 &&
        <>
          <div className="movies-grid">
            {data.recommendations.map(movie => (
              <MovieCard
                key={movie.movie_id}
                movie={movie}
                showScore
                onNotInterested={(movieId) => setData(prev => prev ? ({
                  ...prev,
                  recommendations: prev.recommendations.filter(m => m.movie_id !== movieId),
                  total: Math.max(0, prev.total - 1),
                  total_all: Math.max(0, (prev.total_all || prev.total) - 1),
                }) : prev)}
              />
            ))}
          </div>
          <Pagination
            page={data.page}
            totalPages={data.total_pages}
            total={data.total}
            perPage={data.per_page}
            onPage={setPage}
          />
        </>
      }

      {/* Empty — has ratings but no results */}
      {!loading && !error && data && !data.no_ratings && data.recommendations?.length === 0 &&
        <div className="empty-state">
          <div className="empty-icon">🔍</div>
          <h3>No {method} recommendations found</h3>
          <p>Try switching to a different filter tab, or rate more movies to improve results.</p>
          <a
            href="#"
            className="btn-gold"
            style={{ display: 'inline-block', marginTop: '1.5rem' }}
            onClick={e => { e.preventDefault(); setMethod('all') }}
          >
            Show All Recommendations
          </a>
        </div>
      }
    </div>
  )
}

function Pagination({ page, totalPages, total, perPage, onPage }) {
  if (totalPages <= 1) return null
  const ws = Math.max(1, page - 2)
  const we = Math.min(totalPages, page + 2)
  return (
    <>
      <div className="pagination-row">
        {page > 1 && <>
          <button className="page-btn" onClick={() => onPage(1)}>«</button>
          <button className="page-btn" onClick={() => onPage(page - 1)}>← Prev</button>
        </>}
        {ws > 1 && <span className="page-info">…</span>}
        {Array.from({ length: we - ws + 1 }, (_, i) => ws + i).map(p =>
          p === page
            ? <span key={p} className="page-btn page-btn-active">{p}</span>
            : <button key={p} className="page-btn" onClick={() => onPage(p)}>{p}</button>
        )}
        {we < totalPages && <span className="page-info">…</span>}
        {page < totalPages && <>
          <button className="page-btn" onClick={() => onPage(page + 1)}>Next →</button>
          <button className="page-btn" onClick={() => onPage(totalPages)}>»</button>
        </>}
      </div>
      <p className="page-info" style={{ textAlign: 'center', marginTop: '1rem' }}>
        Showing {(page - 1) * perPage + 1}–{Math.min(page * perPage, total)} of {total}
      </p>
    </>
  )
}