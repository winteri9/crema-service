/**
 * Секция 06 «Парк» — бегущая строка брендов, с которыми работает сервис.
 * Источник: список из брифа/концепта (m00044). draft: клиент не подтверждал,
 * что обслуживает все перечисленные марки — строка идёт как заявка концепта.
 */

export const FLEET = {
  n: '06',
  title: 'С чем работаем',
  draft: true,
  items: [
    'La Marzocco',
    'Rocket',
    'ECM',
    'Profitec',
    'Nuova Simonelli',
    'Victoria Arduino',
    'Gaggia',
    'Jura',
    "De'Longhi",
    'WMF',
    'Franke',
    'Schaerer',
  ],
} as const;
