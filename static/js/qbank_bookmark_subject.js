(function () {
    'use strict';
  
    const QUESTIONS = window.QUESTIONS || [];
    const qlist = document.getElementById('qlist');
    const detail = document.getElementById('detail');
  
    if (!qlist || !detail) return;
  
    let currentIndex = 0;
  
    function renderDetail(i) {
      currentIndex = i;
      const q = QUESTIONS[i];
      if (!q) return;
  
      // Highlight the active item in the list
      document.querySelectorAll('.qlist-item').forEach((el, idx) => {
        el.classList.toggle('active', idx === i);
      });
  
      // Build the detail HTML
      let html = '';
  
      html += `<div class="detail-meta">
        ${escapeHtml(q.category_label)} · ${escapeHtml(q.topic_name)} · Question ${i + 1} of ${QUESTIONS.length}
      </div>`;
  
      html += `<div class="detail-qtext">${escapeHtml(q.text)}</div>`;
  
      if (q.image_path) {
        html += `<img class="detail-image" src="/static/uploads/${escapeHtml(q.image_path)}" alt="">`;
      }
  
      html += `<div class="detail-answer">
        <strong>Answer:</strong>
        <div>${escapeHtml(q.answer)}</div>`;
  
      if (q.answer_image_path) {
        html += `<img class="detail-image" src="/static/uploads/${escapeHtml(q.answer_image_path)}" alt="">`;
      }
  
      html += `</div>`;
  
      html += `
        <div class="detail-nav">
          <button class="btn" id="detail-prev" ${i === 0 ? 'disabled' : ''}>← Previous</button>
          <div style="display:flex; gap:8px;">
            <button class="btn remove-btn" id="detail-remove" data-qid="${q.id}">Remove bookmark</button>
            <button class="btn btn-primary" id="detail-next" ${i === QUESTIONS.length - 1 ? 'disabled' : ''}>Next →</button>
          </div>
        </div>
      `;
  
      detail.innerHTML = html;
  
      // Attach handlers for the buttons we just rendered
      const prevBtn = document.getElementById('detail-prev');
      const nextBtn = document.getElementById('detail-next');
      const removeBtn = document.getElementById('detail-remove');
  
      if (prevBtn) prevBtn.addEventListener('click', () => {
        if (currentIndex > 0) renderDetail(currentIndex - 1);
      });
  
      if (nextBtn) nextBtn.addEventListener('click', () => {
        if (currentIndex < QUESTIONS.length - 1) renderDetail(currentIndex + 1);
      });
  
      if (removeBtn) removeBtn.addEventListener('click', () => removeBookmark(q.id));
    }
  
    async function removeBookmark(qid) {
      try {
        const res = await fetch(`/qbank/questions/${qid}/bookmark`, { method: 'POST' });
        const data = await res.json();
        if (!data.success) {
          alert('Failed to remove bookmark');
          return;
        }
        // data.bookmarked is false after removal
        // Remove from local array + list, refresh
        const idx = QUESTIONS.findIndex(q => q.id === qid);
        if (idx >= 0) {
          QUESTIONS.splice(idx, 1);
          // Remove the corresponding list item from the DOM
          const listItem = qlist.querySelector(`[data-index="${idx}"]`);
          if (listItem) listItem.remove();
          // Re-index the remaining items
          Array.from(qlist.children).forEach((el, newIdx) => {
            el.dataset.index = newIdx;
          });
          // Show the next question in the panel
          if (QUESTIONS.length === 0) {
            detail.innerHTML = '<div class="detail-empty">No more bookmarks.</div>';
          } else {
            const next = Math.min(idx, QUESTIONS.length - 1);
            renderDetail(next);
          }
        }
      } catch (e) {
        alert('Network error: ' + e);
      }
    }
  
    function escapeHtml(s) {
      if (s == null) return '';
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }
  
    // Wire up the list
    document.querySelectorAll('.qlist-item').forEach(el => {
      el.addEventListener('click', () => {
        const i = parseInt(el.dataset.index, 10);
        renderDetail(i);
      });
    });
  
    // Show the first question by default
    if (QUESTIONS.length > 0) {
      renderDetail(0);
    }
  })();