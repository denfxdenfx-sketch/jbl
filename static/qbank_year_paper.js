(function () {
  'use strict';

  const root = document.getElementById('yroot');
  if (!root) return;

  const total      = parseInt(root.dataset.total, 10);
  const reviewMode = root.dataset.review === '1';
  const year       = root.dataset.year;
  const examType   = root.dataset.examType;
  const goalId     = root.dataset.goalId;
  const subjectId  = root.dataset.subjectId;

  const qcards         = Array.from(document.querySelectorAll('.qcard'));
  const prevBtn        = document.getElementById('prev-btn');
  const nextBtn        = document.getElementById('next-btn');
  const revealAllInput = document.getElementById('reveal-all');
  const modal          = document.getElementById('complete-modal');
  const cancelComplete = document.getElementById('cancel-complete');
  const stayComplete   = document.getElementById('stay-complete');
  const nextComplete   = document.getElementById('next-complete');

  let current = 0;
  let pendingCompleteUrl = null;

  // ─────────────────────────────────────────────────────────────
  // Navigation
  // ─────────────────────────────────────────────────────────────
  function show(i) {
    current = i;
    qcards.forEach((el, idx) => { el.hidden = idx !== i; });
    prevBtn.disabled = i === 0;

    const isLast = i === total - 1;
    const card = qcards[i];

    if (isLast) {
      nextBtn.textContent = reviewMode ? 'Finish' : 'Complete Section';
      nextBtn.onclick = () => {
        if (reviewMode) {
          window.location.href = `/qbank/years/${year}/${examType}/subjects/${subjectId}/topics`;
        } else {
          pendingCompleteUrl = card.dataset.completeUrl;
          openCompleteModal();
        }
      };
    } else {
      nextBtn.textContent = 'Next →';
      nextBtn.onclick = nextQuestion;
    }
  }

  function nextQuestion() {
    if (current < total - 1) show(current + 1);
  }
  function prevQuestion() {
    if (current > 0) show(current - 1);
  }

  prevBtn.addEventListener('click', prevQuestion);

  // ─────────────────────────────────────────────────────────────
  // Complete dialog
  // ─────────────────────────────────────────────────────────────
  function openCompleteModal()  { modal.hidden = false; }
  function closeCompleteModal() { modal.hidden = true; }

  cancelComplete.addEventListener('click', closeCompleteModal);
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeCompleteModal();
  });

  stayComplete.addEventListener('click', async () => {
    closeCompleteModal();
    if (!pendingCompleteUrl) return;
    const data = await postComplete(pendingCompleteUrl);
    if (data === false) return;

    if (data.papers_completed && data.papers_completed.length > 0) {
      const labels = data.papers_completed.map(p => `${p.year} ${p.type}`).join(', ');
      alert(`Paper complete: ${labels}`);
      window.location.href = '/qbank/years';
      return;
    }

    window.location.href = `/qbank/years/${year}/${examType}/subjects/${subjectId}/topics`;
  });

  nextComplete.addEventListener('click', async () => {
    closeCompleteModal();
    if (!pendingCompleteUrl) return;
    const data = await postComplete(pendingCompleteUrl);
    if (data === false) return;

    if (data.papers_completed && data.papers_completed.length > 0) {
      const labels = data.papers_completed.map(p => `${p.year} ${p.type}`).join(', ');
      alert(`Paper complete: ${labels}`);
      window.location.href = '/qbank/years';
      return;
    }

    if (data.next_step) {
      window.location.href =
        `/qbank/years/${year}/${examType}/topics/${data.next_step.topic_id}/categories/${data.next_step.category_id}`;
      return;
    }

    window.location.href = `/qbank/years/${year}/${examType}/subjects/${subjectId}/topics`;
  });

  async function postComplete(url) {
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          year: parseInt(year, 10),
          type: examType,
        }),
      });
      const data = await res.json();
      if (!data.success) {
        alert(data.message || 'Failed to complete section');
        return false;
      }
      return data;
    } catch (e) {
      alert('Network error: ' + e);
      return false;
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Reveal-all
  // ─────────────────────────────────────────────────────────────
  const REVEAL_KEY = 'qbank_reveal_all';

  function applyRevealState() {
    const on = revealAllInput.checked;
    document.querySelectorAll('.answer').forEach(el => {
      el.classList.toggle('hidden', !on);
    });
    document.querySelectorAll('.show-answer-btn').forEach(b => {
      b.style.visibility = on ? 'hidden' : 'visible';
    });
  }

  if (localStorage.getItem(REVEAL_KEY) === '1') {
    revealAllInput.checked = true;
  }
  if (reviewMode) {
    revealAllInput.checked = true;
    revealAllInput.disabled = true;
  }
  revealAllInput.addEventListener('change', () => {
    localStorage.setItem(REVEAL_KEY, revealAllInput.checked ? '1' : '0');
    applyRevealState();
  });

  // ─────────────────────────────────────────────────────────────
  // Show/hide answers per question
  // ─────────────────────────────────────────────────────────────
  document.querySelectorAll('.show-answer-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const i = parseInt(btn.dataset.index, 10);
      const ans = document.getElementById('ans-' + i);
      ans.classList.toggle('hidden');
      btn.textContent = ans.classList.contains('hidden') ? 'Show answer' : 'Hide answer';
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Notes
  // ─────────────────────────────────────────────────────────────
  document.querySelectorAll('.save-notes-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const qid = btn.dataset.qid;
      const i = btn.dataset.index;
      const textarea = document.getElementById('notes-' + i);
      const status = document.getElementById('save-status-' + i);

      try {
        const res = await fetch(`/qbank/questions/${qid}/note`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ notes: textarea.value }),
        });
        const data = await res.json();
        status.textContent = data.success ? 'Saved ✓' : 'Failed';
        if (data.success) setTimeout(() => { status.textContent = ''; }, 2000);
      } catch (e) {
        status.textContent = 'Failed';
      }
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Bookmarks
  // ─────────────────────────────────────────────────────────────
  document.querySelectorAll('.bookmark-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const qid = btn.dataset.qid;
      try {
        const res = await fetch(`/qbank/questions/${qid}/bookmark`, { method: 'POST' });
        const data = await res.json();
        if (data.success) btn.textContent = data.bookmarked ? '⭐' : '☆';
      } catch (e) { /* ignore */ }
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Init
  // ─────────────────────────────────────────────────────────────
  applyRevealState();
  show(0);
})();