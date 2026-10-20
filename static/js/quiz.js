// quiz.js

// ─────────────────────────────────────────────────────────────
// Local state
// ─────────────────────────────────────────────────────────────
let currentIndex = START_INDEX;
let answers = {};       // { question_id: "A"|"B"|"C"|"D" }
let feedbacks = {};     // { question_id: { is_correct, correct_option, explanation, explanation_image_path } }
let bookmarks = {};     // { question_id: true }

// Restore past answers
for (const [qid, data] of Object.entries(PAST_ANSWERS)) {
  const id = parseInt(qid);
  answers[id] = data.selected;
  feedbacks[id] = {
    is_correct: data.is_correct,
    correct_option: data.correct_option,
    explanation: data.explanation,
    explanation_image_path: data.explanation_image_path,
  };
}

// Restore bookmarks
for (const qid of BOOKMARKED_IDS) {
  bookmarks[qid] = true;
}

// ─────────────────────────────────────────────────────────────
// Helper: build full image URL from a path
// ─────────────────────────────────────────────────────────────
function buildImageUrl(path) {
  if (!path) return null;
  return `/static/uploads/${path}`;
}

// ─────────────────────────────────────────────────────────────
// Render the current question
// ─────────────────────────────────────────────────────────────
function renderQuestion() {
  const q = QUESTIONS[currentIndex];

  // Progress
  document.getElementById("progress").textContent =
    `Question ${currentIndex + 1} of ${QUESTIONS.length}`;

  // Question text
  document.getElementById("question-text").textContent = q.text;

  // Question image
  const qImg = document.getElementById("question-image");
  const qImgUrl = buildImageUrl(q.image_path);
  if (qImgUrl) {
    qImg.src = qImgUrl;
    qImg.style.display = "block";
  } else {
    qImg.style.display = "none";
    qImg.removeAttribute("src");
  }

  // Options
  const container = document.getElementById("options-container");
  container.innerHTML = "";

  const optionKeys = [
    { key: "A", text: q.option_a },
    { key: "B", text: q.option_b },
    { key: "C", text: q.option_c },
    { key: "D", text: q.option_d },
  ];

  optionKeys.forEach(opt => {
    const btn = document.createElement("button");
    btn.textContent = `${opt.key}) ${opt.text}`;
    btn.style.display = "block";
    btn.style.margin = "8px 0";
    btn.dataset.value = opt.key;

    if (answers[q.id]) {
      // Already answered — show feedback
      btn.disabled = true;

      if (feedbacks[q.id]) {
        // Mark correct option
        if (opt.key === feedbacks[q.id].correct_option) {
          btn.textContent += " ✓";
        }
        // Mark user's wrong choice
        if (opt.key === answers[q.id] && opt.key !== feedbacks[q.id].correct_option) {
          btn.textContent += " ✗";
        }
      }
    } else {
      // Not answered — clickable
      btn.onclick = () => selectOption(q.id, opt.key);
    }

    container.appendChild(btn);
  });

  // Explanation
  const explBox = document.getElementById("explanation-box");
  const explText = document.getElementById("explanation-text");
  const explImg = document.getElementById("explanation-image");

  if (feedbacks[q.id]) {
    explText.textContent = feedbacks[q.id].explanation || "";
    explBox.style.display = "block";

    const explImgUrl = buildImageUrl(feedbacks[q.id].explanation_image_path);
    if (explImgUrl) {
      explImg.src = explImgUrl;
      explImg.style.display = "block";
    } else {
      explImg.style.display = "none";
      explImg.removeAttribute("src");
    }
  } else {
    explBox.style.display = "none";
    explImg.style.display = "none";
  }

  // Navigation buttons
  document.getElementById("prev-btn").disabled = currentIndex === 0;
  document.getElementById("next-btn").textContent =
    currentIndex === QUESTIONS.length - 1 ? "Finish" : "Next";

  // Bookmark button
  updateBookmarkButton(q.id);
}

// ─────────────────────────────────────────────────────────────
// Answer submission
// ─────────────────────────────────────────────────────────────
async function selectOption(questionId, selectedOption) {
  if (answers[questionId]) return;   // already answered

  // Store locally (immediate feedback)
  answers[questionId] = selectedOption;

  // Send to server
  const { data } = await API.post("/practice/answer", {
    question_id: questionId,
    selected_option: selectedOption,
  });

  if (data && data.success) {
    feedbacks[questionId] = {
      is_correct: data.is_correct,
      correct_option: data.correct_option,
      explanation: data.explanation,
      explanation_image_path: data.explanation_image_path,
    };
    renderQuestion();
  } else {
    alert((data && data.message) || "Failed to save answer");
    delete answers[questionId];
    renderQuestion();
  }
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
    finishQuiz();
  }
}

// ─────────────────────────────────────────────────────────────
// Finish quiz
// ─────────────────────────────────────────────────────────────
async function finishQuiz() {
  const { data } = await API.post("/practice/complete", { topic_id: TOPIC_ID });
  if (data && data.success) {
    window.location.href = data.redirect || `/topics/${TOPIC_ID}/submit`;
  } else {
    alert("Failed to complete topic");
  }
}

// ─────────────────────────────────────────────────────────────
// Exit confirmation
// ─────────────────────────────────────────────────────────────
function confirmExit() {
  document.getElementById("exit-modal").style.display = "block";
}

function closeExit() {
  document.getElementById("exit-modal").style.display = "none";
}

// ─────────────────────────────────────────────────────────────
// Bookmark toggle
// ─────────────────────────────────────────────────────────────
async function toggleBookmark() {
  const q = QUESTIONS[currentIndex];
  const questionId = q.id;

  if (bookmarks[questionId]) {
    // Remove
    const { data } = await API.request(`/bookmarks/${questionId}`, {
      method: "DELETE",
    });
    if (data && data.success) {
      bookmarks[questionId] = false;
      updateBookmarkButton(questionId);
    } else {
      alert("Failed to remove bookmark");
    }
  } else {
    // Add
    const { data } = await API.post("/bookmarks", {
      question_id: questionId,
      source: "practice",
    });
    if (data && data.success) {
      bookmarks[questionId] = true;
      updateBookmarkButton(questionId);
    } else {
      alert("Failed to add bookmark");
    }
  }
}

function updateBookmarkButton(questionId) {
  const btn = document.getElementById("bookmark-btn");
  if (bookmarks[questionId]) {
    btn.textContent = "★ Bookmarked";
  } else {
    btn.textContent = "☆ Bookmark";
  }
}

// ─────────────────────────────────────────────────────────────
// Boot
// ─────────────────────────────────────────────────────────────
renderQuestion();