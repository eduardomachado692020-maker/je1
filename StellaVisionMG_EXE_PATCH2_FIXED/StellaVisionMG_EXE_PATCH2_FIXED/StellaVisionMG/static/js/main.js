// Tema escuro/claro
// Aplica o tema salvo no localStorage e permite alternar via botões com classe
// 'theme-toggle'. O corpo recebe classes bootstrap apropriadas e a navbar
// é ajustada para garantir contraste.

function applyTheme(theme) {
  const body = document.body;
  const nav = document.querySelector('nav.navbar');
  if (!body || !nav) return;
  if (theme === 'dark') {
    body.classList.add('bg-dark', 'text-white');
    body.classList.remove('bg-light');
    body.dataset.theme = 'dark';
    // Navbar: usa classes do Bootstrap para tema escuro
    nav.classList.add('bg-dark');
    nav.style.background = '';
  } else {
    body.classList.remove('bg-dark', 'text-white');
    body.classList.add('bg-light');
    body.dataset.theme = 'light';
    nav.classList.remove('bg-dark');
    nav.style.background = '#2563eb';
  }
  // Ajusta texto de botões
  document.querySelectorAll('.theme-toggle').forEach((btn) => {
    btn.textContent = theme === 'dark' ? 'Modo Claro' : 'Modo Escuro';
  });
}

document.addEventListener('DOMContentLoaded', () => {
  // Tema inicial
  const saved = localStorage.getItem('theme') || 'light';
  applyTheme(saved);
  // Listener para botões
  document.querySelectorAll('.theme-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const current = document.body.dataset.theme || 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      localStorage.setItem('theme', next);
      applyTheme(next);
    });
  });
});
