import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import MovieCard from '../components/MovieCard'

export default function Watchlist() {
  const [movies,  setMovies]  = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    api.watchlist()
      .then(data => setMovies(data.watchlist))
      .catch(e  => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  function handleWatchlist(movieId, nowInWatchlist) {
    if (!nowInWatchlist) {
      // Remove from local list immediately
      setMovies(prev => prev.filter(m => m.movie_id !== movieId))
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">🔖 My Watchlist</h1>
        <p className="page-subtitle">
          {movies.length} movie{movies.length !== 1 ? 's' : ''} saved to watch
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

      {!loading && !error && movies.length > 0 &&
        <>
          <div className="section-label">Saved movies</div>
          <div className="movies-grid">
            {movies.map(m => (
              <MovieCard
                key={m.movie_id}
                movie={{ ...m, in_watchlist: true }}
                onWatchlist={handleWatchlist}
              />
            ))}
          </div>
        </>
      }

      {!loading && !error && movies.length === 0 &&
        <div className="empty-state">
          <div className="empty-icon">🔖</div>
          <h3>Your watchlist is empty</h3>
          <p>Browse movies and click ＋ to save them here.</p>
          <Link to="/" className="btn-gold" style={{ display: 'inline-block', marginTop: '1.5rem' }}>
            Browse Movies
          </Link>
        </div>
      }
    </div>
  )
}
