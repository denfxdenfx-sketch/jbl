// login.js — handles Email OR Phone + Password login

async function submitLogin() {
  const identifier = document.getElementById("login-identifier").value.trim();
  const password = document.getElementById("login-password").value;
  const errEl = document.getElementById("login-error");
  
  errEl.textContent = "";

  if (!identifier || !password) {
    errEl.textContent = "Please enter your credentials.";
    return;
  }

  const btn = document.getElementById("login-btn");
  btn.disabled = true;
  btn.textContent = "Logging in...";

  try {
    const { data } = await API.post("/auth/login", { 
      identifier, 
      password 
    });

    if (!data || !data.success) {
      errEl.textContent = (data && data.message) || "Invalid credentials";
      btn.disabled = false;
      btn.textContent = "Log In";
      return;
    }

    window.location.href = data.redirect || "/home";

  } catch (err) {
    errEl.textContent = "Network error. Please try again.";
    btn.disabled = false;
    btn.textContent = "Log In";
  }
}

// ─────────────────────────────────────────────────────────────
// GOOGLE OAUTH
// ─────────────────────────────────────────────────────────────
function signInWithGoogle() {
  // Redirect to our server's /auth/google, which will redirect to Google
  window.location.href = "/auth/google";
}