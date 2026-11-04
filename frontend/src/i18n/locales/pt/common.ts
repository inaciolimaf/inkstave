/** Generic, app-wide strings reused across features (the `common` namespace). */
const common = {
  action: {
    cancel: "Cancelar",
    save: "Salvar",
    saving: "Salvando…",
    delete: "Excluir",
    deleting: "Excluindo…",
    create: "Criar",
    creating: "Criando…",
    close: "Fechar",
    confirm: "Confirmar",
    retry: "Tentar de novo",
    back: "Voltar",
    remove: "Remover",
    rename: "Renomear",
    edit: "Editar",
    search: "Buscar",
    send: "Enviar",
    copy: "Copiar",
    copied: "Copiado",
    upload: "Enviar arquivo",
    signOut: "Sair",
    signIn: "Entrar",
  },
  state: {
    loading: "Carregando…",
    error: "Algo deu errado. Tente novamente.",
    empty: "Nada por aqui ainda.",
  },
  shell: {
    skipToContent: "Pular para o conteúdo principal",
  },
  /** The screen part of `document.title`, set by the app shell from each route's `handle`. */
  title: {
    setup: "Configuração inicial",
    login: "Entrar",
    register: "Criar conta",
    confirmEmail: "Confirmar troca de e-mail",
    verifyEmail: "Verificar e-mail",
    resendVerification: "Reenviar e-mail de verificação",
    magicLink: "Link mágico",
    resetPassword: "Redefinir senha",
    forgotPassword: "Esqueci a senha",
    projects: "Projetos",
    editor: "Editor",
    settings: "Configurações",
    invite: "Convite para projeto",
    join: "Entrar no projeto",
  },
  errorBoundary: {
    title: "Algo deu errado",
    body: "A página encontrou um erro inesperado. Você pode tentar de novo ou recarregar se o problema persistir.",
    retry: "Tentar de novo",
    reload: "Recarregar a página",
  },
};

export default common;
