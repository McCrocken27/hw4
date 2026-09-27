import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './auth'
import { CartProvider } from './cart'
import '@fontsource/graduate'
import '@fontsource/oswald/500.css'
import '@fontsource/oswald/700.css'
import '@fontsource/barlow/400.css'
import '@fontsource/barlow/600.css'
import '@fontsource/barlow/700.css'
import './index.css'
import './storefront.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <CartProvider>
          <App />
        </CartProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
