import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'

// Import your existing CSS from Flask static folder
// During dev, Vite proxies to Flask so this path works
// In production, Flask serves it directly
const link = document.createElement('link')
link.rel  = 'stylesheet'
link.href = '/static/css/style.css'
document.head.appendChild(link)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>
)