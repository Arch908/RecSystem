import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './AuthContext'
import Navbar          from './components/Navbar'
import Browse          from './pages/Browse'
import Trending        from './pages/Trending'
import Recommendations from './pages/Recommendations'
import Watchlist       from './pages/Watchlist'
import MyRatings       from './pages/MyRatings'
import Profile         from './pages/Profile'
import AdminDashboard  from './pages/AdminDashboard'
import Login           from './pages/Login'
import Register        from './pages/Register'
import MovieDetail     from './pages/MovieDetail'
import Onboarding      from './pages/Onboarding'
import NotInterested    from './pages/NotInterested'
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

function ScrollToTop() {
  const { pathname } = useLocation()

  useEffect(() => {
    console.log('ScrollToTop fired for:', pathname)
    window.scrollTo(0, 0)
  }, [pathname])

  return null
}

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
      <div className="spinner" />
    </div>
  )
  if (!user) return <Navigate to="/login" replace />
  if (!user.is_admin && !user.onboarding_complete) return <Navigate to="/onboarding" replace />
  return children
}

function AuthenticatedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ display: 'grid', placeItems: 'center', height: '60vh' }}><div className="spinner" /></div>
  if (!user) return <Navigate to="/login" replace />
  if (user.is_admin || user.onboarding_complete) return <Navigate to="/" replace />
  return children
}

function AppShell() {
  const { loading } = useAuth()
  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
      <div className="spinner" />
    </div>
  )

  return (
    <>
      <ScrollToTop />
      <div className="grain-overlay" />
      <Navbar />
      <main className="main-content">
        <Routes>
          {/* Public */}
          <Route path="/login"    element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/onboarding" element={<AuthenticatedRoute><Onboarding /></AuthenticatedRoute>} />

          {/* Protected */}
          <Route path="/"                element={<ProtectedRoute><Browse /></ProtectedRoute>} />
          <Route path="/movie/:id"       element={<ProtectedRoute><MovieDetail /></ProtectedRoute>} />  {/* ← new */}
          <Route path="/trending"        element={<ProtectedRoute><Trending /></ProtectedRoute>} />
          <Route path="/recommendations" element={<ProtectedRoute><Recommendations /></ProtectedRoute>} />
          <Route path="/watchlist"       element={<ProtectedRoute><Watchlist /></ProtectedRoute>} />
          <Route path="/my-ratings"      element={<ProtectedRoute><MyRatings /></ProtectedRoute>} />
          <Route path="/not-interested"  element={<ProtectedRoute><NotInterested /></ProtectedRoute>} />
          <Route path="/profile"         element={<ProtectedRoute><Profile /></ProtectedRoute>} />
          <Route path="/admin"           element={<ProtectedRoute><AdminDashboard /></ProtectedRoute>} />
          <Route path="/admin/*"         element={<ProtectedRoute><AdminDashboard /></ProtectedRoute>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  )
}

export default function App() {
  useEffect(() => {
    if ('scrollRestoration' in window.history) {
      window.history.scrollRestoration = 'manual'
    }
  }, [])

  return (
    <BrowserRouter>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </BrowserRouter>
  )
}