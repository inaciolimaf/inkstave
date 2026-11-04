const dict = {
  header: {
    title: "Your projects",
    newProject: "New project",
    blankProject: "Blank project",
    searchLabel: "Search projects",
    searchPlaceholder: "Search projects…",
    sortLabel: "Sort projects",
    sort: {
      updatedAt: "Last modified",
      name: "Name A–Z",
      createdAt: "Created",
    },
  },
  appName: "Inkstave",
  nav: {
    settings: "Settings",
  },
  table: {
    caption: "Your projects",
    lastModified: "Last modified",
  },
  actionsMenu: {
    label: "Project actions",
    open: "Open",
    download: "Download as .zip",
  },
  download: {
    error: "Could not download the project",
  },
  list: {
    loadingLabel: "Loading projects",
    emptyTitle: "No projects yet",
    emptyDescription: "Create your first project to get started.",
    createFirst: "Create your first project",
    noResults: "No projects match “{{term}}”.",
    clearSearch: "Clear search",
    loadError: "We couldn’t load your projects.",
  },
  form: {
    nameLabel: "Project name",
    nameRequired: "Project name is required.",
    nameTooLong: "Name must be at most 255 characters.",
  },
  create: {
    title: "Create project",
    description: "Give your new project a name.",
    placeholder: "My Paper",
  },
  rename: {
    title: "Rename project",
    description: "Choose a new name for this project.",
  },
  delete: {
    title: "Delete “{{name}}”?",
    description: "This cannot be undone.",
  },
  toast: {
    created: "Project created",
    createError: "Could not create project",
    renamed: "Project renamed",
    renameError: "Could not rename project",
    deleted: "Project deleted",
    deleteError: "Could not delete project",
  },
  import: {
    cta: "Import (.zip)",
    title: "Import a project",
    description: "Upload a .zip exported from another LaTeX platform. We’ll create a new project from it.",
    fileLabel: "Project archive (.zip)",
    chooseFile: "Choose a .zip file",
    nameLabel: "Project name (optional)",
    namePlaceholder: "Defaults to the archive name",
    submit: "Import",
    uploading: "Uploading…",
    processing: "Importing…",
    success: "Project imported",
    deleteEmpty: "Delete the empty project",
    errors: {
      zip_slip: "This archive contains unsafe file paths and was rejected.",
      zip_too_large: "This archive is too large to import.",
      zip_too_many_entries: "This archive has too many files to import.",
      zip_symlink: "This archive contains symbolic links and was rejected.",
      invalid_zip: "This file is not a valid .zip archive.",
      zip_empty: "This archive has no importable files.",
      upload_failed: "The upload failed. Please try again.",
      generic: "The import failed. Please try again.",
    },
  },
  template: {
    menuItem: "From an Overleaf template…",
    title: "New project from an Overleaf template",
    description:
      "Start from a template you downloaded from Overleaf. Inkstave does not contact Overleaf: you bring the .zip.",
    step1: "Find a template on Overleaf and open it.",
    browse: "Browse Overleaf templates",
    step2: "In the template, choose Menu, then Download, then Source. This saves a .zip.",
    step3: "Drop that .zip here, or choose it.",
    dropHint: "Drop the .zip here, or choose a file",
    imported: "Template imported. Open the project to see what may need attention.",
    openProject: "Open project",
  },
};

export default dict;
export type Dict = typeof dict;
