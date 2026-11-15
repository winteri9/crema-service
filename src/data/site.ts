/**
 * Факты сайта — единственный источник правды.
 * Принцип 1 (~/.dsh/rules/architecture.md): в разметке нет ни одного фактического значения.
 *
 * Источник: бриф клиента (m00003). Всё, чего в брифе нет, — заглушка «—»:
 * см. docs/PLACEHOLDERS.md. Цифры, сроки и гарантии не выдумываются.
 */

export const SITE = {
  brand: 'КРЕМА',
  suffix: 'СЕРВИС',
  monogram: 'КР',
  city: 'Москва',
  year: 2026,
  locale: 'ru_RU',
  title: 'КРЕМА — сервис кофемашин в Москве',
  description:
    'Диагностика, ремонт и обслуживание профессионального оборудования. Кофейни, рестораны, офисы.',
  url: 'https://winteri9.github.io/crema-service/', // TODO: домен проекта
  draft: true,
} as const;

/**
 * Контакты — заглушки: клиент просил не показывать реальные данные.
 * Если поле «—», оно всё равно выводится: так видно место под факт.
 */
export const CONTACTS = {
  phone: '—',
  email: '—',
  address: '—',
  inn: '—',
  hours: '—',
  telegram: 'https://t.me/winteri9',
  handle: '@winteri9',
} as const;

/** Навигация. href — якоря на главной. */
export const NAV = [
  { label: 'Анатомия', href: '#anatomy' },
  { label: 'Услуги', href: '#services' },
  { label: 'Процесс', href: '#process' },
] as const;
