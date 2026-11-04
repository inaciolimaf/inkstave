import type { Dict } from "../en/settings";

const dict: Dict = {
  page: {
    title: "Configurações",
    backToProjects: "Voltar aos projetos",
  },
  profile: {
    title: "Perfil",
    displayName: "Nome de exibição",
    save: "Salvar perfil",
    saving: "Salvando…",
    updated: "Perfil atualizado.",
  },
  editor: {
    title: "Preferências do editor",
    description: "Aplicadas ao seu editor imediatamente e salvas na sua conta.",
    theme: "Tema",
    themeSystem: "Sistema",
    themeLight: "Claro",
    themeDark: "Escuro",
    fontSize: "Tamanho da fonte",
    keymap: "Atalhos de teclado",
    keymapDefault: "Padrão",
    keymapVim: "Vim",
    keymapEmacs: "Emacs",
    autocomplete: "Autocompletar",
  },
  email: {
    title: "E-mail",
    current: "Atual:",
    pending: "· pendente: {{email}}",
    sentPrefix: "Enviamos um link de confirmação para ",
    sentSuffix: ". A alteração entra em vigor assim que você confirmar.",
    newEmail: "Novo e-mail",
    password: "Senha",
    submit: "Alterar e-mail",
    sending: "Enviando…",
    success: "Confirmação enviada.",
  },
  password: {
    title: "Senha",
    description: "Alterá-la encerra suas outras sessões.",
    current: "Senha atual",
    new: "Nova senha",
    confirm: "Confirmar nova senha",
    mismatch: "As senhas não coincidem.",
    submit: "Alterar senha",
    changing: "Alterando…",
    success: "Senha alterada. Faça login novamente.",
  },
  danger: {
    title: "Excluir conta",
    description:
      "Exclui permanentemente sua conta e os projetos de sua propriedade. Isso não pode ser desfeito.",
    trigger: "Excluir minha conta",
    dialogTitle: "Excluir sua conta?",
    dialogDescription: "Digite sua senha e escreva DELETE para confirmar. Seus projetos serão removidos.",
    password: "Senha",
    typeDelete: "Escreva DELETE",
    submit: "Excluir conta",
    deleting: "Excluindo…",
    success: "Conta excluída.",
  },
  error: {
    generic: "Algo deu errado.",
  },
  dictionary: {
    title: "Dicionário pessoal",
    description:
      "As palavras que você adiciona deixam de ser sublinhadas em todos os projetos. Ficam salvas na sua conta, até 5000 palavras.",
    empty:
      "Nenhuma palavra ainda. Clique com o botão direito numa palavra sublinhada no editor para adicioná-la.",
    removeWord: "Remover {{word}}",
    remove: "Remover",
  },
};

export default dict;
