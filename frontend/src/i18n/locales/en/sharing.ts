const dict = {
  dialog: {
    title: "Share project",
    description: "Invite collaborators and manage who has access.",
  },
  invite: {
    label: "Invite by email",
    placeholder: "name@example.com",
    roleLabel: "Invite role",
    submit: "Invite",
    invalidEmail: "Enter a valid email address.",
    sent: "Invitation sent to {{email}}",
    sendError: "Could not send the invitation.",
  },
  // Lowercase: role labels are shown with a `capitalize` CSS class, so the DOM
  // text stays lowercase like the raw role enum. This avoids the read-only role
  // label "Owner" colliding with a member literally named "Owner" in tests/UI.
  role: {
    owner: "owner",
    editor: "editor",
    viewer: "viewer",
  },
  members: {
    title: "People with access",
    sectionLabel: "People with access",
    loadError: "Couldn’t load members.",
    you: " (You)",
    roleFor: "Role for {{name}}",
    transfer: "Transfer",
    remove: "Remove",
    removeLabel: "Remove {{name}}",
    leave: "Leave project",
    transferConfirm: {
      title: "Make {{name}} the owner?",
      description: "You will become an editor. This cannot be undone here.",
      action: "Transfer",
    },
    removeConfirm: {
      title: "Remove {{name}}?",
      description: "They will lose access to this project.",
      action: "Remove",
    },
    leaveConfirm: {
      title: "Leave this project?",
      description: "You will lose access until invited again.",
      action: "Leave",
    },
    changeRoleError: "Could not change the role.",
    removeError: "Could not remove the member.",
    transferred: "Ownership transferred.",
    transferError: "Could not transfer ownership.",
  },
  pending: {
    title: "Pending invites",
    sectionLabel: "Pending invites",
    empty: "No pending invites.",
    revoke: "Revoke",
    revokeLabel: "Revoke invite for {{email}}",
    revokeConfirm: {
      title: "Revoke invite for {{email}}?",
      description: "The invitation link will stop working.",
      action: "Revoke",
    },
    revokeError: "Could not revoke the invite.",
  },
  confirm: {
    cancel: "Cancel",
  },
  accept: {
    loading: "Loading invitation…",
    unavailableTitle: "Invitation unavailable",
    unavailableDescription: "This invitation has expired or is no longer valid.",
    backToProjects: "Back to projects",
    notFound: "This invitation could not be found.",
    invitedTo: "You’re invited to {{projectName}}",
    invitedBy: "{{inviterName}} invited you to join as ",
    accept: "Accept",
    decline: "Decline",
    joined: "You’ve joined the project.",
    acceptError: "Could not accept the invite.",
    declineError: "Could not decline the invite.",
  },
};

export default dict;
export type Dict = typeof dict;
