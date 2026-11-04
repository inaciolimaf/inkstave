import type { Dict } from "../en/projects";

const dict: Dict = {
  header: {
    title: "Seus projetos",
    newProject: "Novo projeto",
    blankProject: "Projeto em branco",
    searchLabel: "Buscar projetos",
    searchPlaceholder: "Buscar projetos…",
    sortLabel: "Ordenar projetos",
    sort: {
      updatedAt: "Última modificação",
      name: "Nome A–Z",
      createdAt: "Criado em",
    },
  },
  appName: "Inkstave",
  nav: {
    settings: "Configurações",
  },
  scope: {
    label: "Mostrar projetos",
    all: "Todos",
    owned: "Meus",
    shared: "Compartilhados comigo",
  },
  owner: {
    you: "Você",
  },
  role: {
    editor: "Pode editar",
    viewer: "Pode visualizar",
  },
  table: {
    caption: "Seus projetos",
    lastModified: "Última modificação",
  },
  actionsMenu: {
    label: "Ações do projeto",
    open: "Abrir",
    download: "Baixar como .zip",
    leave: "Sair do projeto",
  },
  download: {
    error: "Não foi possível baixar o projeto",
  },
  list: {
    loadingLabel: "Carregando projetos",
    emptyTitle: "Nenhum projeto ainda",
    emptyDescription: "Crie seu primeiro projeto para começar.",
    createFirst: "Crie seu primeiro projeto",
    noResults: "Nenhum projeto corresponde a “{{term}}”.",
    clearSearch: "Limpar busca",
    loadError: "Não foi possível carregar seus projetos.",
    sharedEmpty:
      "Nada compartilhado com você ainda. Os projetos para os quais alguém convidar você aparecem aqui.",
    ownedEmpty: "Você ainda não criou nenhum projeto.",
  },
  form: {
    nameLabel: "Nome do projeto",
    nameRequired: "O nome do projeto é obrigatório.",
    nameTooLong: "O nome deve ter no máximo 255 caracteres.",
  },
  create: {
    title: "Criar projeto",
    description: "Dê um nome ao seu novo projeto.",
    placeholder: "Meu Artigo",
    spelling: {
      label: "Ortografia",
      enUS: "Inglês",
      ptBR: "Português (Brasil)",
      hint: "Você pode mudar isso depois no menu do editor (… → Ortografia).",
    },
  },
  rename: {
    title: "Renomear projeto",
    description: "Escolha um novo nome para este projeto.",
  },
  delete: {
    title: "Excluir “{{name}}”?",
    description: "Isso não pode ser desfeito.",
  },
  leave: {
    title: "Sair de “{{name}}”?",
    description: "Você perderá o acesso até que alguém convide você de novo.",
    submit: "Sair do projeto",
  },
  toast: {
    created: "Projeto criado",
    createError: "Não foi possível criar o projeto",
    renamed: "Projeto renomeado",
    renameError: "Não foi possível renomear o projeto",
    deleted: "Projeto excluído",
    deleteError: "Não foi possível excluir o projeto",
    left: "Você saiu do projeto",
    leaveError: "Não foi possível sair do projeto",
  },
  import: {
    cta: "Importar (.zip)",
    title: "Importar um projeto",
    description:
      "Envie um .zip exportado de outra plataforma LaTeX. Vamos criar um novo projeto a partir dele.",
    fileLabel: "Arquivo do projeto (.zip)",
    chooseFile: "Escolha um arquivo .zip",
    nameLabel: "Nome do projeto (opcional)",
    namePlaceholder: "Usa o nome do arquivo por padrão",
    submit: "Importar",
    uploading: "Enviando…",
    processing: "Importando…",
    success: "Projeto importado",
    deleteEmpty: "Excluir o projeto vazio",
    errors: {
      zip_slip: "Este arquivo contém caminhos inseguros e foi rejeitado.",
      zip_too_large: "Este arquivo é grande demais para importar.",
      zip_too_many_entries: "Este arquivo tem arquivos demais para importar.",
      zip_symlink: "Este arquivo contém links simbólicos e foi rejeitado.",
      invalid_zip: "Este arquivo não é um .zip válido.",
      zip_empty: "Este arquivo não tem arquivos importáveis.",
      upload_failed: "O envio falhou. Tente novamente.",
      generic: "A importação falhou. Tente novamente.",
    },
  },
  template: {
    menuItem: "De um template do Overleaf…",
    title: "Novo projeto a partir de um template do Overleaf",
    description:
      "Comece com um template baixado do Overleaf. O Inkstave não acessa o Overleaf: você envia o .zip.",
    step1: "Encontre um template no Overleaf e abra-o.",
    browse: "Ver os templates do Overleaf",
    step2: "No template, escolha Menu, depois Download e depois Source. Isso salva um .zip.",
    step3: "Solte esse .zip aqui ou escolha o arquivo.",
    dropHint: "Solte o .zip aqui, ou escolha um arquivo",
    imported: "Template importado. Abra o projeto para ver o que pode precisar de atenção.",
    openProject: "Abrir projeto",
  },
};

export default dict;
