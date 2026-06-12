// File-tree feature strings (the `files` namespace).
const dict = {
  // Toolbar
  heading: "Files",
  action: {
    newFile: "New file",
    newFolder: "New folder",
    uploadFile: "Upload file",
    uploadHere: "Upload here",
    moveToRoot: "Move to root",
  },
  // Body states
  loadingFiles: "Loading files",
  loadError: "Couldn’t load the file tree.",
  empty: {
    readOnly: "No files yet.",
    editable: "No files yet — create one.",
  },
  treeLabel: "Project files",
  // Node
  expandFolder: "Expand folder",
  collapseFolder: "Collapse folder",
  newNameLabel: "New name",
  actionsFor: "Actions for {{name}}",
  // Create dialog
  createDialog: {
    folderTitle: "New folder",
    fileTitle: "New file",
    nameLabel: "Name",
    defaultFolderName: "New folder",
    defaultFileName: "untitled.tex",
  },
  // Delete dialog
  deleteDialog: {
    title: "Delete “{{name}}”?",
    folderDescription: "This folder and everything inside it will be permanently deleted.",
    fileDescription: "This cannot be undone.",
  },
  // Upload list
  uploadsLabel: "Uploads",
  uploadStatus: {
    failed: "Failed",
    done: "Done",
  },
  dismissUpload: "Dismiss {{name}}",
  // Upload conflict dialog
  conflictDialog: {
    title: "File already exists",
    description: "“{{name}}” already exists in this folder. Replace it with the uploaded file?",
    replace: "Replace",
  },
  // Validation (validate-name.ts)
  validate: {
    required: "Name is required.",
    tooLong: "Name must be at most 255 characters.",
    reserved: "Name cannot be “.” or “..”.",
    slashes: "Name cannot contain slashes.",
    control: "Name cannot contain control characters.",
  },
  // Toasts
  toast: {
    moveIntoSelf: "Can’t move a folder into itself",
    uploaded: "Uploaded {{name}}",
    uploadConflict: "“{{name}}” already exists",
    uploadFailed: "Upload of {{name}} failed",
    createError: "Could not create item",
    created: "Created {{name}}",
    renameError: "Could not rename item",
    renamed: "Renamed",
    moveError: "Could not move item",
    moved: "Moved",
    deleteError: "Could not delete item",
    deleted: "Deleted",
  },
};
export default dict;
export type Dict = typeof dict;
