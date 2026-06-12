const dict = {
  page: {
    title: "Settings",
    backToProjects: "Back to projects",
  },
  profile: {
    title: "Profile",
    description: "Your display name and avatar.",
    displayName: "Display name",
    save: "Save profile",
    saving: "Saving…",
    updated: "Profile updated.",
  },
  editor: {
    title: "Editor preferences",
    description: "Applied to your editor immediately and saved to your account.",
    theme: "Theme",
    themeSystem: "System",
    themeLight: "Light",
    themeDark: "Dark",
    fontSize: "Font size",
    keymap: "Keymap",
    keymapDefault: "Default",
    keymapVim: "Vim",
    keymapEmacs: "Emacs",
  },
  email: {
    title: "Email",
    current: "Current:",
    pending: "· pending: {{email}}",
    sentPrefix: "We sent a confirmation link to ",
    sentSuffix: ". The change takes effect once you confirm it.",
    newEmail: "New email",
    password: "Password",
    submit: "Change email",
    sending: "Sending…",
    success: "Confirmation sent.",
  },
  password: {
    title: "Password",
    description: "Changing it signs out your other sessions.",
    current: "Current password",
    new: "New password",
    confirm: "Confirm new password",
    mismatch: "Passwords do not match.",
    submit: "Change password",
    changing: "Changing…",
    success: "Password changed. Please sign in again.",
  },
  danger: {
    title: "Delete account",
    description:
      "Permanently deletes your account and the projects you own. This cannot be undone.",
    trigger: "Delete my account",
    dialogTitle: "Delete your account?",
    dialogDescription:
      "Enter your password and type DELETE to confirm. Your owned projects will be removed.",
    password: "Password",
    typeDelete: "Type DELETE",
    submit: "Delete account",
    deleting: "Deleting…",
    success: "Account deleted.",
  },
  error: {
    generic: "Something went wrong.",
  },
};

export default dict;
export type Dict = typeof dict;
