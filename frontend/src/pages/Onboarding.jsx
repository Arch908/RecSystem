import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../AuthContext'
import './Onboarding.css'

export default function Onboarding() {
  const navigate = useNavigate()
  const { user, setUser } = useAuth()
  const [step, setStep] = useState(user?.favorite_genres?.length ? 2 : 1)
  const [genres, setGenres] = useState([])
  const [selected, setSelected] = useState(user?.favorite_genres || [])
  const [movies, setMovies] = useState([])
  const [ratings, setRatings] = useState({})
  const [status, setStatus] = useState(user || {})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api.genres(), api.onboardingStatus()])
      .then(([g, s]) => {
        setGenres(g.genres || [])
        setStatus(s)
        setSelected(s.favorite_genres || [])
        if ((s.favorite_genres || []).length) {
          setStep(2)
          return api.onboardingMovies().then(m => {
            setMovies(m.movies || [])
            const existing = {}
            ;(m.movies || []).forEach(movie => {
              if (movie.user_rating !== null && movie.user_rating !== undefined) {
                existing[movie.movie_id] = Number(movie.user_rating)
              }
            })
            setRatings(existing)
          })
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  function toggleGenre(genre) {
    setSelected(current => current.includes(genre)
      ? current.filter(g => g !== genre)
      : current.length < 8 ? [...current, genre] : current)
  }

  async function saveGenres() {
    setError('')
    if (!selected.length) {
      setError('Select at least one genre.')
      return
    }

    setSaving(true)
    try {
      await api.onboardingGenres(selected)

      const [updatedStatus, movieData, me] = await Promise.all([
        api.onboardingStatus(),
        api.onboardingMovies(),
        api.me(),
      ])

      const nextMovies = movieData.movies || []
      const existingRatings = {}
      nextMovies.forEach(movie => {
        if (movie.user_rating !== null && movie.user_rating !== undefined) {
          existingRatings[movie.movie_id] = Number(movie.user_rating)
        }
      })

      setStatus(updatedStatus)
      setMovies(nextMovies)
      setRatings(existingRatings)
      setUser(me)
      setStep(2)
    } catch (e) {
      setError(e.message || 'Could not update genres.')
    } finally {
      setSaving(false)
    }
  }

  async function rateMovie(movieId, rating) {
    setError('')
    const numeric = Number(rating)
    const previousRating = ratings[movieId]

    setRatings(current => ({ ...current, [movieId]: numeric }))

    try {
      await api.rate(movieId, numeric)

      const [updatedStatus, me] = await Promise.all([
        api.onboardingStatus(),
        api.me(),
      ])

      setStatus(updatedStatus)
      setUser(me)
    } catch (e) {
      setRatings(current => {
        const updated = { ...current }
        if (previousRating === undefined) {
          delete updated[movieId]
        } else {
          updated[movieId] = previousRating
        }
        return updated
      })
      setError(e.message || 'Could not save rating.')
    }
  }

  async function finish() {
    setSaving(true); setError('')
    try {
      await api.onboardingComplete()
      const me = await api.me()
      setUser(me)
      navigate('/recommendations', { replace: true })
    } catch (e) { setError(e.message) }
    finally { setSaving(false) }
  }

  if (loading) return <div className="onboarding-center"><div className="spinner" /></div>

  const ratedCount = status.rating_count || Object.keys(ratings).length
  const needed = Math.max(0, 10 - ratedCount)

  return (
    <div className="onboarding-page">
      <div className="onboarding-header">
        <div className="onboarding-step">Step {step} of 2</div>
        <h1>{step === 1 ? 'What do you love watching?' : 'Rate 10 movies'}</h1>
        <p>{step === 1
          ? 'Select your favorite genres so we can choose better starter movies.'
          : `Rate at least 10 movies. ${needed ? `${needed} more to go.` : 'You are ready!'}`}</p>
      </div>

      {error && <div className="onboarding-error">{error}</div>}

      {step === 1 ? (
        <>
          <div className="genre-grid">
            {genres.map(genre => (
              <button key={genre} type="button"
                className={`genre-chip ${selected.includes(genre) ? 'selected' : ''}`}
                onClick={() => toggleGenre(genre)}>{genre}</button>
            ))}
          </div>
          <div className="onboarding-actions">
            <span>{selected.length}/8 selected</span>
            <button className="onboarding-primary" onClick={saveGenres} disabled={saving || !selected.length}>
              {saving ? 'Saving…' : 'Continue to ratings'}
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="rating-progress-wrap">
            <div className="rating-progress-meta">
              <span>Your progress</span>
              <strong>{Math.min(ratedCount, 10)}/10 rated</strong>
            </div>
            <div className="rating-progress">
              <div style={{ width: `${Math.min(100, ratedCount * 10)}%` }} />
            </div>
          </div>
          <div className="onboarding-movie-grid">
            {movies.map(movie => {
              const currentRating = ratings[movie.movie_id]
              return (
                <article className={`onboarding-movie-card ${currentRating ? 'is-rated' : ''}`} key={movie.movie_id}>
                  <div className="onboarding-poster-wrap">
                    {movie.poster_url
                      ? <img src={movie.poster_url} alt={movie.title} loading="lazy" />
                      : <div className="poster-placeholder">No poster</div>}
                    {currentRating && <span className="onboarding-rated-badge">{currentRating} ★</span>}
                  </div>
                  <div className="onboarding-movie-info">
                    <strong title={movie.title}>{movie.title}</strong>
                    <small>{movie.genres?.split('|').slice(0, 3).join(' • ')}</small>
                    <select value={currentRating || ''}
                      aria-label={`Rate ${movie.title}`}
                      onChange={e => rateMovie(movie.movie_id, e.target.value)}>
                      <option value="">Rate this movie</option>
                      {[0.5,1,1.5,2,2.5,3,3.5,4,4.5,5].map(v => <option key={v} value={v}>{v} ★</option>)}
                    </select>
                  </div>
                </article>
              )
            })}
          </div>
          <div className="onboarding-actions sticky">
            <button
              type="button"
              className="onboarding-secondary"
              onClick={() => {
                setError('')
                setSelected(status.favorite_genres || selected)
                setStep(1)
              }}
            >
              Change genres
            </button>
            <strong>{ratedCount}/10 rated</strong>
            <button className="onboarding-primary" onClick={finish} disabled={saving || ratedCount < 10}>
              {saving ? 'Finishing…' : 'See my recommendations'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
