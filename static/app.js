// ═══════════════════════════════════════════════════
// Sidebar toggle
// ═══════════════════════════════════════════════════
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  if (!sidebar) return;
  sidebar.classList.toggle('open');
  overlay.classList.toggle('open');
}

function closeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  if (!sidebar) return;
  sidebar.classList.remove('open');
  overlay.classList.remove('open');
}

// ═══════════════════════════════════════════════════
// Auto-close sidebar on nav link clicks
// ═══════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.sidebar .nav-item').forEach(link => {
    link.addEventListener('click', () => closeSidebar());
  });
});

// ═══════════════════════════════════════════════════
// Esc key closes sidebar
// ═══════════════════════════════════════════════════
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeSidebar();
});