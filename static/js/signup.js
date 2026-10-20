// signup.js — handles the new Email + Phone + Password signup

async function submitSignup() {
    const email = document.getElementById("signup-email").value.trim().toLowerCase();
    const phone = document.getElementById("signup-phone").value.trim();
    const password = document.getElementById("signup-password").value;
    const errEl = document.getElementById("signup-error");
    
    errEl.textContent = "";
  
    // 1. Basic validation
    if (!email || !phone || !password) {
      errEl.textContent = "Please fill in all fields.";
      return;
    }
  
    if (password.length < 6) {
      errEl.textContent = "Password must be at least 6 characters.";
      return;
    }
  
    // 2. Send to backend
    const btn = document.getElementById("signup-btn");
    btn.disabled = true;
    btn.textContent = "Creating account...";
  
    try {
      const { data } = await API.post("/auth/signup", { 
        email, 
        phone, 
        password 
      });
  
      if (!data || !data.success) {
        errEl.textContent = (data && data.message) || "Signup failed";
        btn.disabled = false;
        btn.textContent = "Sign Up";
        return;
      }
  
      // 3. Redirect to Goals page (handled by your existing backend)
      window.location.href = data.redirect || "/goals";
  
    } catch (err) {
      errEl.textContent = "Network error. Please try again.";
      btn.disabled = false;
      btn.textContent = "Sign Up";
    }
  }
  
  // ─────────────────────────────────────────────────────────────
  // GOALS — selection and proceed (kept unchanged)
  // ─────────────────────────────────────────────────────────────
  let selectedGoalId = null;
  
  function selectGoal(goalId, buttonEl) {
    document.querySelectorAll(".goal-option").forEach(btn => {
      btn.classList.remove("selected");
    });
    buttonEl.classList.add("selected");
    selectedGoalId = goalId;
    document.getElementById("proceed-btn").disabled = false;
    document.getElementById("goal-error").textContent = "";
  }
  
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