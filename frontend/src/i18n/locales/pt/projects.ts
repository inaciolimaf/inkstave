import type { Dict } from "../en/projects";

const dict: Dict = {
  header: {
    title: "Seus projetos",
    newProject: "Novo projeto",
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
  table: {
    caption: "Seus projetos",
    name: "Nome",
    lastModified: "Última modificação",
    actions: "Ações",
  },
  card: {
    lastModified: "Última modificação {{date}}",
  },
  actionsMenu: {
    label: "Ações do projeto",
    open: "Abrir",
    download: "Baixar como .zip",
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
  },
  rename: {
    title: "Renomear projeto",
    description: "Escolha um novo nome para este projeto.",
  },
  delete: {
    title: "Excluir “{{name}}”?",
    description: "Isso não pode ser desfeito.",
  },
  toast: {
    created: "Projeto criado",
    createError: "Não foi possível criar o projeto",
    renamed: "Projeto renomeado",
    renameError: "Não foi possível renomear o projeto",
    deleted: "Projeto excluído",
    deleteError: "Não foi possível excluir o projeto",
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
};

export default dict;
