import { useState, useEffect, useCallback, useRef } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'
import { api } from '../api'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement, LineElement,
  PointElement, ArcElement, Filler, Tooltip, Legend,
} from 'chart.js'
import { Bar, Line } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale, LinearScale, BarElement, LineElement,
  PointElement, ArcElement, Filler, Tooltip, Legend,
)

// ── Shared Chart.js theme ──────────────────────────────────────────────────

const GOLD      = '#d4af37'
const GOLD_DIM  = 'rgba(212,175,55,0.18)'
const BLUE      = '#6aa0ff'
const BLUE_DIM  = 'rgba(106,160,255,0.18)'
const GREEN     = '#64dc9a'
const GREEN_DIM = 'rgba(100,220,154,0.18)'
const RED       = '#e05252'
const MUTED     = 'rgba(255,255,255,0.07)'

const BASE_OPTS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 700, easing: 'easeOutQuart' },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: '#18181c',
      borderColor: 'rgba(212,175,55,0.3)',
      borderWidth: 1,
      titleColor: '#e8e6e0',
      bodyColor: '#7a7870',
      padding: 10,
      cornerRadius: 8,
    },
  },
  scales: {
    x: {
      grid: { color: MUTED, drawBorder: false },
      ticks: { color: '#4a4845', font: { size: 11 } },
    },
    y: {
      grid: { color: MUTED, drawBorder: false },
      ticks: { color: '#4a4845', font: { size: 11 } },
      beginAtZero: true,
    },
  },
}

// ── Shared small components ────────────────────────────────────────────────

function ChartCard({ title, subtitle, height = 220, children }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', padding: '1.5rem',
      display: 'flex', flexDirection: 'column', gap: '1rem',
    }}>
      <div>
        <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-muted)', fontWeight: 500 }}>{title}</div>
        {subtitle && <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>{subtitle}</div>}
      </div>
      <div style={{ height, position: 'relative' }}>{children}</div>
    </div>
  )
}

function KpiCard({ label, value, color, sub }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', padding: '1.25rem 1.5rem',
      borderTop: `2px solid ${color}`,
    }}>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: '2rem', fontWeight: 700, color: 'var(--text)', lineHeight: 1, marginBottom: '0.3rem' }}>{value}</div>
      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>{label}</div>
      {sub && <div style={{ fontSize: '0.72rem', color, marginTop: '0.3rem' }}>{sub}</div>}
    </div>
  )
}

function AdminBtn({ children, onClick, danger, disabled = false }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      fontSize: '0.75rem', padding: '0.3rem 0.8rem', borderRadius: 6,
      border: `1px solid ${danger ? 'rgba(224,82,82,0.3)' : 'var(--border-gold)'}`,
      background: danger ? 'rgba(224,82,82,0.1)' : 'var(--gold-dim)',
      color: danger ? '#e05252' : 'var(--gold)',
      cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.55 : 1, fontFamily: 'var(--font-body)', transition: 'background 0.2s',
    }}>
      {children}
    </button>
  )
}

function AdminPagination({ page, totalPages, onPage, total }) {
  if (totalPages <= 1) return null
  const ws = Math.max(1, page - 2), we = Math.min(totalPages, page + 2)
  return (
    <div style={{ display: 'flex', gap: '0.4rem', marginTop: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
      {page > 1 && <button className="page-btn" onClick={() => onPage(page - 1)}>← Prev</button>}
      {ws > 1 && <span className="page-info">…</span>}
      {Array.from({ length: we - ws + 1 }, (_, i) => ws + i).map(p =>
        p === page
          ? <span key={p} className="page-btn page-btn-active">{p}</span>
          : <button key={p} className="page-btn" onClick={() => onPage(p)}>{p}</button>
      )}
      {we < totalPages && <span className="page-info">…</span>}
      {page < totalPages && <button className="page-btn" onClick={() => onPage(page + 1)}>Next →</button>}
      <span style={{ color: 'var(--text-dim)', fontSize: '0.78rem', marginLeft: '0.5rem' }}>{total} total</span>
    </div>
  )
}

// ── Main dashboard ─────────────────────────────────────────────────────────

const TABS = [
  { key: 'overview',  label: '📊 Overview' },
  { key: 'users',     label: '👥 Users' },
  { key: 'movies',    label: '🎬 Movies' },
  { key: 'ml',        label: '🤖 ML Cache' },
  { key: 'recs',      label: '📋 Rec Logs' },
  { key: 'accuracy',  label: '🎯 Evaluation' },
]

export default function AdminDashboard() {
  const { user } = useAuth()
  const [tab, setTab] = useState('overview')
  if (!user?.is_admin) return <Navigate to="/" replace />

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2.5rem', paddingBottom: '1.5rem', borderBottom: '1px solid var(--border)' }}>
        <div>
          <h1 className="page-title">Admin Panel</h1>
          <p className="page-subtitle">Manage users, movies, ML models, and analytics</p>
        </div>
        <span style={{ background: 'rgba(224,82,82,0.15)', border: '1px solid rgba(224,82,82,0.35)', color: '#e05252', fontSize: '0.72rem', fontWeight: 600, padding: '0.25rem 0.75rem', borderRadius: 20, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          ⚙ Administrator
        </span>
      </div>

      <nav style={{ display: 'flex', gap: '0.5rem', marginBottom: '2.5rem', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            padding: '0.65rem 1.25rem', border: 'none',
            borderBottom: `2px solid ${tab === t.key ? '#e05252' : 'transparent'}`,
            marginBottom: -1, background: tab === t.key ? 'rgba(224,82,82,0.07)' : 'transparent',
            color: tab === t.key ? '#e05252' : 'var(--text-muted)',
            fontSize: '0.875rem', cursor: 'pointer', borderRadius: '6px 6px 0 0',
            fontFamily: 'var(--font-body)', transition: 'color 0.2s',
          }}>
            {t.label}
          </button>
        ))}
      </nav>

      {tab === 'overview'  && <OverviewTab />}
      {tab === 'users'     && <UsersTab />}
      {tab === 'movies'    && <MoviesTab />}
      {tab === 'ml'        && <MLTab />}
      {tab === 'recs'      && <RecsTab />}
      {tab === 'accuracy'  && <AccuracyTab />}
    </div>
  )
}

// ── Overview tab ───────────────────────────────────────────────────────────

function OverviewTab() {
  const [stats,   setStats]   = useState(null)
  const [growth,  setGrowth]  = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState('')

  useEffect(() => {
    let cancelled = false

    async function loadOverview() {
      setLoading(true)
      setError('')

      const [statsResult, growthResult] = await Promise.allSettled([
        api.get('/api/admin/stats'),
        api.get('/api/admin/user-growth'),
      ])

      if (cancelled) return

      if (statsResult.status === 'fulfilled') {
        setStats(statsResult.value)
      } else {
        setStats(null)
        setError(statsResult.reason?.message || 'Could not load admin overview statistics.')
      }

      if (growthResult.status === 'fulfilled') {
        setGrowth(growthResult.value)
      } else {
        setGrowth(null)
      }

      setLoading(false)
    }

    loadOverview()
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '4rem' }}><div className="spinner" style={{ margin: '0 auto' }} /></div>
  }

  if (!stats) {
    return (
      <div className="empty-state">
        <div className="empty-icon">⚠️</div>
        <h3>Overview could not be loaded</h3>
        <p>{error || 'The admin statistics endpoint returned no data.'}</p>
        <p style={{ color: 'var(--text-dim)', fontSize: '0.78rem' }}>
          Check the browser Console and Network tabs for <code>/api/admin/stats</code>.
        </p>
      </div>
    )
  }

  const ratingsByDay = Array.isArray(stats.ratings_by_day) ? stats.ratings_by_day : []
  const ratingDistribution = Array.isArray(stats.rating_dist) ? stats.rating_dist : []
  const mostRatedMovies = Array.isArray(stats.top_movies) ? stats.top_movies : []
  const genreDistribution = Array.isArray(stats.top_genres) ? stats.top_genres : []

  const ratingsDay = {
    labels: ratingsByDay.map(d => String(d.day || '').slice(5)),
    datasets: [{ label: 'Ratings', data: ratingsByDay.map(d => Number(d.cnt) || 0), backgroundColor: GOLD_DIM, borderColor: GOLD, borderWidth: 2, borderRadius: 4 }],
  }
  const ratingDist = {
    labels: ratingDistribution.map(d => `${d.star}★`),
    datasets: [{ label: 'Count', data: ratingDistribution.map(d => Number(d.cnt) || 0), backgroundColor: [BLUE_DIM,BLUE_DIM,GOLD_DIM,GOLD_DIM,GREEN_DIM], borderColor: [BLUE,BLUE,GOLD,GOLD,GREEN], borderWidth: 2, borderRadius: 4 }],
  }
  const topMovies = {
    labels: mostRatedMovies.map(d => String(d.title || 'Untitled').replace(/\s*\(\d{4}\)/, '').slice(0, 22)),
    datasets: [{ label: 'Ratings', data: mostRatedMovies.map(d => Number(d.cnt) || 0), backgroundColor: GOLD_DIM, borderColor: GOLD, borderWidth: 1, borderRadius: 3 }],
  }
  const topGenres = {
    labels: genreDistribution.map(d => d.genre || 'Unknown'),
    datasets: [{ label: 'Movies', data: genreDistribution.map(d => Number(d.cnt) || 0), backgroundColor: GREEN_DIM, borderColor: GREEN, borderWidth: 1, borderRadius: 3 }],
  }

  const growthLine = growth?.growth?.length ? {
    labels: growth.growth.map(d => d.day.slice(5)),
    datasets: [
      { label: 'New Users', data: growth.growth.map(d => d.new_users), borderColor: BLUE, backgroundColor: BLUE_DIM, fill: true, tension: 0.4, pointRadius: 3, pointBackgroundColor: BLUE },
      { label: 'Cumulative', data: growth.growth.map(d => d.cumulative), borderColor: GOLD, backgroundColor: 'transparent', fill: false, tension: 0.4, pointRadius: 2, borderDash: [4,3], pointBackgroundColor: GOLD },
    ],
  } : null

  const horizOpts = { ...BASE_OPTS, indexAxis: 'y', scales: { x: { ...BASE_OPTS.scales.x, beginAtZero: true }, y: { grid: { display: false }, ticks: { color: '#7a7870', font: { size: 11 } } } } }
  const lineOpts  = { ...BASE_OPTS, plugins: { ...BASE_OPTS.plugins, legend: { display: true, labels: { color: '#7a7870', boxWidth: 12, font: { size: 11 } } } } }

  return (
    <div>
      <div className="admin-kpi-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: '1rem', marginBottom: '2rem' }}>
        <KpiCard label="Total Users"  value={stats.total_users}   color={GOLD} />
        <KpiCard label="Movies"       value={stats.total_movies}  color={BLUE} />
        <KpiCard label="User Ratings" value={stats.total_ratings} color={GREEN} />
        <KpiCard label="Banned"       value={stats.banned_users}  color={RED} />
        <KpiCard label="Admins"       value={stats.admin_users}   color="#c07a52" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1.25rem' }}>
        <ChartCard title="Ratings — last 14 days" height={200}><Bar data={ratingsDay} options={BASE_OPTS} /></ChartCard>
        <ChartCard title="Rating Distribution"    height={200}><Bar data={ratingDist} options={BASE_OPTS} /></ChartCard>
        <ChartCard title="Most Rated Movies"      height={240}><Bar data={topMovies}  options={horizOpts} /></ChartCard>
        <ChartCard title="Genre Distribution"     height={240}><Bar data={topGenres}  options={horizOpts} /></ChartCard>
      </div>

      {growthLine ? (
        <ChartCard title="User Growth — last 60 days" subtitle="New registrations per day and running total (dashed)" height={220}>
          <Line data={growthLine} options={lineOpts} />
        </ChartCard>
      ) : (
        <ChartCard title="User Growth" height={100}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-dim)', fontSize: '0.85rem' }}>No registration data yet.</div>
        </ChartCard>
      )}
    </div>
  )
}

// ── Evaluation tab ───────────────────────────────────────────────────────────

function AccuracyTab() {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [offline, setOffline] = useState(null)
  const [running, setRunning] = useState(false)
  const [evalMessage, setEvalMessage] = useState('')

  useEffect(() => {
    Promise.all([
      api.get('/api/admin/rec-accuracy').catch(() => null),
      api.get('/api/admin/offline-evaluation').catch(() => null),
    ]).then(([live, evalData]) => { setData(live); setOffline(evalData) }).finally(() => setLoading(false))
  }, [])

  async function runEvaluation() {
    if (!confirm('Run a fresh offline evaluation? This may take a minute.')) return
    setRunning(true)
    setEvalMessage('Running evaluation… Please keep this page open.')
    try {
      const fresh = await api.post('/api/admin/offline-evaluation/run', { k: 10, max_users: 200, random_state: 42 })
      setOffline(fresh)
      setEvalMessage('Evaluation completed and saved successfully.')
    } catch (error) {
      setEvalMessage(error.message || 'Evaluation failed.')
    } finally {
      setRunning(false)
    }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: '4rem' }}><div className="spinner" style={{ margin: '0 auto' }} /></div>
  if (!data && !offline) return null

  if ((!data || data.total_logged === 0) && !offline) return (
    <div className="empty-state">
      <div className="empty-icon">🎯</div>
      <h3>No recommendation data yet</h3>
      <p>Live success tracking starts once users receive and later rate recommended movies.</p>
    </div>
  )

  const liveData = data || {total_logged:0,rated_count:0,rated_pct:0,highly_rated:0,accuracy_pct:0,avg_user_rating:0,weekly_accuracy:[],score_buckets:[],by_method:[]}

  const methodColors = { collaborative: BLUE, content: GREEN, both: GOLD }
  const methodDim    = { collaborative: BLUE_DIM, content: GREEN_DIM, both: GOLD_DIM }

  const weeklyChart = {
    labels: liveData.weekly_accuracy.map(w => w.week?.slice(5) || ''),
    datasets: [{ label: '% Highly Rated', data: liveData.weekly_accuracy.map(w => w.pct), borderColor: GOLD, backgroundColor: GOLD_DIM, fill: true, tension: 0.4, pointRadius: 4, pointBackgroundColor: GOLD }],
  }

  const scatterChart = {
    labels: liveData.score_buckets.map(b => b.score.toFixed(1)),
    datasets: [{ label: 'Avg User Rating', data: liveData.score_buckets.map(b => b.avg_user_rating), borderColor: GREEN, backgroundColor: GREEN_DIM, fill: false, tension: 0.3, pointRadius: 5, pointBackgroundColor: GREEN }],
  }

  const methodChart = {
    labels: liveData.by_method.map(m => m.method),
    datasets: [{
      label: 'Positive Rate %',
      data: liveData.by_method.map(m => m.accuracy_pct),
      backgroundColor: liveData.by_method.map(m => methodDim[m.method] || GOLD_DIM),
      borderColor:     liveData.by_method.map(m => methodColors[m.method] || GOLD),
      borderWidth: 2, borderRadius: 6,
    }],
  }

  const pctOpts = {
    ...BASE_OPTS,
    scales: { ...BASE_OPTS.scales, y: { ...BASE_OPTS.scales.y, max: 100, ticks: { ...BASE_OPTS.scales.y.ticks, callback: v => `${v}%` } } },
    plugins: { ...BASE_OPTS.plugins, tooltip: { ...BASE_OPTS.plugins.tooltip, callbacks: { label: ctx => ` ${ctx.parsed.y.toFixed(1)}%` } } },
  }

  const corrOpts = {
    ...BASE_OPTS,
    scales: {
      x: { ...BASE_OPTS.scales.x, title: { display: true, text: 'Predicted Score', color: '#4a4845', font: { size: 11 } } },
      y: { ...BASE_OPTS.scales.y, min: 0, max: 5, title: { display: true, text: 'Avg User Rating', color: '#4a4845', font: { size: 11 } } },
    },
    plugins: { ...BASE_OPTS.plugins, tooltip: { ...BASE_OPTS.plugins.tooltip, callbacks: { title: ctx => `Score: ${ctx[0].label}`, label: ctx => ` Avg rating: ${ctx.parsed.y.toFixed(2)}★` } } },
  }

  return (
    <div>
      <div style={{background:'var(--surface)',border:'1px solid var(--border)',borderRadius:'var(--radius-lg)',padding:'1.25rem',marginBottom:'1.5rem'}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:'1rem',flexWrap:'wrap',marginBottom:'0.9rem'}}>
          <div>
            <div className="section-label" style={{margin:0}}>Offline Recommendation Evaluation (Registered Users)</div>
            <div style={{color:'var(--text-dim)',fontSize:'0.75rem',marginTop:'0.25rem'}}>
              Leakage-free holdout evaluation using {offline?.protocol?.dataset || 'registered user data'}
              {offline?.eligible_users != null ? ` • ${offline.eligible_users} eligible user${offline.eligible_users === 1 ? '' : 's'}` : ''}
              {offline?.generated_at ? ` • Last run: ${new Date(offline.generated_at).toLocaleString()}` : ''}
            </div>
          </div>
          <AdminBtn onClick={runEvaluation} disabled={running}>{running ? '⏳ Running…' : '▶ Run Evaluation'}</AdminBtn>
        </div>

        {evalMessage && <div style={{padding:'0.65rem 0.8rem',marginBottom:'0.9rem',borderRadius:6,background:running?'rgba(106,160,255,0.1)':'var(--gold-dim)',color:running?BLUE:GOLD,fontSize:'0.8rem'}}>{evalMessage}</div>}

        {offline && offline.insufficient_data ? (
          <div style={{padding:'1rem 1.25rem', background:'rgba(212,175,55,0.08)', border:'1px solid var(--border-gold)', borderRadius:'var(--radius)', color:'var(--text-muted)', fontSize:'0.85rem'}}>
            <strong style={{color:'var(--gold)'}}>Not enough data yet.</strong> {offline.note}
            {offline.registered_users_with_ratings != null && (
              <div style={{marginTop:'0.4rem', fontSize:'0.78rem', color:'var(--text-dim)'}}>
                {offline.registered_users_with_ratings} registered user(s) have ratings so far.
              </div>
            )}
          </div>
        ) : offline ? <>
          <div className="section-label" style={{marginBottom:'0.75rem'}}>Ranking Quality &amp; Catalog Evaluation at K={offline.protocol.k}</div>
          {offline.recommended_weights && (
            <div style={{display:'grid',gridTemplateColumns:'repeat(3,minmax(0,1fr))',gap:'0.75rem',marginBottom:'1rem'}}>
              <KpiCard label={`Best Precision@${offline.protocol.k}`} value={`${(offline.recommended_weights.precision_at_k*100).toFixed(2)}%`} color={BLUE} />
              <KpiCard label={`Best Recall@${offline.protocol.k}`} value={`${(offline.recommended_weights.recall_at_k*100).toFixed(2)}%`} color={GREEN} />
              <KpiCard label={`Best F1@${offline.protocol.k}`} value={`${(offline.recommended_weights.f1_at_k*100).toFixed(2)}%`} color={GOLD} />
              <KpiCard label={`Best NDCG@${offline.protocol.k}`} value={`${((offline.recommended_weights.ndcg_at_k||0)*100).toFixed(2)}%`} color="#b98cff" />
              <KpiCard label="Diversity" value={`${((offline.recommended_weights.diversity_at_k||0)*100).toFixed(2)}%`} color="#f08aa5" />
              <KpiCard label="Catalog Coverage" value={`${((offline.recommended_weights.coverage||0)*100).toFixed(2)}%`} color="#55c7c1" />
            </div>
          )}
          <div style={{overflowX:'auto'}}>
            <table className="admin-table" style={{margin:0}}><thead><tr><th>Method</th><th>Precision@K</th><th>Recall@K</th><th>F1@K</th><th>NDCG@K</th><th>Diversity</th><th>Coverage</th><th>Users</th></tr></thead>
            <tbody>{offline.results.map(r=><tr key={r.method}><td>{r.method.replaceAll('_',' ')}</td><td>{(r.precision_at_k*100).toFixed(2)}%</td><td>{(r.recall_at_k*100).toFixed(2)}%</td><td style={{fontWeight:600,color:GOLD}}>{((r.f1_at_k||0)*100).toFixed(2)}%</td><td>{((r.ndcg_at_k||0)*100).toFixed(2)}%</td><td>{((r.diversity_at_k||0)*100).toFixed(2)}%</td><td>{((r.coverage||0)*100).toFixed(2)}%</td><td>{r.users_evaluated}</td></tr>)}</tbody></table>
          </div>
          <div style={{margin:'0.75rem 0 0',color:'var(--text-dim)',fontSize:'0.75rem',lineHeight:1.6}}>
            <div><strong>NDCG@K</strong> rewards relevant movies that appear nearer the top of the list.</div>
            <div><strong>Diversity</strong> is the average genre dissimilarity among recommended movies.</div>
            <div><strong>Coverage</strong> is the percentage of the movie catalog reached across evaluated users — naturally low with few registered users, and expected to rise as more people rate movies.</div>
          </div>
          {offline.recommended_weights && <p style={{marginTop:'0.75rem',color:'var(--text-muted)',fontSize:'0.8rem'}}>Best hybrid blend selected by F1@{offline.protocol.k}: <strong style={{color:GOLD}}>{Math.round(offline.recommended_weights.cf_weight*100)}% CF / {Math.round(offline.recommended_weights.cb_weight*100)}% CBF</strong></p>}
        </> : <p style={{color:'var(--text-muted)',fontSize:'0.82rem',margin:0}}>No saved metrics yet. Click <strong>Run Evaluation</strong> to calculate Precision@K, Recall@K, F1@K, NDCG@K, diversity, and coverage.</p>}
      </div>

      <div style={{ marginBottom: '1.75rem' }}>
        <div className="section-label" style={{ margin: '0 0 0.35rem' }}>Post-Recommendation Success Rate</div>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem' }}>Live behavioral metric showing how often recommended movies are later rated 3.5★ or higher</p>
      </div>

      <div className="admin-kpi-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: '1rem', marginBottom: '2rem' }}>
        <KpiCard label="Recommendations Logged" value={liveData.total_logged.toLocaleString()} color={GOLD} />
        <KpiCard label="Later Rated"            value={liveData.rated_count.toLocaleString()}  color={BLUE}  sub={`${liveData.rated_pct}% engagement`} />
        <KpiCard label="Highly Rated (≥ 3.5★)"  value={liveData.highly_rated.toLocaleString()} color={GREEN} sub={`${liveData.accuracy_pct}% positive rate`} />
        <KpiCard label="Avg Rating Given"        value={liveData.avg_user_rating > 0 ? `${liveData.avg_user_rating}★` : '—'} color="#c07a52" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem', marginBottom: '1.25rem' }}>
        <ChartCard title="Weekly Positive Recommendation Rate" subtitle="% of recommended movies later rated ≥ 3.5★ per week" height={210}>
          {liveData.weekly_accuracy.length > 1
            ? <Line data={weeklyChart} options={pctOpts} />
            : <div style={{ display:'flex',alignItems:'center',justifyContent:'center',height:'100%',color:'var(--text-dim)',fontSize:'0.82rem' }}>Not enough weekly data yet.</div>
          }
        </ChartCard>
        <ChartCard title="Positive Rate by Method" subtitle="% of recommended movies later rated highly by algorithm" height={210}>
          {liveData.by_method.length > 0
            ? <Bar data={methodChart} options={pctOpts} />
            : <div style={{ display:'flex',alignItems:'center',justifyContent:'center',height:'100%',color:'var(--text-dim)',fontSize:'0.82rem' }}>No method data yet.</div>
          }
        </ChartCard>
      </div>

      <ChartCard title="Score Correlation" subtitle="Model's predicted score vs actual user ratings — a rising line means the model ranks well" height={220}>
        {liveData.score_buckets.length > 1
          ? <Line data={scatterChart} options={corrOpts} />
          : <div style={{ display:'flex',alignItems:'center',justifyContent:'center',height:'100%',color:'var(--text-dim)',fontSize:'0.82rem' }}>Not enough rated recommendations yet.</div>
        }
      </ChartCard>

      {liveData.by_method.length > 0 && (
        <div style={{ marginTop: '1.25rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          <div style={{ padding: '1rem 1.5rem', borderBottom: '1px solid var(--border)', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-muted)' }}>Method Breakdown</div>
          <table className="admin-table accuracy-table" style={{ margin: 0 }}>
            <thead><tr><th>Method</th><th>Logged</th><th>Rated</th><th>Highly Rated</th><th>Positive Rate</th><th>Avg Rating</th></tr></thead>
            <tbody>
              {liveData.by_method.map(m => (
                <tr key={m.method}>
                  <td><span style={{ background: methodDim[m.method]||GOLD_DIM, color: methodColors[m.method]||GOLD, fontSize:'0.72rem', padding:'0.2rem 0.6rem', borderRadius:20, fontWeight:500 }}>{m.method}</span></td>
                  <td>{m.total}</td>
                  <td>{m.rated} <span style={{ color:'var(--text-dim)',fontSize:'0.75rem' }}>({m.total>0?Math.round(m.rated/m.total*100):0}%)</span></td>
                  <td>{m.highly_rated}</td>
                  <td>
                    <div style={{ display:'flex',alignItems:'center',gap:'0.5rem' }}>
                      <div style={{ flex:1,height:6,background:'var(--surface2)',borderRadius:20,overflow:'hidden',minWidth:60 }}>
                        <div style={{ height:'100%',width:`${m.accuracy_pct}%`,background:methodColors[m.method]||GOLD,borderRadius:20,transition:'width 0.6s ease' }} />
                      </div>
                      <span style={{ color:methodColors[m.method]||GOLD,fontWeight:600,fontSize:'0.85rem',minWidth:38 }}>{m.accuracy_pct}%</span>
                    </div>
                  </td>
                  <td style={{ color:GOLD,fontWeight:500 }}>{m.avg_rating>0?`${m.avg_rating}★`:'—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Users tab ──────────────────────────────────────────────────────────────

function UsersTab() {
  const { user: currentUser } = useAuth()
  const [users,setUsers]=useState([])
  const [total,setTotal]=useState(0)
  const [pages,setPages]=useState(1)
  const [page,setPage]=useState(1)
  const [search,setSearch]=useState('')
  const [loading,setLoading]=useState(true)

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get(`/api/admin/users?page=${page}&search=${encodeURIComponent(search)}`)
      setUsers(data.users); setTotal(data.total); setPages(data.total_pages)
    } finally { setLoading(false) }
  }, [page, search])

  useEffect(() => { fetchUsers() }, [fetchUsers])

  async function banUser(uid, banned) {
    if (!confirm(banned?'Unban?':'Ban?')) return
    const d = await api.post(`/api/admin/users/${uid}/ban`)
    setUsers(p => p.map(u => u.user_id===uid ? {...u,is_banned:d.banned} : u))
  }
  async function deleteUser(uid, name) {
    if (!confirm(`Delete "${name}"?`)) return
    await api.post(`/api/admin/users/${uid}/delete`)
    setUsers(p => p.filter(u => u.user_id!==uid)); setTotal(t=>t-1)
  }
  async function toggleAdmin(uid, isAdmin) {
    if (!confirm(isAdmin?'Remove admin?':'Grant admin?')) return
    const d = await api.post(`/api/admin/users/${uid}/toggle_admin`)
    setUsers(p => p.map(u => u.user_id===uid ? {...u,is_admin:d.is_admin} : u))
  }

  return (
    <div>
      <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1.5rem',flexWrap:'wrap',gap:'0.75rem' }}>
        <div className="section-label" style={{ margin:0 }}>All Users — {total} total</div>
        <input type="text" className="search-input" placeholder="Search username or email…"
          value={search} onChange={e=>{setSearch(e.target.value);setPage(1)}} style={{ width:240 }} />
      </div>
      {loading
        ? <div style={{textAlign:'center',padding:'3rem'}}><div className="spinner" style={{margin:'0 auto'}} /></div>
        : <div style={{overflowX:'auto'}}>
            <table className="admin-table users-table">
              <thead><tr><th>ID</th><th>Username</th><th>Email</th><th>Ratings</th><th>Joined</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>
                {users.map(u=>(
                  <tr key={u.user_id}>
                    <td style={{color:'var(--text-dim)'}}>{u.user_id}</td>
                    <td>{u.username}{u.is_admin&&<span style={{background:'rgba(100,160,255,0.1)',color:'#6aa0ff',fontSize:'0.68rem',padding:'0.15rem 0.5rem',borderRadius:20,marginLeft:4}}>admin</span>}</td>
                    <td style={{color:'var(--text-muted)'}}>{u.email}</td>
                    <td>{u.rating_count}</td>
                    <td style={{color:'var(--text-muted)',fontSize:'0.78rem'}}>{u.created_at?.slice(0,10)}</td>
                    <td><span style={{background:u.is_banned?'rgba(224,82,82,0.1)':'rgba(100,220,160,0.1)',color:u.is_banned?'#e05252':'#64dc9a',fontSize:'0.68rem',padding:'0.15rem 0.5rem',borderRadius:20,fontWeight:500}}>{u.is_banned?'Banned':'Active'}</span></td>
                    <td>
                      {u.user_id!==currentUser.user_id
                        ?<div style={{display:'flex',gap:'0.4rem',flexWrap:'wrap'}}>
                          <AdminBtn danger onClick={()=>banUser(u.user_id,u.is_banned)}>{u.is_banned?'Unban':'Ban'}</AdminBtn>
                          <AdminBtn onClick={()=>toggleAdmin(u.user_id,u.is_admin)}>{u.is_admin?'Remove Admin':'Make Admin'}</AdminBtn>
                          <AdminBtn danger onClick={()=>deleteUser(u.user_id,u.username)}>Delete</AdminBtn>
                        </div>
                        :<span style={{color:'var(--text-dim)',fontSize:'0.75rem'}}>You</span>
                      }
                    </td>
                  </tr>
                ))}
                {users.length===0&&<tr><td colSpan={7} style={{textAlign:'center',color:'var(--text-dim)',padding:'2rem'}}>No users found.</td></tr>}
              </tbody>
            </table>
            <AdminPagination page={page} totalPages={pages} onPage={setPage} total={total} />
          </div>
      }
    </div>
  )
}

// ── Movies tab ─────────────────────────────────────────────────────────────

function MoviesTab() {
  const [movies,setMovies]=useState([])
  const [total,setTotal]=useState(0)
  const [pages,setPages]=useState(1)
  const [page,setPage]=useState(1)
  const [search,setSearch]=useState('')
  const [loading,setLoading]=useState(true)
  const [modal,setModal]=useState(null)

  const fetchMovies = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.get(`/api/admin/movies?page=${page}&search=${encodeURIComponent(search)}`)
      setMovies(data.movies); setTotal(data.total); setPages(data.total_pages)
    } finally { setLoading(false) }
  }, [page, search])

  useEffect(() => { fetchMovies() }, [fetchMovies])

  async function deleteMovie(id, title) {
    if (!confirm(`Delete "${title}"?`)) return
    await api.post(`/api/admin/movies/${id}/delete`)
    setMovies(p=>p.filter(m=>m.movie_id!==id)); setTotal(t=>t-1)
  }
  async function saveMovie(form) {
    if (modal==='add') await api.post('/api/admin/movies/add', form)
    else await api.post(`/api/admin/movies/${modal.movie_id}/edit`, form)
    setModal(null); fetchMovies()
  }

  return (
    <div>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1.5rem',flexWrap:'wrap',gap:'0.75rem'}}>
        <div className="section-label" style={{margin:0}}>Movie Catalogue — {total} total</div>
        <div style={{display:'flex',gap:'0.5rem'}}>
          <input type="text" className="search-input" placeholder="Search title or genre…"
            value={search} onChange={e=>{setSearch(e.target.value);setPage(1)}} style={{width:220}} />
          <AdminBtn onClick={()=>setModal('add')}>＋ Add Movie</AdminBtn>
        </div>
      </div>
      {loading
        ?<div style={{textAlign:'center',padding:'3rem'}}><div className="spinner" style={{margin:'0 auto'}} /></div>
        :<div style={{overflowX:'auto'}}>
          <table className="admin-table movies-table">
            <thead><tr><th>ID</th><th>Title</th><th>Genres</th><th>Ratings</th><th>Avg ★</th><th>Poster</th><th>Actions</th></tr></thead>
            <tbody>
              {movies.map(m=>(
                <tr key={m.movie_id}>
                  <td style={{color:'var(--text-dim)'}}>{m.movie_id}</td>
                  <td style={{maxWidth:200}}>{m.title}</td>
                  <td style={{color:'var(--text-muted)',fontSize:'0.78rem',maxWidth:140}}>{(m.genres||'—').replace(/\|/g,' · ').slice(0,30)}</td>
                  <td>{m.rating_count||0}</td>
                  <td>{(m.avg_rating||0).toFixed(1)}</td>
                  <td>{m.poster_url?<img src={m.poster_url} style={{width:28,height:42,objectFit:'cover',borderRadius:3}} alt="" />:<span style={{color:'var(--text-dim)'}}>—</span>}</td>
                  <td><div style={{display:'flex',gap:'0.4rem'}}><AdminBtn onClick={()=>setModal(m)}>Edit</AdminBtn><AdminBtn danger onClick={()=>deleteMovie(m.movie_id,m.title)}>Delete</AdminBtn></div></td>
                </tr>
              ))}
              {movies.length===0&&<tr><td colSpan={7} style={{textAlign:'center',color:'var(--text-dim)',padding:'2rem'}}>No movies found.</td></tr>}
            </tbody>
          </table>
          <AdminPagination page={page} totalPages={pages} onPage={setPage} total={total} />
        </div>
      }
      {modal&&<MovieFormModal movie={modal==='add'?null:modal} onSave={saveMovie} onClose={()=>setModal(null)} />}
    </div>
  )
}

function MovieFormModal({ movie, onSave, onClose }) {
  const [form,setForm]=useState({ movie_id:movie?.movie_id||'', title:movie?.title||'', genres:movie?.genres||'', poster_url:movie?.poster_url||'', overview:movie?.overview||'' })
  const [saving,setSaving]=useState(false)
  const [error,setError]=useState('')

  async function handleSave() {
    if (!form.title.trim()){setError('Title required.');return}
    if (!movie&&!form.movie_id){setError('Movie ID required.');return}
    setSaving(true)
    try{await onSave({...form,movie_id:parseInt(form.movie_id)||undefined})}
    catch(e){setError(e.message)}
    finally{setSaving(false)}
  }

  return (
    <div className="modal-backdrop open" onClick={e=>{if(e.target===e.currentTarget)onClose()}}>
      <div className="modal-panel" style={{maxWidth:520}}>
        <button className="modal-close" onClick={onClose}>×</button>
        <div style={{padding:'1.75rem'}}>
          <h3 className="modal-title" style={{fontSize:'1.2rem',marginBottom:'1.25rem'}}>{movie?'Edit Movie':'Add Movie'}</h3>
          {error&&<div className="flash-msg flash-danger" style={{position:'static',marginBottom:'1rem',maxWidth:'100%'}}>{error}</div>}
          {!movie&&<div className="form-group"><label className="form-label">Movie ID</label><input type="number" className="form-input" value={form.movie_id} onChange={e=>setForm(f=>({...f,movie_id:e.target.value}))} /></div>}
          {[{key:'title',label:'Title'},{key:'genres',label:'Genres (pipe-separated)',placeholder:'Action|Drama'},{key:'poster_url',label:'Poster URL'}].map(f=>(
            <div key={f.key} className="form-group"><label className="form-label">{f.label}</label><input type="text" className="form-input" placeholder={f.placeholder||''} value={form[f.key]} onChange={e=>setForm(p=>({...p,[f.key]:e.target.value}))} /></div>
          ))}
          <div className="form-group"><label className="form-label">Overview</label><textarea className="form-input" rows={3} style={{resize:'vertical'}} value={form.overview} onChange={e=>setForm(f=>({...f,overview:e.target.value}))} /></div>
          <button className="btn-submit" style={{marginTop:'0.5rem'}} onClick={handleSave} disabled={saving}>{saving?'Saving…':'Save'}</button>
        </div>
      </div>
    </div>
  )
}

// ── ML Cache tab ───────────────────────────────────────────────────────────

function MLTab() {
  const [cacheRows,setCacheRows]=useState([])
  const [log,setLog]=useState('Ready.')
  const [loading,setLoading]=useState(true)

  useEffect(()=>{ api.get('/api/admin/stats').then(d=>setCacheRows(d.cache_rows)).finally(()=>setLoading(false)) },[])
  const addLog = msg => setLog(`[${new Date().toLocaleTimeString()}] ${msg}`)

  async function clearCache(key) {
    if (!confirm(`Clear ${key==='all'?'ALL':key}?`)) return
    addLog(`Clearing ${key}…`)
    try{ await api.post('/api/admin/cache/clear',{key:key==='all'?null:key}); addLog('✓ Cleared.'); setCacheRows([]) }
    catch(e){ addLog('✗ '+e.message) }
  }
  async function rebuildCache(key) {
    if (!confirm(`Rebuild ${key==='all'?'ALL':key}? (~20–60s)`)) return
    addLog(`Rebuilding ${key}…`)
    try{
      await api.post('/api/admin/cache/rebuild',{key})
      addLog('✓ Done.')
      const fresh = await api.get('/api/admin/stats')
      setCacheRows(fresh.cache_rows)
    }
    catch(e){ addLog('✗ '+e.message) }
  }

  return (
    <div>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1.5rem'}}>
        <div className="section-label" style={{margin:0}}>ML Model Cache</div>
        <div style={{display:'flex',gap:'0.5rem'}}>
          <AdminBtn onClick={()=>rebuildCache('all')}>🔄 Rebuild All</AdminBtn>
          <AdminBtn danger onClick={()=>clearCache('all')}>🗑 Clear All</AdminBtn>
        </div>
      </div>
      <div style={{background:'var(--surface)',border:'1px solid var(--border)',borderRadius:'var(--radius-lg)',padding:'1.5rem',marginBottom:'1.5rem'}}>
        {loading&&<div className="spinner" style={{margin:'0 auto'}}/>}
        {!loading&&cacheRows.length===0&&<p style={{color:'var(--text-dim)',fontSize:'0.875rem'}}>No models cached.</p>}
        {cacheRows.map(row=>(
          <div key={row.cache_key} style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'0.85rem 0',borderBottom:'1px solid var(--border)',gap:'1rem',flexWrap:'wrap'}}>
            <div>
              <div style={{fontFamily:'monospace',fontSize:'0.85rem',color:'var(--gold)',fontWeight:500}}>{row.cache_key}</div>
              <div style={{fontSize:'0.75rem',color:'var(--text-muted)',display:'flex',gap:'1.5rem',marginTop:'0.25rem'}}>
                <span>Hash: {row.data_hash.slice(0, 12)}…</span>
                <span>Size: {(row.blob_size / 1024 / 1024).toFixed(1)} MB</span>
                <span>Built: {row.built_at}</span>
                <span style={{ color: 'var(--gold)' }}>By: {row.built_by}</span>
              </div>
            </div>
            <div style={{display:'flex',gap:'0.5rem'}}>
              <AdminBtn onClick={()=>rebuildCache(row.cache_key)}>Rebuild</AdminBtn>
              <AdminBtn danger onClick={()=>clearCache(row.cache_key)}>Clear</AdminBtn>
            </div>
          </div>
        ))}
      </div>
      <div style={{background:'var(--surface)',border:'1px solid var(--border)',borderRadius:'var(--radius-lg)',padding:'1.5rem'}}>
        <div style={{fontSize:'0.8rem',textTransform:'uppercase',letterSpacing:'0.08em',color:'var(--text-muted)',marginBottom:'0.75rem'}}>Action Log</div>
        <div style={{fontFamily:'monospace',fontSize:'0.8rem',color:'var(--text-muted)'}}>{log}</div>
      </div>
    </div>
  )
}

// ── Rec Logs tab ───────────────────────────────────────────────────────────

function RecsTab() {
  const [logs,setLogs]=useState([])
  const [loading,setLoading]=useState(true)
  useEffect(()=>{ api.get('/api/admin/rec-logs').then(d=>setLogs(d.logs)).finally(()=>setLoading(false)) },[])
  const mc=m=>m==='collaborative'?BLUE:m==='content'?GREEN:GOLD
  const mb=m=>m==='collaborative'?BLUE_DIM:m==='content'?GREEN_DIM:'var(--gold-dim)'
  return (
    <div>
      <div className="section-label">Recent Recommendation Logs</div>
      {loading?<div style={{textAlign:'center',padding:'3rem'}}><div className="spinner" style={{margin:'0 auto'}}/></div>
        :<div style={{overflowX:'auto'}}>
          <table className="admin-table logs-table">
            <thead><tr><th>User</th><th>Movie</th><th>Score</th><th>Method</th><th>Time</th></tr></thead>
            <tbody>
              {logs.map((r,i)=>(
                <tr key={i}>
                  <td>{r.username}</td>
                  <td style={{color:'var(--text-muted)',maxWidth:200}}>{r.title?.slice(0,35)}</td>
                  <td>{r.score?.toFixed(3)}</td>
                  <td><span style={{background:mb(r.method),color:mc(r.method),fontSize:'0.68rem',padding:'0.15rem 0.5rem',borderRadius:20,fontWeight:500}}>{r.method}</span></td>
                  <td style={{color:'var(--text-dim)',fontSize:'0.78rem'}}>{r.created_at?.slice(0,19)}</td>
                </tr>
              ))}
              {logs.length===0&&<tr><td colSpan={5} style={{textAlign:'center',color:'var(--text-dim)',padding:'2rem'}}>No logs yet.</td></tr>}
            </tbody>
          </table>
        </div>
      }
    </div>
  )
}