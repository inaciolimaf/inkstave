import type { Dict } from "../en/files";

const dict: Dict = {
  // Toolbar
  heading: "Arquivos",
  action: {
    newFile: "Novo arquivo",
    newFolder: "Nova pasta",
    uploadFile: "Enviar arquivo",
    uploadHere: "Enviar aqui",
    moveToRoot: "Mover para a raiz",
  },
  // Body states
  loadingFiles: "Carregando arquivos",
  loadError: "Não foi possível carregar a árvore de arquivos.",
  empty: {
    readOnly: "Nenhum arquivo ainda.",
    editable: "Nenhum arquivo ainda — crie um.",
  },
  treeLabel: "Arquivos do projeto",
  // Node
  expandFolder: "Expandir pasta",
  collapseFolder: "Recolher pasta",
  newNameLabel: "Novo nome",
  actionsFor: "Ações para {{name}}",
  // Create dialog
  createDialog: {
    folderTitle: "Nova pasta",
    fileTitle: "Novo arquivo",
    nameLabel: "Nome",
    defaultFolderName: "Nova pasta",
    defaultFileName: "untitled.tex",
  },
  // Delete dialog
  deleteDialog: {
    title: "Excluir “{{name}}”?",
    folderDescription: "Esta pasta e tudo o que há dentro dela serão excluídos permanentemente.",
    fileDescription: "Isso não pode ser desfeito.",
  },
  // Upload list
  uploadsLabel: "Envios",
  uploadStatus: {
    failed: "Falhou",
    done: "Concluído",
  },
  dismissUpload: "Dispensar {{name}}",
  // Upload conflict dialog
  conflictDialog: {
    title: "O arquivo já existe",
    description: "“{{name}}” já existe nesta pasta. Substituí-lo pelo arquivo enviado?",
    replace: "Substituir",
  },
  // Validation (validate-name.ts)
  validate: {
    required: "O nome é obrigatório.",
    tooLong: "O nome deve ter no máximo 255 caracteres.",
    reserved: "O nome não pode ser “.” ou “..”.",
    slashes: "O nome não pode conter barras.",
    control: "O nome não pode conter caracteres de controle.",
  },
  // Toasts
  toast: {
    moveIntoSelf: "Não é possível mover uma pasta para dentro dela mesma",
    uploaded: "{{name}} enviado",
    uploadConflict: "“{{name}}” já existe",
    uploadFailed: "Falha no envio de {{name}}",
    createError: "Não foi possível criar o item",
    created: "{{name}} criado",
    renameError: "Não foi possível renomear o item",
    renamed: "Renomeado",
    moveError: "Não foi possível mover o item",
    moved: "Movido",
    deleteError: "Não foi possível excluir o item",
    deleted: "Excluído",
  },
};

export default dict;
