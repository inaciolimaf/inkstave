import type { Dict } from "../en/history";

const dict: Dict = {
  panel: {
    title: "Histórico de versões",
    description:
      "Navegue pelas versões, veja o que mudou e restaure — restaurar cria uma nova versão.",
  },
  timeline: {
    ariaLabel: "Histórico de versões",
    empty: "Nenhum histórico ainda.",
    loadFailed: "Não foi possível carregar o histórico.",
    loadMore: "Carregar mais",
    loading: "Carregando…",
    unknownAuthor: "Desconhecido",
    changes_one: "{{count}} alteração",
    changes_other: "{{count}} alterações",
  },
  diff: {
    ariaLabel: "Diferenças da versão",
    selectPrompt: "Selecione uma versão para ver o que mudou.",
    loadFailed: "Não foi possível carregar as diferenças.",
    binary: "Este documento não tem diferenças de texto.",
    tooLarge: "Esta versão é grande demais para comparar.",
    noChanges: "Nenhuma alteração entre estas versões.",
    labelsForVersion: "Rótulos da versão {{version}}",
  },
  labels: {
    namePlaceholder: "Nome do rótulo",
    nameAriaLabel: "Nome do rótulo",
    add: "Adicionar",
    addToVersion: "Adicionar rótulo à versão {{version}}",
    remove: "Remover rótulo {{name}}",
  },
  restore: {
    trigger: "Restaurar esta versão",
    confirmTitle: "Restaurar a versão {{version}}?",
    confirmDescription:
      "O conteúdo atual do documento será substituído pela versão {{version}}. Uma nova versão é criada — nada é excluído, e você pode restaurar de volta a qualquer momento.",
    labelPlaceholder: "Adicione um rótulo para esta restauração (opcional)",
    labelAriaLabel: "Rótulo da restauração",
    cancel: "Cancelar",
    action: "Restaurar",
    restoring: "Restaurando…",
    success: "Restaurado para a versão {{version}}; versão {{newVersion}} criada.",
    error: "Falha ao restaurar. Tente novamente.",
  },
  toast: {
    addLabelFailed: "Não foi possível adicionar o rótulo.",
    removeLabelFailed: "Não foi possível remover o rótulo.",
  },
};

export default dict;
