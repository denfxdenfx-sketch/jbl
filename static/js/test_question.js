// test_question.js

let currentIndex = START_INDEX;
let answers = {};     // { question_id: "A"|"B"|"C"|"D" }
let marked = {};      // { question_id: true }
let bookmarks = {};
let timeRemaining = REMAINING_SECONDS;
let paletteStart = 0;       // index of first question shown in palette
const PALETTE_SIZE = 60;    // how many questions per palette page

// Restore from drafts
for (const [qid, d] of Object.entries(DRAFTS)) {
  const id = parseInt(qid);
  if (d.selected) answers[id] = d.selected;
  if (d.marked) marked[id] = true;
}

// Restore bookmarks
for (const qid of BOOKMARKED_IDS) {
  bookmarks[qid] = true;
}


// ─────────────────────────────────────────────────────────────
// Timer
// ─────────────────────────────────────────────────────────────

function updateTimer() {
  if (timeRemaining <= 0) {
    autoSubmit();
    return;
  }
  const mins = Math.floor(timeRemaining / 60);
  const secs = timeRemaining % 60;
  document.getElementById("timer").textContent =
    `${mins}:${secs.toString().padStart(2, "0")}`;
  timeRemaining--;
}

setInterval(updateTimer, 1000);
updateTimer();


// ─────────────────────────────────────────────────────────────
// Render question
// ─────────────────────────────────────────────────────────────

function buildImageUrl(path) {
  if (!path) return null;
  return `/static/uploads/${path}`;
}

function renderQuestion() {
  const q = QUESTIONS[currentIndex];

  document.getElementById("progress").textContent = currentIndex + 1;
  document.getElementById("question-text").textContent = q.text;

  // Question image
  const qImg = document.getElementById("question-image");
  const url = buildImageUrl(q.image_path);
  if (url) {
    qImg.src = url;
    qImg.style.display = "block";
  } else {
    qImg.style.display = "none";
    qImg.removeAttribute("src");
  }

  // Options
  const container = document.getElementById("options-container");
  container.innerHTML = "";

  const opts = [
    { key: "A", text: q.option_a },
    { key: "B", text: q.option_b },
    { key: "C", text: q.option_c },
    { key: "D", text: q.option_d },
  ];

  opts.forEach(o => {
    const btn = document.createElement("button");
    btn.textContent = `${o.key}) ${o.text}`;
    btn.style.display = "block";
    btn.style.margin = "8px 0";
    btn.style.width = "100%";
    btn.style.textAlign = "left";
    btn.dataset.value = o.key;

    if (answers[q.id] === o.key) {
      btn.style.fontWeight = "bold";
      btn.style.background = "#d4edda";   // green
    }

    btn.onclick = () => toggleAnswer(q.id, o.key);
    container.appendChild(btn);
  });

  // Nav buttons
  document.getElementById("prev-btn").disabled = currentIndex === 0;
  document.getElementById("next-btn").textContent =
    currentIndex === QUESTIONS.length - 1 ? "Submit" : "Next";

  // Bookmark
  updateBookmarkButton(q.id);

  // Mark button
  updateMarkButton(q.id);

  // Palette
  renderPalette();
}


// ─────────────────────────────────────────────────────────────
// Toggle answer (select/deselect)
// ─────────────────────────────────────────────────────────────

async function toggleAnswer(questionId, option) {
  const wasSelected = answers[questionId] === option;

  if (wasSelected) {
    // Deselect
    delete answers[questionId];
  } else {
    // Select
    answers[questionId] = option;
  }

  // Save draft
  await saveDraft(questionId);

  renderQuestion();
}

async function saveDraft(questionId) {
  const selected = answers[questionId] || null;
  const status = selected ? "answered" : "unanswered";

  await API.post(`/tests/attempts/${ATTEMPT_ID}/save-draft`, {
    question_id: questionId,
    selected_option: selected,
    status: status,
    marked: marked[questionId] || false,
  });
}


// ─────────────────────────────────────────────────────────────
// Mark for review
// ─────────────────────────────────────────────────────────────

async function toggleMark() {
  const q = QUESTIONS[currentIndex];

  if (marked[q.id]) {
    delete marked[q.id];
  } else {
    marked[q.id] = true;
  }

  await saveDraft(q.id);
  renderQuestion();
}

function updateMarkButton(qid) {
  const btn = document.getElementById("mark-btn");
  if (marked[qid]) {
    btn.textContent = "★ Marked for Review";
    btn.style.background = "#dc3545";
    btn.style.color = "white";
  } else {
    btn.textContent = "☆ Mark for Review";
    btn.style.background = "";
    btn.style.color = "";
  }
}


// ─────────────────────────────────────────────────────────────
// Bookmark
// ─────────────────────────────────────────────────────────────

async function toggleBookmark() {
  const q = QUESTIONS[currentIndex];
  if (bookmarks[q.id]) {
    await API.request(`/bookmarks/${q.id}`, { method: "DELETE" });
    bookmarks[q.id] = false;
  } else {
    await API.post("/bookmarks", { question_id: q.id, source: "test" });
    bookmarks[q.id] = true;
  }
  updateBookmarkButton(q.id);
}

function updateBookmarkButton(qid) {
  const btn = document.getElementById("bookmark-btn");
  btn.textContent = bookmarks[qid] ? "★ Bookmarked" : "☆ Bookmark";
}


// ─────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────

function goPrev() {
  if (currentIndex > 0) {
    currentIndex--;
    renderQuestion();
  }
}

function goNext() {
  if (currentIndex < QUESTIONS.length - 1) {
    currentIndex++;
    renderQuestion();
  } else {
    submitTest();
  }
}

function jumpTo(index) {
  currentIndex = index;
  renderQuestion();
}


// ─────────────────────────────────────────────────────────────
// Palette
// ─────────────────────────────────────────────────────────────

function renderPalette() {
  const palette = document.getElementById("palette");
  palette.innerHTML = "";

  const end = Math.min(paletteStart + PALETTE_SIZE, QUESTIONS.length);

  for (let i = paletteStart; i < end; i++) {
    const q = QUESTIONS[i];
    const btn = document.createElement("button");
    btn.textContent = i + 1;
    btn.style.margin = "2px";
    btn.style.width = "32px";
    btn.style.height = "32px";
    btn.style.cursor = "pointer";

    if (marked[q.id]) {
      btn.style.background = "#dc3545";
      btn.style.color = "white";
    } else if (answers[q.id]) {
      btn.style.background = "#28a745";
      btn.style.color = "white";
    } else {
      btn.style.background = "#e9ecef";
    }

    if (i === currentIndex) {
      btn.style.outline = "2px solid #000";
    }

    btn.onclick = () => jumpTo(i);
    palette.appendChild(btn);
  }

  // Show pagination controls if needed
  const prevPageBtn = document.getElementById("palette-prev");
  const nextPageBtn = document.getElementById("palette-next");

  if (paletteStart > 0) {
    prevPageBtn.style.display = "inline-block";
  } else {
    prevPageBtn.style.display = "none";
  }

  if (end < QUESTIONS.length) {
    nextPageBtn.style.display = "inline-block";
  } else {
    nextPageBtn.style.display = "none";
  }
}

function paletteNext() {
  if (paletteStart + PALETTE_SIZE < QUESTIONS.length) {
    paletteStart += PALETTE_SIZE;
    renderPalette();
  }
}

function palettePrev() {
  if (paletteStart > 0) {
    paletteStart = Math.max(0, paletteStart - PALETTE_SIZE);
    renderPalette();
  }
}


// ─────────────────────────────────────────────────────────────
// Submit
// ─────────────────────────────────────────────────────────────

async function submitTest() {
  if (!confirm("Submit the test?")) return;
  const { data } = await API.post(`/tests/attempts/${ATTEMPT_ID}/submit`);
  if (data && data.success) {
    window.location.href = data.redirect || `/tests/attempts/${ATTEMPT_ID}/review`;
  }
}

async function autoSubmit() {
  const { data } = await API.post(`/tests/attempts/${ATTEMPT_ID}/submit`);
  if (data && data.success) {
    window.location.href = data.redirect;
  }
}


// ─────────────────────────────────────────────────────────────
// Exit
// ─────────────────────────────────────────────────────────────

function confirmExit() {
  document.getElementById("exit-modal").style.display = "block";
}

function closeExit() {
  document.getElementById("exit-modal").style.display = "none";
}


// Boot
renderQuestion();