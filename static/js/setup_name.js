// setup_name.js — collect first + last name, save to server

async function saveName() {
    const firstName = document.getElementById("first_name").value.trim();
    const lastName = document.getElementById("last_name").value.trim();
    const errEl = document.getElementById("name-error");
    errEl.textContent = "";
  
    if (!firstName) {
      errEl.textContent = "Please enter your first name";
      return;
    }
  
    const { data } = await API.post("/user/set-name", {
      first_name: firstName,
      last_name: lastName,
    });
  
    if (!data || !data.success) {
      errEl.textContent = (data && data.message) || "Failed to save";
      return;
    }
  
    window.location.href = data.redirect || "/setup-number";
  }

  // ─────────────────────────────────────────────────────────────
// Step 3: Send OTP to phone number
// ─────────────────────────────────────────────────────────────
async function sendNumberOtp() {
    const phone = document.getElementById("phone").value.trim();
    const errEl = document.getElementById("number-error");
    errEl.textContent = "";
  
    if (!phone) {
      errEl.textContent = "Enter your phone number";
      return;
    }
  
    // Basic format check
    if (!phone.startsWith("+")) {
      errEl.textContent = "Include country code (e.g. +919876543210)";
      return;
    }
  
    const { data } = await API.post("/auth/signup-number-send-otp", { phone });
  
    if (!data || !data.success) {
      errEl.textContent = (data && data.message) || "Failed to send OTP";
      return;
    }
  
    // Navigate to OTP page
    window.location.href = "/setup-number/otp?phone=" + encodeURIComponent(phone);
  }
  
  // ─────────────────────────────────────────────────────────────
  // Step 4: Verify OTP
  // ─────────────────────────────────────────────────────────────
  async function verifyNumberOtp() {
    const otp = document.getElementById("otp").value.trim();
    const errEl = document.getElementById("otp-error");
    errEl.textContent = "";
  
    if (!otp || otp.length !== 6) {
      errEl.textContent = "Enter the 6-digit code";
      return;
    }
  
    const { data } = await API.post("/auth/signup-number-verify-otp", {
      phone: SIGNUP_PHONE,
      otp: otp,
    });
  
    if (!data || !data.success) {
      errEl.textContent = (data && data.message) || "Invalid OTP";
      return;
    }
  
    window.location.href = data.redirect || "/home";
  }