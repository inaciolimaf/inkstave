import type { Dict } from "../en/editor";

const dict: Dict = {
  pane: {
    selectFile: "Selecione um arquivo para começar a editar.",
    loadingDocument: "Carregando documento",
    documentGone: "Este documento não existe mais.",
    loadFailed: "Não foi possível carregar este documento.",
    retry: "Tentar novamente",
    binaryFile: "Este é um arquivo binário e não pode ser editado aqui.",
    noFileOpen: "Nenhum arquivo aberto",
    syncToPdf: "Sincronizar com o PDF",
    syncToPdfTitle: "Ir para esta linha no PDF",
  },
  toolbar: {
    agent: "Agente",
    history: "Histórico",
    share: "Compartilhar",
    download: "Baixar",
    openToJump: "Abra {{file}} para ir até lá",
    backToProjects: "Voltar para projetos",
  },
  conflict: {
    title: "Este documento mudou no servidor",
    description:
      "Alguém (ou outra aba) salvou uma versão mais recente desde que você o abriu. Escolha como resolver o conflito.",
    keepMine: "Manter minha versão",
    reload: "Recarregar versão do servidor",
  },
  settings: {
    trigger: "Configurações do editor",
    title: "Configurações do editor",
    fontSize: "Tamanho da fonte",
    fontSizeUnit: "{{size}}px",
    keymap: "Atalhos de teclado",
    keymapDefault: "Padrão",
    keymapVim: "Vim",
    keymapEmacs: "Emacs",
    lineWrapping: "Quebra de linha",
  },
  saveStatus: {
    saved: "Salvo",
    unsaved: "Alterações não salvas",
    saving: "Salvando…",
    saveFailed: "Falha ao salvar — tentando novamente",
    offline: "Offline — as alterações serão salvas quando você reconectar",
    conflict: "Conflito",
    retry: "Tentar novamente",
    savedJustNow: "Salvo agora mesmo",
    savedSecondsAgo: "Salvo há {{seconds}}s",
    savedMinutesAgo: "Salvo há {{minutes}}min",
    savedHoursAgo: "Salvo há {{hours}}h",
  },
  unsavedGuard: {
    title: "Sair com alterações não salvas?",
    description:
      "Suas edições mais recentes ainda não terminaram de ser salvas. Se você sair agora, elas podem ser perdidas.",
    stay: "Ficar",
    leave: "Sair",
  },
  cm: {
    label: "Editor LaTeX",
  },
  collab: {
    connected: "Ao vivo",
    connecting: "Conectando…",
    reconnecting: "Reconectando…",
    offline: "Offline",
    connection: "Conexão: {{status}}",
    loadingDocument: "Carregando documento…",
    syncing: "sincronizando…",
    viewOnly: "Somente leitura",
  },
  presence: {
    you: "{{name}} (Você)",
    idle: "{{who}} — ausente",
    online: "{{who}} — online",
    peopleOnline: "Pessoas online",
    moreOnline: "Mais {{count}} online",
  },
};

export default dict;
