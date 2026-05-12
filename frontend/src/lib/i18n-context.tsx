import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useMemo,
  type ReactNode,
} from 'react'
import { translations, localeNames, type Locale, type Translations } from './i18n'

interface I18nContextType {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: Translations
  isRtl: boolean
}

const I18nContext = createContext<I18nContextType | undefined>(undefined)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>('en')

  useEffect(() => {
    const savedLocale = localStorage.getItem('locale') as Locale | null
    let initialLocale: Locale
    if (savedLocale && (savedLocale === 'en' || savedLocale === 'zh')) {
      initialLocale = savedLocale
    } else {
      const browserLang = navigator.language.split('-')[0]
      initialLocale = browserLang === 'zh' ? 'zh' : 'en'
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocaleState(initialLocale)
  }, [])

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale)
    localStorage.setItem('locale', newLocale)
    document.documentElement.lang = newLocale
  }

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      t: translations[locale],
      isRtl: false,
    }),
    [locale],
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useI18n() {
  const context = useContext(I18nContext)
  if (!context) {
    throw new Error('useI18n must be used within an I18nProvider')
  }
  return context
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLocale() {
  const { locale, setLocale } = useI18n()
  return { locale, setLocale, localeName: localeNames[locale] }
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTranslation() {
  const { t } = useI18n()
  return t
}
