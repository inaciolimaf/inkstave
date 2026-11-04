/** Textos em português das ferramentas de inserção (o namespace `insert`, spec 114). */
import type { Dict } from "../en/insert";

const dict: Dict = {
  menu: {
    trigger: "Inserir",
    symbol: "Símbolo…",
    table: "Tabela…",
    equation: "Equação…",
  },
  packageHint: {
    needs: "Precisa de {{line}}",
    add: "Adicionar",
    noMainDocument: "Adicione {{line}} antes de \\begin{document} no documento principal.",
  },
  symbols: {
    title: "Símbolos",
    description: "Pesquise pelo nome ou pelo comando e escolha um símbolo para inseri-lo no cursor.",
    search: "Pesquisar símbolos",
    placeholder: "Pesquisar, por exemplo alpha",
    tabs: "Categorias de símbolos",
    all: "Todos",
    recent: "Recentes",
    categories: {
      greek: "Grego",
      relations: "Relações",
      operators: "Operadores",
      arrows: "Setas",
      sets: "Conjuntos e lógica",
      delimiters: "Delimitadores",
      accents: "Acentos",
      misc: "Diversos",
    },
    empty: "Nenhum símbolo corresponde a “{{query}}”.",
    packageTip: "Precisa do pacote {{name}}",
  },
  table: {
    title: "Gerador de tabela",
    description:
      "Preencha a grade e depois insira o código da tabela no cursor. Cole a partir de uma planilha para preenchê-la.",
    style: "Filetes",
    styles: {
      booktabs: "Booktabs",
      grid: "Grade",
    },
    placement: "Posicionamento flutuante",
    caption: "Legenda",
    label: "Rótulo",
    header: "Linha de cabeçalho",
    cellsAreLatex: "As células contêm LaTeX",
    preview: "Código LaTeX",
    columnAlign: "Alinhamento da coluna {{column}}",
    columnWidth: "Largura da coluna {{column}}",
    align: {
      l: "Esquerda",
      c: "Centro",
      r: "Direita",
      p: "Parágrafo",
    },
    removeColumn: "Remover coluna {{column}}",
    removeRow: "Remover linha {{row}}",
    cellLabel: "Linha {{row}}, coluna {{column}}",
    rows: "Linhas",
    addRow: "Adicionar linha",
    addColumn: "Adicionar coluna",
    cancel: "Cancelar",
    insert: "Inserir tabela",
  },
  equation: {
    title: "Editor de equação",
    description: "Edite a fórmula e depois salve-a de volta no documento.",
    loading: "Carregando o editor de equações…",
    fallbackLabel: "LaTeX da equação",
    display: "Em destaque (centralizada)",
    keyboard: "Teclado virtual",
    cancel: "Cancelar",
    save: "Salvar",
  },
};

export default dict;
