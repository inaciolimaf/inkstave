/** Portuguese strings for the AI agent chat panel (the `agent` namespace). */
import type { Dict } from "../en/agent";

const dict: Dict = {
  ariaLabel: "Agente de IA",
  newChat: "Nova conversa",
  sessions: "Sessões",
  untitledChat: "Conversa sem título",
  description:
    "Converse com o assistente de escrita por IA. Ele propõe mudanças para você revisar.",
  resizeHandle: "Redimensionar painel do agente",
  loadingConversation: "Carregando conversa",
  empty: {
    intro:
      "Peça ao agente para ler ou revisar seu projeto. Ele propõe mudanças que você revisa — nunca edita os arquivos diretamente.",
    example1: "Reescreva a introdução para ser mais concisa.",
    example2: "Encontre onde a seção de metodologia está definida.",
    example3: "Adicione uma conclusão resumindo os principais resultados.",
  },
  composer: {
    placeholder: "Peça ao agente para ler ou editar o projeto…",
    messageLabel: "Mensagem para o agente",
    sendLabel: "Enviar mensagem",
    sendTooltip: "Enviar (Enter)",
  },
  run: {
    stop: "Parar",
    stopLabel: "Parar a execução",
  },
  error: {
    retry: "Tentar de novo",
    generic: "Erro",
    titles: {
      transport: "Conexão perdida",
      internal: "Falha na execução",
      llm_error: "Serviço de IA indisponível",
      rate_limited: "Limite de uso atingido",
      agent_rate_limited: "Limite de uso atingido",
      budget_exceeded: "Orçamento excedido",
      agent_budget_exceeded: "Orçamento atingido",
      cancelled: "Execução cancelada",
      timeout: "Tempo esgotado",
    },
    messages: {
      cancelled: "Execução cancelada.",
      agent_rate_limited: "Você atingiu o limite de uso do agente. Tente novamente em instantes.",
      rate_limited: "Você atingiu um limite de uso. Tente novamente em instantes.",
      agent_budget_exceeded: "Esta execução atingiu o orçamento de tokens ou de custo.",
      budget_exceeded: "Esta execução excederia o orçamento de tokens.",
      llm_error: "O serviço de IA está temporariamente indisponível.",
      internal: "A execução do agente falhou. Tente novamente.",
      timeout:
        "A execução demorou demais e foi interrompida. Tente uma tarefa menor — por exemplo, um arquivo ou seção por vez.",
      generic: "Algo deu errado.",
      connectionLost: "Conexão perdida.",
      startFailed: "Não foi possível iniciar a execução.",
    },
  },
  transcript: {
    conversation: "Conversa",
    jumpToLatest: "Ir para o final",
    runCancelled: "Execução cancelada",
    tools: {
      search_project: "Pesquisou o projeto",
      read_file: "Leu um arquivo",
      list_tree: "Listou a árvore de arquivos",
      locate_section: "Localizou uma seção",
      propose_edit: "Propôs uma edição",
    },
    proposedChanges: "Mudanças propostas",
    hunkLine_one: "{{path}} · {{count}} hunk",
    hunkLine_other: "{{path}} · {{count}} hunks",
    reviewChanges: "Revisar mudanças",
    reviewChangesCount: "Revisar mudanças ({{count}})",
  },
};

export default dict;
