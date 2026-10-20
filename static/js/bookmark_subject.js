// bookmark_subject.js

let currentIndex = 0;
let bookmarks = {};

// All questions here are bookmarked by default
for (const q of QUESTIONS) {
  bookmarks[q.id] = true;
}

function buildImageUrl(path) {
  if (!path) return null;
  return `/static/uploads/${path}`;
}

// Open a question in the detail view
function openQuestion(index) {
  currentIndex = index;
  document.getElementById("detail-view").style.display = "block";
  renderQuestion();
  document.getElementById("detail-view").scrollIntoView({ behavior: "smooth" });
}

function closeDetail() {
  document.getElementById("detail-view").style.display = "none";
}

// Render the detail view for the current question
function renderQuestion() {
  const q = QUESTIONS[currentIndex];

  document.getElementById("detail-progress").textContent =
    `Question ${currentIndex + 1} of ${QUESTIONS.length}`;

  document.getElementById("detail-topic").textContent = q.topic_name;
  document.getElementById("detail-question-text").textContent = q.text;

  // Question image
  const qImg = document.getElementById("detail-question-image");
  const qImgUrl = buildImageUrl(q.image_path);
  if (qImgUrl) {
    qImg.src = qImgUrl;
    qImg.style.display = "block";
  } else {
    qImg.style.display = "none";
    qImg.removeAttribute("src");
  }

  // Options (read-only, with markers)
  const container = document.getElementById("detail-options");
  container.innerHTML = "";

  const optionKeys = [
    { key: "A", text: q.option_a },
    { key: "B", text: q.option_b },
    { key: "C", text: q.option_c },
    { key: "D", text: q.option_d },
  ];

  optionKeys.forEach(opt => {
    const div = document.createElement("div");
    div.style.margin = "8px 0";
    div.textContent = `${opt.key}) ${opt.text}`;

    if (opt.key === q.correct_option) {
      div.textContent += " ✓";
    }
    if (q.user_answer && opt.key === q.user_answer && opt.key !== q.correct_option) {
      div.textContent += " ✗";
    }
    if (!q.user_answer && opt.key === q.correct_option) {
      div.textContent += " (not answered)";
    }

    container.appendChild(div);
  });

  // Explanation
  const explBox = document.getElementById("detail-explanation-box");
  const explText = document.getElementById("detail-explanation");
  const explImg = document.getElementById("detail-explanation-image");

  explText.textContent = q.explanation || "";
  explBox.style.display = "block";

  const explImgUrl = buildImageUrl(q.explanation_image_path);
  if (explImgUrl) {
    explImg.src = explImgUrl;
    explImg.style.display = "block";
  } else {
    explImg.style.display = "none";
    explImg.removeAttribute("src");
  }

  // Nav buttons
  document.getElementById("prev-btn").disabled = currentIndex === 0;
  document.getElementById("next-btn").textContent =
    currentIndex === QUESTIONS.length - 1 ? "Finish" : "Next";

  // Bookmark button
  updateBookmarkButton(q.id);
}

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
    // Finished — back to the landing page
    window.location.href = "/bookmarks";
  }
}

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
    }
  } else {
    // Add
    const { data } = await API.post("/bookmarks", {
      question_id: questionId,
      source: "review",
    });
    if (data && data.success) {
      bookmarks[questionId] = true;
      updateBookmarkButton(questionId);
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

if (QUESTIONS && QUESTIONS.length > 0) {
  openQuestion(0);
}