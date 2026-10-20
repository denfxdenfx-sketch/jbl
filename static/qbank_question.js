(function () {
  'use strict';

  // ─────────────────────────────────────────────────────────────
  // DOM refs
  // ─────────────────────────────────────────────────────────────
  const root = document.getElementById('qroot');
  if (!root) return;

  const total       = parseInt(root.dataset.total, 10);
  const reviewMode  = root.dataset.review === '1';
  const completeUrl = root.dataset.completeUrl;
  const topicId     = root.dataset.topicId;
  const categoryId  = root.dataset.categoryId;
  const subjectId   = root.dataset.subjectId;
  const catsRaw     = root.dataset.cats || '';
  const cats        = catsRaw
    ? catsRaw.split(',').map(x => parseInt(x, 10)).filter(n => !isNaN(n))
    : [];

  const qcards         = Array.from(document.querySelectorAll('.qcard'));
  const prevBtn        = document.getElementById('prev-btn');
  const nextBtn        = document.getElementById('next-btn');
  const revealAllInput = document.getElementById('reveal-all');
  const modal          = document.getElementById('complete-modal');
  const cancelComplete = document.getElementById('cancel-complete');
  const stayComplete   = document.getElementById('stay-complete');
  const nextComplete   = document.getElementById('next-complete');

  let current = 0;

  // ─────────────────────────────────────────────────────────────
  // Navigation between questions
  // ─────────────────────────────────────────────────────────────
  function show(i) {
    current = i;

    qcards.forEach((el, idx) => {
      el.hidden = idx !== i;
    });

    prevBtn.disabled = i === 0;

    const isLast = i === total - 1;

    if (isLast) {
      // On the last question, both modes open the dialog
      nextBtn.textContent = reviewMode ? 'Move to next →' : 'Complete Section';
      nextBtn.disabled = false;
      nextBtn.onclick = openCompleteModal;
    } else {
      nextBtn.textContent = 'Next →';
      nextBtn.disabled = false;
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
  // NOTE: Do NOT addEventListener on nextBtn — its onclick is set inside show().

  // ─────────────────────────────────────────────────────────────
  // Complete Section dialog
  // ─────────────────────────────────────────────────────────────
  function openCompleteModal() {
    modal.hidden = false;
  }

  function closeCompleteModal() {
    modal.hidden = true;
  }

  cancelComplete.addEventListener('click', closeCompleteModal);

  // Click the dimmed backdrop to close
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeCompleteModal();
  });

  // "Stay on this topic"
  stayComplete.addEventListener('click', async () => {
    closeCompleteModal();

    if (reviewMode) {
      // Already complete — nothing to do, just close.
      return;
    }

    const next = await completeSectionRequest();
    if (next === false) return;   // error already alerted

    const catsParam = cats.length ? `?cats=${cats.join(',')}` : '';
    window.location.replace(
      `/qbank/topics/${topicId}/categories/${categoryId}/review${catsParam}`);
  });

  // "Move to next section"
  nextComplete.addEventListener('click', async () => {
    closeCompleteModal();

    const next = await completeSectionRequest();
    if (next === false) return;   // error already alerted

    const catsParam = cats.length ? `?cats=${cats.join(',')}` : '';

    if (next) {
      window.location.replace(
        `/qbank/topics/${next.topic_id}/categories/${next.category_id}/questions${catsParam}`);
    } else {
      window.location.replace(`/qbank/subjects/${subjectId}/topics${catsParam}`);
    }
  });

  // POST to the complete endpoint.
  // Returns:
  //   object {topic_id, category_id} — there's a next step
  //   null — this was the last section
  //   false — network/server error
  async function completeSectionRequest() {
    try {
      const res = await fetch(completeUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cats }),
      });
      const data = await res.json();
      if (!data.success) {
        alert(data.message || 'Failed to complete section');
        return false;
      }
      return data.next_step || null;
    } catch (e) {
      alert('Network error: ' + e);
      return false;
    }
  }

  // ─────────────────────────────────────────────────────────────
  // Reveal-all toggle
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
  // Per-question answer toggle
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