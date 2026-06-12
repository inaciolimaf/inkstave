import type { Dict } from "../en/sharing";

const dict: Dict = {
  dialog: {
    title: "Compartilhar projeto",
    description: "Convide colaboradores e gerencie quem tem acesso.",
  },
  invite: {
    label: "Convidar por e-mail",
    placeholder: "nome@exemplo.com",
    roleLabel: "Papel do convite",
    submit: "Convidar",
    invalidEmail: "Informe um endereço de e-mail válido.",
    sent: "Convite enviado para {{email}}",
    sendError: "Não foi possível enviar o convite.",
  },
  // Lowercase (shown with a `capitalize` CSS class) — see en/sharing.ts.
  role: {
    owner: "proprietário",
    editor: "editor",
    viewer: "visualizador",
  },
  members: {
    title: "Pessoas com acesso",
    sectionLabel: "Pessoas com acesso",
    loadError: "Não foi possível carregar os membros.",
    you: " (Você)",
    roleFor: "Papel de {{name}}",
    transfer: "Transferir",
    remove: "Remover",
    removeLabel: "Remover {{name}}",
    leave: "Sair do projeto",
    transferConfirm: {
      title: "Tornar {{name}} o proprietário?",
      description: "Você se tornará um editor. Isso não pode ser desfeito aqui.",
      action: "Transferir",
    },
    removeConfirm: {
      title: "Remover {{name}}?",
      description: "Eles perderão o acesso a este projeto.",
      action: "Remover",
    },
    leaveConfirm: {
      title: "Sair deste projeto?",
      description: "Você perderá o acesso até ser convidado novamente.",
      action: "Sair",
    },
    changeRoleError: "Não foi possível alterar o papel.",
    removeError: "Não foi possível remover o membro.",
    transferred: "Propriedade transferida.",
    transferError: "Não foi possível transferir a propriedade.",
  },
  pending: {
    title: "Convites pendentes",
    sectionLabel: "Convites pendentes",
    empty: "Nenhum convite pendente.",
    revoke: "Revogar",
    revokeLabel: "Revogar convite para {{email}}",
    revokeConfirm: {
      title: "Revogar convite para {{email}}?",
      description: "O link do convite deixará de funcionar.",
      action: "Revogar",
    },
    revokeError: "Não foi possível revogar o convite.",
  },
  confirm: {
    cancel: "Cancelar",
  },
  accept: {
    loading: "Carregando convite…",
    unavailableTitle: "Convite indisponível",
    unavailableDescription: "Este convite expirou ou não é mais válido.",
    backToProjects: "Voltar aos projetos",
    notFound: "Este convite não pôde ser encontrado.",
    invitedTo: "Você foi convidado para {{projectName}}",
    invitedBy: "{{inviterName}} convidou você para entrar como ",
    accept: "Aceitar",
    decline: "Recusar",
    joined: "Você entrou no projeto.",
    acceptError: "Não foi possível aceitar o convite.",
    declineError: "Não foi possível recusar o convite.",
  },
};

export default dict;
