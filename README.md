# VOIDCODE — шаблон клиентского сайта (Astro)

Чистый скелет без клиентских фактов. Собран по принципам `~/.dsh/rules/architecture.md`
(разбор проекта APM «Индекс»).

**В шаблоне намеренно нет кода.** Есть структура, контракты в шапках файлов и `TODO`.
Контент и вёрстка появляются после утверждения плана — не раньше.

## Новый проект за 4 шага

```powershell
Copy-Item -Recurse "C:\KworkProjects\_templates\voidcode-astro" "C:\KworkProjects\<проект>"
cd "C:\KworkProjects\<проект>"
npm install
Copy-Item .env.example .env      # вписать UNSPLASH_ACCESS_KEY
```

Проверка, что скелет живой:

```powershell
npm run dev          # http://localhost:4321 — заглушки секций
npm run verify       # 9 проверок: типы, сборка, контраст, скриншоты, структура
```

## Что где

```
src/data/                 факты: site.ts, services.ts (растёт по проекту)
src/components/sections/  секции: Hero, Services, Contact (по одной на блок макета)
src/layouts/              BaseLayout — <html>/<head>/слот
src/pages/                index.astro — порядок секций объявлен здесь
src/styles/               tokens.css (цвет только здесь), base.css
tools/                    verify, contrast, shot, predeploy-check, fetch_photos.py
src/lib/                  format.ts (числа, склонения), images.ts (фото + атрибуция)
.claude/                  settings.json (запреты), rules/, launch.json на 4321
HANDOFF.md                передача проекта: как переделать, что не сделано, история
assets/photos/            скачанные фото + photos.json (атрибуция Unsplash)
plans/                    план проекта с фазами и kill list
retrospectives/           ретроспективы по вехам
docs/                     ARCHITECTURE.md — карта кода и решения
```

## Фото

```powershell
python tools/fetch_photos.py "modern real estate interior" -n 5
```

Скачивает в `assets/photos/`, пишет `photos.json` с автором и ссылками.
Атрибуция обязательна — вывести автора в интерфейсе или в кредитах.
Нейрогенерация — только крайний fallback (правило в `~/.dsh/rules/architecture.md`).

## Порядок работы

1. Прочитать `AGENTS.md` в корне — там порядок чтения.
2. Написать `plans/YYYY-MM-DD-<slug>.md`, вывести план в чат на утверждение.
3. Заполнить `src/data/`, затем секции, затем токены.
4. Проверить: `npm run build` → контраст → скриншоты 1440 / 390 / `--reduce`.
