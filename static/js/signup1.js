// signup.js — handles the signup flow (email → OTP → new account)

// ─────────────────────────────────────────────────────────────
// Step 1: Send OTP to email
// ─────────────────────────────────────────────────────────────
async function signupSendOtp() {
  const email = document.getElementById("signup-email").value.trim().toLowerCase();
  const errEl = document.getElementById("signup-error");
  errEl.textContent = "";

  if (!email) {
    errEl.textContent = "Enter your email";
    return;
  }

  const { data } = await API.post("/auth/signup-send-otp", { email });

  if (!data || !data.success) {
    errEl.textContent = (data && data.message) || "Failed to send OTP";
    return;
  }

  // Navigate to the signup OTP page
  window.location.href = "/signup/otp?email=" + encodeURIComponent(email);
}

// ─────────────────────────────────────────────────────────────
// Step 2: Verify OTP, create account
// ─────────────────────────────────────────────────────────────
async function signupVerifyOtp() {
  const otp = document.getElementById("signup-otp").value.trim();
  const errEl = document.getElementById("signup-otp-error");
  errEl.textContent = "";

  if (!otp || otp.length !== 6) {
    errEl.textContent = "Enter the 6-digit code";
    return;
  }

  const { data } = await API.post("/auth/signup-verify-otp", {
    email: SIGNUP_EMAIL,
    otp: otp,
  });

  if (!data || !data.success) {
    errEl.textContent = (data && data.message) || "Invalid OTP";
    return;
  }

  // Redirect to goals (or /home)
  window.location.href = data.redirect || "/goals";
}

// ─────────────────────────────────────────────────────────────
// GOALS — selection and proceed
// ─────────────────────────────────────────────────────────────

let selectedGoalId = null;

/**
 * Called when a goal button is clicked.
 * Highlights the button, stores the goal ID, enables Proceed.
 */
function selectGoal(goalId, buttonEl) {
  // Remove 'selected' from all goal buttons
  document.querySelectorAll(".goal-option").forEach(btn => {
    btn.classList.remove("selected");
  });

  // Mark this one as selected
  buttonEl.classList.add("selected");
  selectedGoalId = goalId;

  // Enable the Proceed button
  document.getElementById("proceed-btn").disabled = false;
  document.getElementById("goal-error").textContent = "";
}

/**
 * Called when "Proceed" is clicked.
 * Sends the selected goal ID to the server, then redirects.
 */
async function proceedWithGoal() {
  const errEl = document.getElementById("goal-error");
  errEl.textContent = "";

  if (!selectedGoalId) {
    errEl.textContent = "Please select a goal first.";
    return;
  }

  const { data } = await API.post("/goals/select", { goal_id: selectedGoalId });

  if (!data || !data.success) {
    errEl.textContent = (data && data.message) || "Failed to save goal.";
    return;
  }

  window.location.href = data.redirect || "/name";
}