import type { Dict } from "../en/discussion";

/** Strings for the project chat (the `discussion` namespace, spec 117). */
const dict: Dict = {
  title: "Chat do projeto",
  tabs: {
    chat: "Chat",
  },
  button: {
    label: "Chat",
    unreadAria: "Chat, {{count}} não lidas",
  },
  empty: "Nenhuma mensagem ainda. Diga oi aos colaboradores.",
  loadOlder: "Carregar mensagens anteriores",
  loading: "Carregando o chat…",
  loadFailed: "Não foi possível carregar o chat.",
  composer: {
    label: "Mensagem",
    placeholder: "Escreva uma mensagem…",
    send: "Enviar",
  },
  message: {
    you: "Você",
    unknownAuthor: "Ex-membro",
    deleted: "Mensagem apagada",
    delete: "Apagar mensagem",
    sending: "Enviando…",
    failed: "Não enviada.",
    retry: "Tentar de novo",
  },
  comments: {
    title: "Comentários",
    description: "Comentários sobre o texto deste projeto.",
    close: "Fechar comentários",
    button: {
      label: "Comentários",
      openAria: "Comentários, {{count}} abertos",
    },
    selection: {
      comment: "Comentar",
    },
    filter: {
      label: "Filtrar comentários",
      open: "Abertos",
      resolved: "Resolvidos",
      all: "Todos",
    },
    scope: {
      label: "Quais comentários",
      file: "Este arquivo",
      all: "Todos os arquivos",
    },
    empty: "Nenhum comentário aqui.",
    thread: {
      label: "Conversa do comentário",
      messages: "Mensagens",
    },
    detached: "Comentário solto",
    detachedNotice: "O texto em que este comentário estava foi removido",
    messageDeleted: "Mensagem apagada",
    edited: "editado",
    formerMember: "Ex-membro",
    you: "Você",
    edit: "Editar",
    delete: "Apagar",
    save: "Salvar",
    cancel: "Cancelar",
    resolve: "Resolver",
    reopen: "Reabrir",
    reply: {
      label: "Responder",
      placeholder: "Responder…",
      send: "Enviar",
    },
    composer: {
      label: "Novo comentário",
      placeholder: "Adicione um comentário sobre o texto selecionado…",
      submit: "Comentar",
    },
    mentions: {
      label: "Membros",
      hint: "Digite @ para mencionar um membro. Ctrl/Cmd+Enter envia.",
    },
    error: {
      save: "Não foi possível salvar o comentário. Tente de novo.",
    },
  },
};

export default dict;
