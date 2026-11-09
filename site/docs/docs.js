const sidebar = document.querySelector('.docs-sidebar');
const currentPage = sidebar?.querySelector('[aria-current="page"]');
const mobileNavigation = window.matchMedia('(max-width: 860px)');

function centerCurrentPage() {
  if (!sidebar || !currentPage || !mobileNavigation.matches) return;
  const sidebarBounds = sidebar.getBoundingClientRect();
  const currentBounds = currentPage.getBoundingClientRect();
  sidebar.scrollLeft += currentBounds.left - sidebarBounds.left
    - (sidebar.clientWidth - currentBounds.width) / 2;
}

centerCurrentPage();
mobileNavigation.addEventListener('change', centerCurrentPage);
window.addEventListener('resize', centerCurrentPage);
const translateDocs = (text) => window.siadaDocsI18n?.translate(text) ?? text;
function updateHeaderHeight() {
  const height = document.querySelector('.docs-header')?.getBoundingClientRect().height;
  if (height) document.body.style.setProperty('--docs-header-height', `${height}px`);
}
updateHeaderHeight();
window.addEventListener('resize', updateHeaderHeight);
window.addEventListener('siada-language-change', () => {
  updateHeaderHeight();
  centerCurrentPage();
});

const announcement = document.createElement('p');
announcement.className = 'docs-visually-hidden';
announcement.setAttribute('role', 'status');
document.body.append(announcement);
let announcementMessage = '';
function announce(message) {
  announcementMessage = message;
  announcement.textContent = translateDocs(message);
}
window.addEventListener('siada-language-change', () => {
  announcement.textContent = translateDocs(announcementMessage);
});

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Older or restricted browser contexts may still support local copying.
    }
  }

  const previousFocus = document.activeElement;
  const field = document.createElement('textarea');
  field.className = 'docs-copy-fallback';
  field.value = text;
  field.readOnly = true;
  document.body.append(field);
  field.select();
  try {
    if (!document.execCommand('copy')) throw new Error('Clipboard unavailable');
  } finally {
    field.remove();
    previousFocus?.focus({ preventScroll: true });
  }
}

document.querySelectorAll('.docs-code').forEach((block) => {
  const label = block.querySelector('.docs-code-label');
  const code = block.querySelector('pre code');
  if (!label || !code) return;

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'docs-copy';
  const labelText = () => [...label.childNodes]
    .filter((node) => node !== button).map((node) => node.textContent).join('').trim();
  let buttonMessage = '复制';
  function updateCopyLabel() {
    button.textContent = translateDocs(buttonMessage);
    button.setAttribute('aria-label', window.siadaDocsI18n?.getLanguage() === 'en'
      ? `Copy ${labelText()} code` : `复制${labelText()}代码`);
  }
  updateCopyLabel();
  window.addEventListener('siada-language-change', updateCopyLabel);
  label.append(button);
  let resetTimer;

  button.addEventListener('click', async () => {
    clearTimeout(resetTimer);
    announce('');
    button.disabled = true;
    try {
      await copyText(code.textContent);
      buttonMessage = '已复制';
      updateCopyLabel();
      button.setAttribute('data-copied', '');
      announce('代码已复制到剪贴板');
    } catch {
      const range = document.createRange();
      range.selectNodeContents(code);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
      buttonMessage = '请手动复制';
      updateCopyLabel();
      announce('未能访问剪贴板，代码已选中，请手动复制');
    } finally {
      button.disabled = false;
      button.focus({ preventScroll: true });
      resetTimer = setTimeout(() => {
        buttonMessage = '复制';
        updateCopyLabel();
        button.removeAttribute('data-copied');
      }, 2000);
    }
  });
});

const tocLinks = [...document.querySelectorAll('.docs-toc a[href^="#"]')];
const tocSections = tocLinks.map((link) => ({
  link,
  section: document.getElementById(decodeURIComponent(link.hash.slice(1))),
})).filter(({ section }) => section);

if (tocSections.length) {
  let scheduled = false;

  function updateToc() {
    scheduled = false;
    const header = document.querySelector('.docs-header');
    const offset = (header?.getBoundingClientRect().height || 76) + 48;
    let active = tocSections[0];
    for (const item of tocSections) {
      if (item.section.getBoundingClientRect().top <= offset) active = item;
    }
    const requested = tocSections.find(({ link }) => link.hash === location.hash);
    const atPageEnd = scrollY + innerHeight >= document.documentElement.scrollHeight - 2;
    if (atPageEnd && requested) {
      const top = requested.section.getBoundingClientRect().top;
      if (top >= offset && top < innerHeight) active = requested;
    }
    for (const item of tocSections) {
      if (item === active) item.link.setAttribute('aria-current', 'location');
      else item.link.removeAttribute('aria-current');
    }
  }

  window.addEventListener('scroll', () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(updateToc);
  }, { passive: true });
  window.addEventListener('resize', updateToc);
  window.addEventListener('hashchange', updateToc);
  window.addEventListener('siada-language-change', updateToc);
  updateToc();
}