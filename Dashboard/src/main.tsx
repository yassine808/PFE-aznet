import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from '@/App'
import { I18nProvider } from '@/lib/i18n'
import { SettingsProvider } from '@/lib/settings'
import { ThemeProvider } from '@/lib/theme'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <I18nProvider>
        <SettingsProvider>
          <App />
        </SettingsProvider>
      </I18nProvider>
    </ThemeProvider>
  </StrictMode>,
)
