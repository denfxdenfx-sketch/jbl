// ─────────────────────────────────────────────────────────────
// PHONE + OTP
// ─────────────────────────────────────────────────────────────
async function sendOtp() {
  const phone = document.getElementById("phone").value.trim();
  const errEl = document.getElementById("phone-error");
  errEl.textContent = "";

  if (!phone) {
    errEl.textContent = "Enter a phone number";
    return;
  }

  const { status, data } = await API.post("/auth/send-otp", { phone });

  if (!data || !data.success) {
    errEl.textContent = (data && data.message) || "Failed to send OTP";
    return;
  }

  // Navigate to OTP page (server-side render with phone in URL)
  window.location.href = "/login/otp?phone=" + encodeURIComponent(phone);
}

async function verifyOtp() {
  const otp = document.getElementById("otp").value.trim();
  const errEl = document.getElementById("otp-error");
  errEl.textContent = "";

  if (!otp || otp.length !== 6) {
    errEl.textContent = "Enter the 6-digit code";
    return;
  }

  const { status, data } = await API.post("/auth/verify-otp", {
    phone: PHONE,
    otp: otp,
  });

  if (!data || !data.success) {
    errEl.textContent = (data && data.message) || "Invalid OTP";
    return;
  }

  window.location.href = "/home";
}

// ─────────────────────────────────────────────────────────────
// EMAIL
// ─────────────────────────────────────────────────────────────
function signInWithEmail() {
  window.location.href = "/login/email";
}

async function loginWithEmail() {
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  const errEl = document.getElementById("email-error");
  errEl.textContent = "";

  if (!email || !password) {
    errEl.textContent = "Enter email and password";
    return;
  }

  const { status, data } = await API.post("/auth/login-email", {
    email: email,
    password: password,
  });

  if (!data || !data.success) {
    errEl.textContent = (data && data.message) || "Login failed";
    return;
  }

  window.location.href = "/home";
}

// ─────────────────────────────────────────────────────────────
// GOOGLE
// ─────────────────────────────────────────────────────────────
function signInWithGoogle() {
  // Redirect to our server's /auth/google, which will redirect to Google
  window.location.href = "/auth/google";
}


// ─────────────────────────────────────────────────────────────
// EMAIL OTP
// ─────────────────────────────────────────────────────────────

/**
 * Called from login_email.html when the user clicks "Get OTP".
 * Sends the email to the server, then navigates to the OTP entry page.
 */
async function sendEmailOtp() {
  const email = document.getElementById("email").value.trim().toLowerCase();
  const errEl = document.getElementById("email-error");
  errEl.textContent = "";

  if (!email) {
    errEl.textContent = "Enter your email";
    return;
  }

  const { data } = await API.post("/auth/send-email-otp", { email });

  if (!data || !data.success) {
    errEl.textContent = (data && data.message) || "Failed to send OTP";
    return;
  }

  // Navigate to the email OTP page with the email in the URL
  window.location.href = "/login/email-otp?email=" + encodeURIComponent(email);
}

/**
 * Called from login_email_otp.html when the user clicks "Verify".
 * Sends the email + OTP to the server, then redirects to home on success.
 */
async function verifyEmailOtp() {
  const otp = document.getElementById("otp").value.trim();
  const errEl = document.getElementById("otp-error");
  errEl.textContent = "";

  if (!otp || otp.length !== 6) {
    errEl.textContent = "Enter the 6-digit code";
    return;
  }

  const { data } = await API.post("/auth/verify-email-otp", {
    email: EMAIL,
    otp: otp,
  });

  if (!data || !data.success) {
    errEl.textContent = (data && data.message) || "Invalid OTP";
    return;
  }

  window.location.href = "/home";
}