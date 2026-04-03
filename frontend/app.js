const API_BASE_URL = "http://localhost:5000";
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function getElement(id) {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLElement)) {
    throw new Error(`Missing element: ${id}`);
  }
  return element;
}

function getInput(id) {
  const element = getElement(id);
  if (!(element instanceof HTMLInputElement)) {
    throw new Error(`Expected input: ${id}`);
  }
  return element;
}

function getSelect(id) {
  const element = getElement(id);
  if (!(element instanceof HTMLSelectElement)) {
    throw new Error(`Expected select: ${id}`);
  }
  return element;
}

function setBanner(target, message, visible) {
  target.textContent = message;
  target.classList.toggle("is-hidden", !visible);
}

function clearErrors(fieldIds) {
  fieldIds.forEach((fieldId) => {
    const errorElement = getElement(`${fieldId}-error`);
    errorElement.textContent = "";
  });
}

function applyErrors(errors) {
  Object.entries(errors).forEach(([fieldId, message]) => {
    const errorElement = getElement(`${fieldId}-error`);
    errorElement.textContent = message;
  });
}

function switchMode(mode) {
  const loginTab = getElement("login-tab");
  const signupTab = getElement("signup-tab");
  const loginPanel = getElement("login-panel");
  const signupPanel = getElement("signup-panel");
  const successBanner = getElement("auth-success");
  const errorBanner = getElement("auth-error");
  const loginActive = mode === "login";

  loginTab.classList.toggle("is-active", loginActive);
  signupTab.classList.toggle("is-active", !loginActive);
  loginTab.setAttribute("aria-selected", String(loginActive));
  signupTab.setAttribute("aria-selected", String(!loginActive));
  loginPanel.classList.toggle("is-hidden", !loginActive);
  signupPanel.classList.toggle("is-hidden", loginActive);

  setBanner(errorBanner, "", false);
  if (mode === "signup") {
    setBanner(successBanner, "", false);
  }
}

function getRoleLabel(role) {
  return role === "customer" ? "Customer ID (Cust_ID)" : "Employee ID (Emp_ID)";
}

function updateEntityLabel() {
  const roleSelect = getSelect("signup-role");
  const entityLabel = getElement("signup-entity-id-label");
  const roleValue = roleSelect.value === "customer" ? "customer" : "employee";
  entityLabel.textContent = getRoleLabel(roleValue);
}

function validateLoginForm() {
  const fieldIds = ["login-username", "login-password", "login-role"];
  clearErrors(fieldIds);

  const username = getInput("login-username").value.trim();
  const password = getInput("login-password").value.trim();
  const roleValue = getSelect("login-role").value.trim();
  const errors = {};

  if (!username) {
    errors["login-username"] = "Username is required.";
  }

  if (!password) {
    errors["login-password"] = "Password is required.";
  }

  if (roleValue !== "employee" && roleValue !== "customer") {
    errors["login-role"] = "Role is required.";
  }

  if (Object.keys(errors).length > 0) {
    applyErrors(errors);
    return null;
  }

  return {
    username,
    password,
    role: roleValue,
  };
}

function validateSignUpForm() {
  const fieldIds = [
    "signup-full-name",
    "signup-username",
    "signup-email",
    "signup-password",
    "signup-confirm-password",
    "signup-role",
    "signup-entity-id",
  ];
  clearErrors(fieldIds);

  const fullName = getInput("signup-full-name").value.trim();
  const username = getInput("signup-username").value.trim();
  const email = getInput("signup-email").value.trim();
  const password = getInput("signup-password").value.trim();
  const confirmPassword = getInput("signup-confirm-password").value.trim();
  const roleValue = getSelect("signup-role").value.trim();
  const entityId = getInput("signup-entity-id").value.trim();
  const errors = {};

  if (!fullName) {
    errors["signup-full-name"] = "Full name is required.";
  }

  if (!username) {
    errors["signup-username"] = "Username is required.";
  }

  if (!email) {
    errors["signup-email"] = "Email is required.";
  } else if (!emailPattern.test(email)) {
    errors["signup-email"] = "Enter a valid email address.";
  }

  if (!password) {
    errors["signup-password"] = "Password is required.";
  }

  if (!confirmPassword) {
    errors["signup-confirm-password"] = "Please confirm your password.";
  } else if (password !== confirmPassword) {
    errors["signup-confirm-password"] = "Passwords do not match.";
  }

  if (roleValue !== "employee" && roleValue !== "customer") {
    errors["signup-role"] = "Role is required.";
  }

  if (!entityId) {
    errors["signup-entity-id"] = "ID is required.";
  }

  if (Object.keys(errors).length > 0) {
    applyErrors(errors);
    return null;
  }

  return {
    full_name: fullName,
    username,
    email,
    password,
    role: roleValue,
    entity_id: entityId,
  };
}

async function submitLogin(event) {
  event.preventDefault();

  try {
    const errorBanner = getElement("auth-error");
    const successBanner = getElement("auth-success");
    const submitButton = getElement("login-submit");
    const payload = validateLoginForm();

    setBanner(successBanner, "", false);
    setBanner(errorBanner, "", false);

    if (!payload) {
      return;
    }

    submitButton.disabled = true;

    const response = await fetch(`${API_BASE_URL}/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      setBanner(errorBanner, data.message || "Login failed.", true);
      return;
    }

    if (data.role === "customer") {
      window.location.href = "/pages/customer.html";
      return;
    }

    if (data.role === "employee") {
      window.location.href = "/pages/employee.html";
      return;
    }

    setBanner(errorBanner, "Invalid server response.", true);
  } catch (_error) {
    const errorBanner = getElement("auth-error");
    setBanner(errorBanner, "Unable to complete login right now.", true);
  } finally {
    const submitButton = getElement("login-submit");
    submitButton.disabled = false;
  }
}

async function submitSignUp(event) {
  event.preventDefault();

  try {
    const errorBanner = getElement("auth-error");
    const successBanner = getElement("auth-success");
    const submitButton = getElement("signup-submit");
    const signupForm = getElement("signup-form");
    const payload = validateSignUpForm();

    setBanner(errorBanner, "", false);
    setBanner(successBanner, "", false);

    if (!payload) {
      return;
    }

    submitButton.disabled = true;

    const response = await fetch(`${API_BASE_URL}/signup`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      setBanner(errorBanner, data.message || "Sign up failed.", true);
      return;
    }

    signupForm.reset();
    updateEntityLabel();
    switchMode("login");
    setBanner(successBanner, "Account created. Please log in.", true);
  } catch (_error) {
    const errorBanner = getElement("auth-error");
    setBanner(errorBanner, "Unable to complete sign up right now.", true);
  } finally {
    const submitButton = getElement("signup-submit");
    submitButton.disabled = false;
  }
}

function bindEvents() {
  const loginTab = getElement("login-tab");
  const signupTab = getElement("signup-tab");
  const gotoSignup = getElement("goto-signup");
  const gotoLogin = getElement("goto-login");
  const signupRole = getSelect("signup-role");
  const loginForm = getElement("login-form");
  const signupForm = getElement("signup-form");

  loginTab.addEventListener("click", () => switchMode("login"));
  signupTab.addEventListener("click", () => switchMode("signup"));
  gotoSignup.addEventListener("click", () => switchMode("signup"));
  gotoLogin.addEventListener("click", () => switchMode("login"));
  signupRole.addEventListener("change", updateEntityLabel);
  loginForm.addEventListener("submit", (event) => {
    void submitLogin(event);
  });
  signupForm.addEventListener("submit", (event) => {
    void submitSignUp(event);
  });

  updateEntityLabel();
}

try {
  bindEvents();
} catch (_error) {
  const errorBanner = getElement("auth-error");
  setBanner(errorBanner, "Unable to initialize the page.", true);
}
