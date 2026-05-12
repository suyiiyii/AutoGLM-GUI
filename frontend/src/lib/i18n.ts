import { en } from './locales/en'
import { zh } from './locales/zh'

export type Locale = 'en' | 'zh'

export type Translations = typeof en

export const translations: Record<Locale, Translations> = {
  en,
  zh,
}

export const localeNames: Record<Locale, string> = {
  en: 'EN',
  zh: '中文',
}
