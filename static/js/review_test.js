// review_test.js

let allQuestions = QUESTIONS;
let filtered = [...QUESTIONS];
let currentIndex = 0;
let bookmarks = {};

// Restore bookmarks
for (const q of QUESTIONS) {
  if (q.bookmarked) bookmarks[q.id] = true;
}

// ─────────────────────────────────────────────────────────────
// Filters
// ─────────────────────────────────────────────────────────────

function applyFilters() {
  const statusFilter = document.getElementById("status-filter").value;
  const subjectFilter = document.getElementById("subject-filter").value;

  filtered = allQuestions.filter(q => {
    // Status filter
    if (statusFilter === "correct" && q.is_correct !== true) return false;
    if (statusFilter === "wrong" && (q.is_correct !== false || q.user_answer === null)) return false;
    if (statusFilter === "skipped" && q.user_answer !== null) return false;

    // Subject filter
    if (subjectFilter !== "all" && q.subject_id !== parseInt(subjectFilter)) return false;

    return true;
  });

  currentIndex = 0;
  renderQuestion();
}

// ─────────────────────────────────────────────────────────────
// Render the current question (main area)
// ─────────────────────────────────────────────────────────────

function buildImageUrl(path) {
  if (!path) return null;
  return `/static/uploads/${path}`;
}

function renderQuestion() {
  // If no questions match, show empty state
  if (filtered.length === 0) {
    document.getElementById("progress").textContent = "0";
    document.getElementById("total").textContent = "0";
    document.getElementById("subject-name").textContent = "";
    document.getElementById("question-text").textContent = "No questions match the current filters.";
    document.getElementById("options-container").innerHTML = "";
    document.getElementById("explanation-box").style.display = "none";
    document.getElementById("question-image").style.display = "none";
    document.getElementById("bookmark-btn").style.display = "none";
    document.getElementById("prev-btn").disabled = true;
    document.getElementById("next-btn").disabled = true;
    renderQuestionList();
    return;
  }

  document.getElementById("bookmark-btn").style.display = "inline-block";

  const q = filtered[currentIndex];

  document.getElementById("progress").textContent = currentIndex + 1;
  document.getElementById("total").textContent = filtered.length;
  document.getElementById("subject-name").textContent = q.subject_name;
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
    const div = document.createElement("div");
    div.style.margin = "8px 0";
    div.style.padding = "8px";
    div.style.borderRadius = "4px";
    div.textContent = `${o.key}) ${o.text}`;

    if (o.key === q.correct_option) {
      div.style.background = "#d4edda";
    }
    if (q.user_answer === o.key && o.key !== q.correct_option) {
      div.style.background = "#f8d7da";
    }
    if (q.user_answer === o.key && o.key === q.correct_option) {
      div.textContent += " (your answer)";
    }
    if (q.user_answer === null && o.key === q.correct_option) {
      div.textContent += " (not answered)";
    }

    container.appendChild(div);
  });

  // Explanation
  const explBox = document.getElementById("explanation-box");
  const explText = document.getElementById("explanation-text");
  const explImg = document.getElementById("explanation-image");

  explText.textContent = q.explanation || "";
  explBox.style.display = "block";

  const explUrl = buildImageUrl(q.explanation_image_path);
  if (explUrl) {
    explImg.src = explUrl;
    explImg.style.display = "block";
  } else {
    explImg.style.display = "none";
    explImg.removeAttribute("src");
  }

  // Nav
  document.getElementById("prev-btn").disabled = currentIndex === 0;
  document.getElementById("next-btn").disabled = currentIndex === filtered.length - 1;

  // Bookmark
  updateBookmarkButton(q.id);

  // Sidebar question list
  renderQuestionList();
}

// ─────────────────────────────────────────────────────────────
// Render the question list in the sidebar
// ─────────────────────────────────────────────────────────────

function renderQuestionList() {
  const list = document.getElementById("question-list");
  list.innerHTML = "";

  if (filtered.length === 0) {
    list.innerHTML = "<p style='color:#888;'>No questions.</p>";
    return;
  }

  filtered.forEach((q, i) => {
    const item = document.createElement("div");
    item.style.padding = "8px";
    item.style.marginBottom = "4px";
    item.style.borderRadius = "4px";
    item.style.cursor = "pointer";
    item.style.border = "1px solid #ddd";
    item.style.fontSize = "13px";

    // Truncate the question text
    const text = q.text.length > 60 ? q.text.slice(0, 60) + "..." : q.text;
    item.textContent = `${i + 1}. ${text}`;

    // Status color dot
    let dotColor = "#888";  // grey for skipped
    if (q.is_correct === true) dotColor = "#28a745";       // green
    else if (q.user_answer !== null) dotColor = "#dc3545"; // red

    const dot = document.createElement("span");
    dot.style.display = "inline-block";
    dot.style.width = "8px";
    dot.style.height = "8px";
    dot.style.borderRadius = "50%";
    dot.style.background = dotColor;
    dot.style.marginRight = "6px";
    item.prepend(dot);

    // Highlight the current question
    if (i === currentIndex) {
      item.style.background = "#e7f1f8";
      item.style.borderColor = "#175e7a";
    }

    item.onclick = () => {
      currentIndex = i;
      renderQuestion();
    };

    list.appendChild(item);
  });
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
  if (currentIndex < filtered.length - 1) {
    currentIndex++;
    renderQuestion();
  }
}

// ─────────────────────────────────────────────────────────────
// Bookmark
// ─────────────────────────────────────────────────────────────

async function toggleBookmark() {
  const q = filtered[currentIndex];

  if (bookmarks[q.id]) {
    await API.request(`/bookmarks/${q.id}`, { method: "DELETE" });
    bookmarks[q.id] = false;
  } else {
    await API.post("/bookmarks", { question_id: q.id, source: "review" });
    bookmarks[q.id] = true;
  }

  updateBookmarkButton(q.id);
}

function updateBookmarkButton(qid) {
  const btn = document.getElementById("bookmark-btn");
  btn.textContent = bookmarks[qid] ? "★ Bookmarked" : "☆ Bookmark";
}

// ─────────────────────────────────────────────────────────────
// Boot
// ─────────────────────────────────────────────────────────────

renderQuestion();