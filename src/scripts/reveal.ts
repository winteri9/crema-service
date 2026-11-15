/**
 * Появление элементов при скролле.
 *
 * Работает без разметки: селекторы ниже сами находят кандидатов, ставит
 * data-reveal и индекс для стаггера. Исключены сцена просмотрщика и подписи
 * деталей — там своя анимация, чужая их ломает.
 */

const SELECTORS = [
  '.hero__eyebrow',
  '.hero__title',
  '.hero__lead',
  '.hero__actions',
  '.hero__meta',
  '.sec__num',
  '.h2',
  '.lead',
  '.sec .rule',
  '.sec ol > li',
  '.sec ul > li',
  '.sec figure',
  '.anatomy__list > li',
  '.footer__col',
];

const SKIP = new Set(['.viewer__label', '.viewer__leader', '.viewer__leader-dot']);
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

function insideStage(el: Element): boolean {
  return !!el.closest('[data-viewer-stage]') || !!el.closest('.anatomy__labels');
}

function run(): void {
  const nodes: HTMLElement[] = [];

  for (const sel of SELECTORS) {
    document.querySelectorAll<HTMLElement>(sel).forEach((el) => {
      if (SKIP.has('.' + el.className.split(' ')[0])) return;
      if (insideStage(el)) return;
      if (el.hasAttribute('data-reveal')) return;
      el.setAttribute('data-reveal', '');
      nodes.push(el);
    });
  }

  if (!nodes.length) return;

  if (reduced() || !('IntersectionObserver' in window)) {
    nodes.forEach((el) => el.classList.add('is-in'));
    return;
  }

  // стаггер внутри каждой группы соседей
  const groups = new Map<Element | null, HTMLElement[]>();
  for (const el of nodes) {
    const key = el.parentElement;
    const list = groups.get(key) ?? [];
    list.push(el);
    groups.set(key, list);
  }
  for (const list of groups.values()) {
    const max = Math.min(list.length, 6);
    list.forEach((el, i) => {
      el.style.setProperty('--i', String(Math.min(i, max - 1)));
    });
  }

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add('is-in');
        io.unobserve(entry.target);
      }
    },
    { rootMargin: '0px 0px -12% 0px', threshold: 0.12 },
  );

  nodes.forEach((el) => io.observe(el));
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', run, { once: true });
} else {
  run();
}
