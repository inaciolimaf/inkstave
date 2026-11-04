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
};

export default dict;
