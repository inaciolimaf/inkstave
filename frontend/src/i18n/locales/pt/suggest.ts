/** Portuguese strings for suggested changes (Sugerindo, spec 119): the switch, the marks in the text and the tab. */
import type { Dict } from "../en/suggest";

const dict: Dict = {
  mode: {
    label: "Sugerindo",
    hint: "Sugerir mudanças: o que você digitar ou apagar vira uma sugestão que os outros aceitam ou rejeitam.",
    on: "Sugerindo ativado",
    off: "Sugerindo desativado",
    failed: "Não foi possível salvar sua configuração de Sugerindo.",
  },
  popover: {
    label: "Sugestão de {{name}}",
    insertion: "Inserção sugerida",
    deletion: "Exclusão sugerida",
    accept: "Aceitar",
    reject: "Rejeitar",
    dismiss: "Descartar",
  },
  deleted: {
    folded_one: "…{{count}} palavra",
    folded_other: "…{{count}} palavras",
    label: "Exclusão sugerida por {{name}}: {{text}}",
  },
  blocked: "Muito para apagar como sugestão. Desative Sugerindo para apagar isso.",
  presence: {
    suggesting: "sugerindo",
  },
  tab: {
    label: "Sugestões",
    empty: "Nenhuma sugestão neste documento.",
    insertion: "Inserção",
    deletion: "Exclusão",
    by: "por {{name}}",
    stale: "Não se aplica mais",
    acceptAll: "Aceitar todas",
    rejectAll: "Rejeitar todas",
    accept: "Aceitar",
    reject: "Rejeitar",
    dismiss: "Descartar",
    rowLabel: "{{kind}} por {{name}}",
  },
};

export default dict;
