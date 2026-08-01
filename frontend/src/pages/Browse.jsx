import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import MovieCard, { MovieCardSkeleton } from '../components/MovieCard'

const PER_PAGE = 42

export default function Browse() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [movies,      setMovies]      = useState([])
  const [genres,      setGenres]      = useState([])
  const [total,       setTotal]       = useState(0)
  const [page,        setPage]        = useState(1)
  const [hasMore,     setHasMore]     = useState(true)
  const [loading,     setLoading]     = useState(false)  // loading more
  const [initialLoad, setInitialLoad] = useState(true)   // very first load
  const loaderRef = useRef(null)

  const search = searchParams.get('search') || ''
  const genre  = searchParams.get('genre')  || ''

  // When filters change → reset list
  useEffect(() => {
    setMovies([])
    setPage(1)
    setHasMore(true)
    setInitialLoad(true)
  }, [search, genre])

  // Fetch next page
  const fetchPage = useCallback(async (pageNum) => {
    if (loading) return
    setLoading(true)
    try {
      const data = await api.movies({ page: pageNum, search, genre, per_page: PER_PAGE })
      setMovies(prev => pageNum === 1 ? data.movies : [...prev, ...data.movies])
      setTotal(data.total)
      setHasMore(pageNum < data.total_pages)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
      setInitialLoad(false)
    }
  }, [search, genre]) // eslint-disable-line react-hooks/exhaustive-deps

  // Trigger fetch when page changes
  useEffect(() => {
    fetchPage(page)
  }, [page, search, genre]) // eslint-disable-line react-hooks/exhaustive-deps

  // IntersectionObserver for infinite scroll sentinel
  useEffect(() => {
    const el = loaderRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          setPage(p => p + 1)
        }
      },
      { rootMargin: '300px' }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasMore, loading])

  // Genres list
  useEffect(() => {
    api.genres().then(d => setGenres(d.genres)).catch(() => {})
  }, [])

  function setParam(key, val) {
    const p = new URLSearchParams(searchParams)
    if (val) p.set(key, val); else p.delete(key)
    setSearchParams(p)
  }

  // Search on Enter
  const searchInputRef = useRef(null)

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Browse Movies</h1>
        <p className="page-subtitle">
          {total > 0 ? `${total.toLocaleString()} movies` : 'Loading…'}
          {genre  && <> in <strong>{genre}</strong></>}
          {search && <> matching "<strong>{search}</strong>"</>}
        </p>
      </div>

      {/* Search + genre filter */}
      <div className="filter-bar">
        <input
          ref={searchInputRef}
          type="text"
          className="search-input"
          placeholder="Search by title…"
          defaultValue={search}
          onKeyDown={e => { if (e.key === 'Enter') setParam('search', e.target.value) }}
        />
        <select
          className="genre-select"
          value={genre}
          onChange={e => setParam('genre', e.target.value)}
        >
          <option value="">All Genres</option>
          {genres.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
        <button className="search-btn"
          onClick={() => setParam('search', searchInputRef.current?.value || '')}>
          Search
        </button>
        {(search || genre) &&
          <button className="search-btn" onClick={() => { setSearchParams({}); if (searchInputRef.current) searchInputRef.current.value = '' }}>
            Clear
          </button>
        }
      </div>

      {/* Genre pills */}
      <div className="genre-pills-row">
        <button className={`genre-pill-btn ${!genre ? 'active' : ''}`} onClick={() => setParam('genre', '')}>All</button>
        {genres.slice(0, 18).map(g => (
          <button key={g} className={`genre-pill-btn ${g === genre ? 'active' : ''}`} onClick={() => setParam('genre', g)}>
            {g}
          </button>
        ))}
      </div>

      <div className="section-label">
        {search || genre ? 'Filtered results' : 'All movies'}
        {total > 0 && <> — {movies.length} of {total.toLocaleString()}</>}
      </div>

      {/* Skeleton grid on initial load */}
      {initialLoad && (
        <div className="movies-grid">
          {Array.from({ length: PER_PAGE }).map((_, i) => <MovieCardSkeleton key={i} />)}
        </div>
      )}

      {/* Actual movies */}
      {!initialLoad && (
        <>
          {movies.length > 0 ? (
            <div className="movies-grid">
              {movies.map(m => (
                <MovieCard key={m.movie_id} movie={m} />
              ))}
              {/* Skeleton cards appended while loading more */}
              {loading && Array.from({ length: 6 }).map((_, i) => <MovieCardSkeleton key={`sk-${i}`} />)}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">🔍</div>
              <h3>No movies found</h3>
              <p>Try a different search or genre.</p>
            </div>
          )}
        </>
      )}

      {/* Infinite scroll sentinel */}
      <div ref={loaderRef} style={{ height: 1 }} />

      {/* End of results */}
      {!hasMore && movies.length > 0 && !loading && (
        <p style={{ textAlign: 'center', color: 'var(--text-dim)', fontSize: '0.82rem', marginTop: '2rem' }}>
          — All {total.toLocaleString()} movies loaded —
        </p>
      )}
    </div>
  )
}