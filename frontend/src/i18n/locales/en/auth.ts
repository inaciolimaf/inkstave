const dict = {
  login: {
    title: "Sign in to Inkstave",
    description: "Enter your email and password to continue.",
    justRegistered: "Account created — please sign in.",
    submit: "Sign in",
    noAccount: "No account?",
    createOne: "Create one",
    invalidCredentials: "Invalid email or password.",
    tooManyAttempts: "Too many attempts. Please try again later.",
  },
  register: {
    title: "Create your account",
    description: "Start writing with Inkstave.",
    submit: "Create account",
    haveAccount: "Already have an account?",
    emailExists: "An account with this email already exists.",
  },
  setup: {
    title: "Set up Inkstave",
    description: "Create the first administrator account.",
    submit: "Create admin",
    statusError: "Couldn’t reach the server to check setup status. Please try again.",
    alreadyComplete: "Setup is already complete. Redirecting to sign in…",
  },
  confirmEmail: {
    title: "Confirm email change",
    confirming: "Confirming your new email…",
    done: "Your email is now {{email}}.",
    missingToken: "This link is missing its confirmation token.",
    failed: "Could not confirm the email change.",
    goToSettings: "Go to settings",
  },
  fields: {
    email: "Email",
    emailPlaceholder: "you@example.com",
    adminEmailPlaceholder: "admin@example.com",
    password: "Password",
    confirmPassword: "Confirm password",
    displayName: "Display name",
  },
  validation: {
    emailRequired: "Email is required.",
    emailInvalid: "Enter a valid email address.",
    passwordRequired: "Password is required.",
    passwordMin: "Password must be at least 8 characters.",
    passwordMax: "Password must be at most 72 characters.",
    passwordLetter: "Password must contain at least one letter.",
    passwordDigit: "Password must contain at least one digit.",
    confirmPasswordRequired: "Please confirm your password.",
    passwordsMismatch: "Passwords do not match.",
    displayNameRequired: "Display name is required.",
    displayNameMax: "Display name must be at most 100 characters.",
  },
};

export default dict;
export type Dict = typeof dict;
