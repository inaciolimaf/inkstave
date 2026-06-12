/** Portuguese strings for the diff-review surface (the `review` namespace). */
import type { Dict } from "../en/review";

const dict: Dict = {
  title: "Revisar mudanças propostas",
  description:
    "Revise as mudanças propostas pelo agente e aceite ou rejeite cada hunk antes de aplicar.",
  accepted: "{{accepted}}/{{total}} aceitos",
  apply: "Aplicar",
  loadError: "Não foi possível carregar a proposta.",
  noChanges: "Esta proposta não tem mudanças.",
  applyResult: {
    successTitle: "Mudanças aplicadas",
    errorTitle: "Algumas mudanças não puderam ser aplicadas",
    applied: "{{count}} aplicadas",
    skipped: ", {{count}} ignoradas",
    error: " — erro: {{error}}",
  },
  toast: {
    applyError: "Algumas mudanças não puderam ser aplicadas.",
    applySuccess: "Mudanças aplicadas ao seu documento.",
  },
  confirmApply: {
    title: "Aplicar mudanças?",
    description:
      "Isto gravará {{applicable}} mudança aceita em {{fileCount}} arquivo no seu documento.",
    description_fileMany:
      "Isto gravará {{applicable}} mudança aceita em {{fileCount}} arquivos nos seus documentos.",
    descriptionMany:
      "Isto gravará {{applicable}} mudanças aceitas em {{fileCount}} arquivo no seu documento.",
    descriptionMany_fileMany:
      "Isto gravará {{applicable}} mudanças aceitas em {{fileCount}} arquivos nos seus documentos.",
    blocked: " {{count}} hunk não se aplica mais e será ignorado.",
    blockedMany: " {{count}} hunks não se aplicam mais e serão ignorados.",
    confirm: "Aplicar",
  },
  confirmDiscard: {
    title: "Descartar sua revisão?",
    description: "Suas escolhas de aceitar/rejeitar serão perdidas.",
    keep: "Continuar revisando",
    discard: "Descartar",
  },
  file: {
    changesTo: "Mudanças em {{path}}",
    newFile: "Novo arquivo",
    deleted: "Excluído",
    hunkCount: "{{accepted}}/{{total}} hunks",
    acceptAll: "Aceitar todos",
    rejectAll: "Rejeitar todos",
    diff: "Diff",
    preview: "Pré-visualizar",
    baseChangedTitle: "Este arquivo mudou desde a proposta",
    baseChangedDescription: "Hunks que não se aplicam mais são marcados e serão ignorados.",
  },
  hunk: {
    noLongerApplies: "Não se aplica mais",
    accept: "Aceitar",
    reject: "Rejeitar",
    acceptChange: "Aceitar mudança: {{header}}",
    added: "adicionado",
    removed: "removido",
  },
  filePreview: "Pré-visualização do arquivo",
};

export default dict;
