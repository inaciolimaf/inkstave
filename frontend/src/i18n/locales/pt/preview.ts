import type { Dict } from "../en/preview";

/** Strings for the PDF preview / compile feature (the `preview` namespace). */
const dict: Dict = {
  compile: {
    compile: "Compilar",
    compiling: "Compilando…",
    queued: "Na fila…",
    working: "Trabalhando…",
    compileProject: "Compilar projeto",
    cancelCompilation: "Cancelar compilação",
    progressLabel: "Compilando",
  },
  announce: {
    succeeded: "Compilação concluída.",
    failed: "Falha na compilação.",
    timedOut: "A compilação expirou.",
    cancelled: "Compilação cancelada.",
    error: "Erro na compilação.",
  },
  status: {
    exit: "saída {{code}}",
  },
  errorState: {
    failureTitle: "Falha na compilação",
    failureMessage: "Seu documento não compilou. Confira o registro para ver os erros do LaTeX.",
    timeoutTitle: "A compilação expirou",
    timeoutMessage:
      "A compilação demorou demais e foi interrompida. Simplifique o documento ou tente novamente.",
    errorTitle: "Algo deu errado",
    errorMessage: "A compilação não pôde ser concluída devido a um erro do sistema.",
    viewLog: "Ver registro",
    tryAgain: "Tentar novamente",
  },
  empty: {
    noPreview: "Nenhuma prévia ainda",
    compileToPreview: "Compile para ver uma prévia do seu documento.",
  },
  loading: {
    loadingPdfLabel: "Carregando PDF",
    loadingPreview: "Carregando prévia…",
    pdfErrorLabel: "Erro no PDF",
  },
  pane: {
    label: "Painel de prévia do PDF",
    compileOutput: "Saída da compilação",
    pdfPreview: "Prévia do PDF",
    collapseOutput: "Recolher saída da compilação",
    expandOutput: "Expandir saída da compilação",
  },
  log: {
    title: "Registro",
    copyToClipboard: "Copiar registro para a área de transferência",
    compileLog: "Registro da compilação",
    loadingLog: "Carregando registro…",
    noLogOutput: "Sem saída de registro.",
  },
  problems: {
    title: "Problemas",
    region: "Problemas da compilação",
    noLogYet: "Nenhum registro ainda — execute uma compilação.",
    noProblems: "Nenhum problema.",
    updating: "atualizando…",
    loading: "carregando…",
    errors: "Erros",
    warnings: "Avisos",
    typesetting: "Composição",
    group: "{{label}} ({{count}})",
    countSeverity: "{{count}} {{severity}}",
    rowLabel: "{{severity}}: {{message}}{{location}}",
  },
  toolbar: {
    zoomOut: "Diminuir zoom",
    zoomIn: "Aumentar zoom",
    zoomLevel: "Nível de zoom",
    fitWidth: "Ajustar à largura",
    fitPage: "Ajustar à página",
    previousPage: "Página anterior",
    nextPage: "Próxima página",
    pageNumber: "Número da página",
    of: "de {{numPages}}",
    downloadPdf: "Baixar PDF",
  },
  viewer: {
    page: "Página {{pageNumber}}",
  },
  errors: {
    startCompile: "Não foi possível iniciar a compilação.",
    loadLog: "Não foi possível carregar o registro.",
    loadPdf: "Não foi possível carregar o PDF.",
  },
  sync: {
    unavailable: "Dados de SyncTeX indisponíveis para esta compilação",
    noMatch: "Nenhuma localização correspondente",
    failed: "Falha na sincronização",
  },
};

export default dict;
