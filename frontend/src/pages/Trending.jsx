import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import MovieCard from '../components/MovieCard'

export default function Trending() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [movies,     setMovies]     = useState([])
  const [genres,     setGenres]     = useState([])
  const [total,      setTotal]      = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading,    setLoading]    = useState(true)

  const page  = parseInt(searchParams.get('page')  || '1')
  const genre = searchParams.get('genre') || ''
  const limit = parseInt(searchParams.get('limit') || '200')

  const fetchTrending = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.trending({ page, genre, limit })
      setMovies(data.movies)
      setTotal(data.total)
      setTotalPages(data.total_pages)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [page, genre, limit])

  useEffect(() => { fetchTrending() }, [fetchTrending])

  useEffect(() => {
    api.genres().then(d => setGenres(d.genres)).catch(() => {})
  }, [])

  function setParam(key, val) {
    const p = new URLSearchParams(searchParams)
    if (val) p.set(key, val); else p.delete(key)
    p.delete('page')
    setSearchParams(p)
  }

  function setPage(p) {
    const params = new URLSearchParams(searchParams)
    params.set('page', p)
    setSearchParams(params)
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">🔥 Trending Now</h1>
        <p className="page-subtitle">{total} most-rated movies across all users</p>
      </div>

      {/* Filters */}
      <div className="filter-bar" style={{ marginBottom: '1rem' }}>
        <select
          className="genre-select"
          value={genre}
          onChange={e => setParam('genre', e.target.value)}
        >
          <option value="">All Genres</option>
          {genres.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
        <select
          className="genre-select"
          value={limit}
          onChange={e => setParam('limit', e.target.value)}
        >
          {[100, 200, 300, 500].map(l =>
            <option key={l} value={l}>Top {l}</option>
          )}
        </select>
        {genre &&
          <button className="search-btn" onClick={() => setParam('genre', '')}>
            Clear genre
          </button>
        }
      </div>

      {/* Genre pills */}
      <div className="genre-pills-row">
        <button
          className={`genre-pill-btn ${!genre ? 'active' : ''}`}
          onClick={() => setParam('genre', '')}
        >All</button>
        {genres.slice(0, 20).map(g => (
          <button
            key={g}
            className={`genre-pill-btn ${g === genre ? 'active' : ''}`}
            onClick={() => setParam('genre', g)}
          >{g}</button>
        ))}
      </div>

      <div className="section-label">
        Rank #{(page - 1) * 42 + 1}–#{Math.min(page * 42, total)} of {total} — page {page} of {totalPages}
      </div>

      {loading
        ? <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--text-muted)' }}>
            <div className="spinner" style={{ margin: '0 auto' }} />
          </div>
        : movies.length
          ? <>
              <div className="movies-grid">
                {movies.map(m => (
                  <MovieCard key={m.movie_id} movie={m} showRank />
                ))}
              </div>
              <Pagination page={page} totalPages={totalPages} onPage={setPage} genre={genre} limit={limit} />
              <p className="page-info" style={{ textAlign: 'center', marginTop: '1rem' }}>
                Showing {(page - 1) * 42 + 1}–{Math.min(page * 42, total)} of {total}
              </p>
            </>
          : <div className="empty-state">
              <div className="empty-icon">🔍</div>
              <h3>No movies found</h3>
              <p>Try a different genre filter.</p>
            </div>
      }
    </div>
  )
}

function Pagination({ page, totalPages, onPage }) {
  if (totalPages <= 1) return null
  const ws = Math.max(1, page - 2)
  const we = Math.min(totalPages, page + 2)
  return (
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
  )
}