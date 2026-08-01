// All API calls go through here — base URL works for both dev proxy and production
const BASE = ''

async function request(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  }
  if (body) opts.body = JSON.stringify(body)
  const res  = await fetch(BASE + path, opts)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || 'Request failed')
  return data
}

export const api = {
  get:    (path)        => request('GET',    path),
  post:   (path, body)  => request('POST',   path, body),
  delete: (path)        => request('DELETE', path),

  // Auth
  login:    (u, p)   => api.post('/api/auth/login',    { username: u, password: p }),
  register: (u, e, p) => api.post('/api/auth/register', { username: u, email: e, password: p }),
  logout:   ()       => api.post('/api/auth/logout'),
  me:       ()       => api.get('/api/auth/me'),

  // New-user onboarding
  onboardingStatus: ()       => api.get('/api/onboarding/status'),
  onboardingGenres:(genres)  => api.post('/api/onboarding/genres', { genres }),
  onboardingMovies:()        => api.get('/api/onboarding/movies'),
  onboardingComplete:()      => api.post('/api/onboarding/complete'),

  // Movies
  movies:  (params)  => api.get('/api/movies?'   + new URLSearchParams(params)),
  trending:(params)  => api.get('/api/movies/trending?' + new URLSearchParams(params)),
  genres:  ()        => api.get('/api/movies/genres'),
  similarMovies: (movie_id, limit = 12) => api.get(`/api/movies/${movie_id}/similar?limit=${limit}`),

  // Ratings
  rate:       (movie_id, rating) => api.post('/api/rate', { movie_id, rating }),
  myRatings:  ()                 => api.get('/api/ratings'),

  // Watchlist
  watchlist:       ()         => api.get('/api/watchlist'),
  watchlistAdd:    (movie_id) => api.post('/api/watchlist/add',    { movie_id }),
  watchlistRemove: (movie_id) => api.post('/api/watchlist/remove', { movie_id }),

  // Recommendations
  recommendations: (params) => api.get('/api/recommendations?' + new URLSearchParams(params)),
  notInterestedList: () => api.get('/api/feedback/not-interested'),
  notInterested: (movie_id) => api.post('/api/feedback/not-interested', { movie_id }),
  undoNotInterested: (movie_id) => api.post('/api/feedback/not-interested/remove', { movie_id }),

  // Profile
  profile: () => api.get('/api/profile'),
}