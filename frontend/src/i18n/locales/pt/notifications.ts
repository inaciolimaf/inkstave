import type { Dict } from "../en/notifications";

const dict: Dict = {
  title: "Notificações",
  unreadAria: "Notificações, {{count}} não lidas",
  markAllRead: "Marcar todas como lidas",
  markRead: "Marcar como lida",
  notification: "Notificação",
  dismiss: "Dispensar notificação",
  accept: "Aceitar",
  empty: "Você está em dia.",
  loadFailed: "Não foi possível carregar as notificações.",
  invite: {
    prefix: "{{inviter}} convidou você para ",
    suffix: " como {{role}}",
    defaultInviter: "Alguém",
    defaultProject: "um projeto",
    defaultRole: "colaborador",
  },
  fallbackMessage: "Você tem uma nova notificação.",
};

export default dict;
