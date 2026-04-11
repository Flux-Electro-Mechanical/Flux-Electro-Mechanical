document.addEventListener('DOMContentLoaded', function () {
  const revealItems = document.querySelectorAll('.reveal');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) entry.target.classList.add('visible');
    });
  }, { threshold: 0.14 });
  revealItems.forEach(item => observer.observe(item));

  const menuBtn = document.querySelector('[data-menu-toggle]');
  const mobileMenu = document.querySelector('[data-mobile-menu]');
  if (menuBtn && mobileMenu) {
    menuBtn.addEventListener('click', () => {
      mobileMenu.classList.toggle('open');
      document.body.classList.toggle('menu-open');
    });
    mobileMenu.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        mobileMenu.classList.remove('open');
        document.body.classList.remove('menu-open');
      });
    });
  }

  const tabs = document.querySelectorAll('[data-tab-btn]');
  const panels = document.querySelectorAll('[data-tab-panel]');
  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tabBtn;
      tabs.forEach(b => b.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const panel = document.querySelector('[data-tab-panel="' + target + '"]');
      if (panel) panel.classList.add('active');
    });
  });

  const faqButtons = document.querySelectorAll('.faq button');
  faqButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const item = btn.closest('.faq');
      item.classList.toggle('open');
    });
  });

  const track = document.querySelector('[data-testimonial-track]');
  if (track) {
    const slides = track.querySelectorAll('.testimonial');
    let index = 0;
    const update = () => track.style.transform = 'translateX(-' + (index * 100) + '%)';
    const prev = document.querySelector('[data-testimonial-prev]');
    const next = document.querySelector('[data-testimonial-next]');
    if (prev) prev.addEventListener('click', () => { index = (index - 1 + slides.length) % slides.length; update(); });
    if (next) next.addEventListener('click', () => { index = (index + 1) % slides.length; update(); });
    setInterval(() => {
      index = (index + 1) % slides.length;
      update();
    }, 5000);
  }
});
