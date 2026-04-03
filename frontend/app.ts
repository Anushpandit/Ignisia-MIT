interface SignUpPayload {
  full_name: string;
  username: string;
  email: string;
  password: string;
  role: "employee" | "customer";
  entity_id: string;
}

interface LoginPayload {
  username: string;
  password: string;
  role: "employee" | "customer";
}

interface AuthResponse {
  success: boolean;
  message: string;
  role?: "employee" | "customer";
}

type AuthMode = "login" | "signup";
type Role = "employee" | "customer";
type FormFieldMap = Record<string, string>;

const API_BASE_URL = "http://localhost:5000";

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function getElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLElement)) {
    throw new Error(`Missing element: ${id}`);
  }
  return element as T;
}

function getInput(id: string): HTMLInputElement {
  const element = getElement<HTMLElement>(id);
  if (!(element instanceof HTMLInputElement)) {
    throw new Error(`Expected input: ${id}`);
  }
  return element;
}

function getSelect(id: string): HTMLSelectElement {
  const element = getElement<HTMLElement>(id);
  if (!(element instanceof HTMLSelectElement)) {
    throw new Error(`Expected select: ${id}`);
  }
  return element;
}

function setBanner(
  target: HTMLElement,
  message: string,
  visible: boolean,
): void {
  target.textContent = message;
  target.classList.toggle("is-hidden", !visible);
}

function clearErrors(fieldIds: string[]): void {
  fieldIds.forEach((fieldId) => {
    const errorElement = getElement<HTMLElement>(`${fieldId}-error`);
    errorElement.textContent = "";
  });
}

function applyErrors(errors: FormFieldMap): void {
  Object.entries(errors).forEach(([fieldId, message]) => {
    const errorElement = getElement<HTMLElement>(`${fieldId}-error`);
    errorElement.textContent = message;
  });
}

function switchMode(mode: AuthMode): void {
  const loginTab = getElement<HTMLButtonElement>("login-tab");
  const signupTab = getElement<HTMLButtonElement>("signup-tab");
  const loginPanel = getElement<HTMLElement>("login-panel");
  const signupPanel = getElement<HTMLElement>("signup-panel");
  const successBanner = getElement<HTMLElement>("auth-success");
  const errorBanner = getElement<HTMLElement>("auth-error");

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

function getRoleLabel(role: Role | ""): string {
  return role === "customer" ? "Customer ID (Cust_ID)" : "Employee ID (Emp_ID)";
}

function updateEntityLabel(): void {
  const roleSelect = getSelect("signup-role");
  const entityLabel = getElement<HTMLLabelElement>("signup-entity-id-label");
  const roleValue = roleSelect.value === "customer" ? "customer" : "employee";
  entityLabel.textContent = getRoleLabel(roleValue);
}

function validateLoginForm(): LoginPayload | null {
  const fieldIds = ["login-username", "login-password", "login-role"];
  clearErrors(fieldIds);

  const username = getInput("login-username").value.trim();
  const password = getInput("login-password").value.trim();
  const roleValue = getSelect("login-role").value.trim();
  const errors: FormFieldMap = {};

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
    role: roleValue as Role,
  };
}

function validateSignUpForm(): SignUpPayload | null {
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
  const errors: FormFieldMap = {};

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
    role: roleValue as Role,
    entity_id: entityId,
  };
}

async function submitLogin(event: Event): Promise<void> {
  event.preventDefault();

  try {
    const errorBanner = getElement<HTMLElement>("auth-error");
    const successBanner = getElement<HTMLElement>("auth-success");
    const submitButton = getElement<HTMLButtonElement>("login-submit");
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

    const data: AuthResponse = (await response.json()) as AuthResponse;

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
  } catch (_error: unknown) {
    const errorBanner = getElement<HTMLElement>("auth-error");
    setBanner(errorBanner, "Unable to complete login right now.", true);
  } finally {
    const submitButton = getElement<HTMLButtonElement>("login-submit");
    submitButton.disabled = false;
  }
}

async function submitSignUp(event: Event): Promise<void> {
  event.preventDefault();

  try {
    const errorBanner = getElement<HTMLElement>("auth-error");
    const successBanner = getElement<HTMLElement>("auth-success");
    const submitButton = getElement<HTMLButtonElement>("signup-submit");
    const signupForm = getElement<HTMLFormElement>("signup-form");
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

    const data: AuthResponse = (await response.json()) as AuthResponse;

    if (!response.ok || !data.success) {
      setBanner(errorBanner, data.message || "Sign up failed.", true);
      return;
    }

    signupForm.reset();
    updateEntityLabel();
    switchMode("login");
    setBanner(successBanner, "Account created. Please log in.", true);
  } catch (_error: unknown) {
    const errorBanner = getElement<HTMLElement>("auth-error");
    setBanner(errorBanner, "Unable to complete sign up right now.", true);
  } finally {
    const submitButton = getElement<HTMLButtonElement>("signup-submit");
    submitButton.disabled = false;
  }
}

function bindEvents(): void {
  const loginTab = getElement<HTMLButtonElement>("login-tab");
  const signupTab = getElement<HTMLButtonElement>("signup-tab");
  const gotoSignup = getElement<HTMLButtonElement>("goto-signup");
  const gotoLogin = getElement<HTMLButtonElement>("goto-login");
  const signupRole = getSelect("signup-role");
  const loginForm = getElement<HTMLFormElement>("login-form");
  const signupForm = getElement<HTMLFormElement>("signup-form");

  loginTab.addEventListener("click", () => switchMode("login"));
  signupTab.addEventListener("click", () => switchMode("signup"));
  gotoSignup.addEventListener("click", () => switchMode("signup"));
  gotoLogin.addEventListener("click", () => switchMode("login"));
  signupRole.addEventListener("change", updateEntityLabel);
  loginForm.addEventListener("submit", (event: Event) => {
    void submitLogin(event);
  });
  signupForm.addEventListener("submit", (event: Event) => {
    void submitSignUp(event);
  });

  updateEntityLabel();
}

try {
  bindEvents();
} catch (_error: unknown) {
  const errorBanner = getElement<HTMLElement>("auth-error");
  setBanner(errorBanner, "Unable to initialize the page.", true);
}
