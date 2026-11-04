/** Portuguese strings for the inline review of the agent's proposals (the `review` namespace). */
import type { Dict } from "../en/review";

const dict: Dict = {
  bar: {
    label: "Revisão no texto",
    counter: "Mudança {{index}} de {{total}}",
    previous: "Anterior",
    next: "Próxima",
    acceptAll: "Aceitar todas",
    rejectAll: "Rejeitar todas",
    close: "Fechar",
  },
  inline: {
    counter: "Mudança {{index}} de {{total}}",
    accept: "Aceitar",
    reject: "Rejeitar",
    acceptHunk: "Aceitar a mudança {{index}}",
    rejectHunk: "Rejeitar a mudança {{index}}",
    blocked: "Este trecho mudou desde a proposta",
  },
  toast: {
    acceptError: "A mudança não pôde ser gravada. Tente de novo.",
    saveError: "A decisão não pôde ser salva. Tente de novo.",
    drifted: "Este trecho mudou desde a proposta, então só pode ser rejeitado.",
    alreadyDecided: "Esta proposta já foi decidida.",
    notInProject: "Este arquivo não está no projeto.",
    loadError: "Não foi possível carregar a proposta.",
  },
};

export default dict;
