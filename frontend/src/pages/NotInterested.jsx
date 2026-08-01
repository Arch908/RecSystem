import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import MovieCard from '../components/MovieCard'

export default function NotInterested() {
  const [movies, setMovies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.notInterestedList()
      .then(data => setMovies(data.movies || []))
      .catch(err => setError(err.message || 'Could not load your feedback.'))
      .finally(() => setLoading(false))
  }, [])

  function handleRestore(movieId) {
    setMovies(current => current.filter(movie => movie.movie_id !== movieId))
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">👎 Not Interested</h1>
        <p className="page-subtitle">
          {movies.length} movie{movies.length !== 1 ? 's' : ''} hidden from your recommendations
        </p>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: '4rem' }}>
          <div className="spinner" style={{ margin: '0 auto' }} />
        </div>
      )}

      {error && (
        <div className="empty-state">
          <div className="empty-icon">⚠️</div>
          <h3>Could not load your movies</h3>
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && movies.length > 0 && (
        <>
          <div className="section-label">Hidden movies</div>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginBottom: '1.25rem' }}>
            Restore a movie to allow it to appear in future recommendations again.
          </p>
          <div className="movies-grid">
            {movies.map(movie => (
              <MovieCard
                key={movie.movie_id}
                movie={movie}
                showUndoNotInterested
                onUndoNotInterested={handleRestore}
              />
            ))}
          </div>
        </>
      )}

      {!loading && !error && movies.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">👎</div>
          <h3>No hidden movies</h3>
          <p>Movies you mark as Not Interested will appear here.</p>
          <Link to="/recommendations" className="btn-gold" style={{ display: 'inline-block', marginTop: '1.5rem' }}>
            View Recommendations
          </Link>
        </div>
      )}
    </div>
  )
}
