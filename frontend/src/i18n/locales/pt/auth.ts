import type { Dict } from "../en/auth";

const dict: Dict = {
  login: {
    title: "Entrar no Inkstave",
    description: "Informe seu email e senha para continuar.",
    justRegistered: "Conta criada — faça login.",
    submit: "Entrar",
    noAccount: "Não tem conta?",
    createOne: "Criar uma",
    invalidCredentials: "Email ou senha inválidos.",
    tooManyAttempts: "Muitas tentativas. Tente novamente mais tarde.",
  },
  register: {
    title: "Crie sua conta",
    description: "Comece a escrever com o Inkstave.",
    submit: "Criar conta",
    haveAccount: "Já tem uma conta?",
    emailExists: "Já existe uma conta com este email.",
  },
  setup: {
    title: "Configurar o Inkstave",
    description: "Crie a primeira conta de administrador.",
    submit: "Criar administrador",
    statusError:
      "Não foi possível acessar o servidor para verificar o status da configuração. Tente novamente.",
    alreadyComplete: "A configuração já foi concluída. Redirecionando para o login…",
  },
  confirmEmail: {
    title: "Confirmar alteração de email",
    confirming: "Confirmando seu novo email…",
    done: "Seu email agora é {{email}}.",
    missingToken: "Este link está sem o token de confirmação.",
    failed: "Não foi possível confirmar a alteração de email.",
    goToSettings: "Ir para configurações",
  },
  fields: {
    email: "Email",
    emailPlaceholder: "voce@exemplo.com",
    adminEmailPlaceholder: "admin@exemplo.com",
    password: "Senha",
    confirmPassword: "Confirmar senha",
    displayName: "Nome de exibição",
  },
  validation: {
    emailRequired: "O email é obrigatório.",
    emailInvalid: "Informe um endereço de email válido.",
    passwordRequired: "A senha é obrigatória.",
    passwordMin: "A senha deve ter pelo menos 8 caracteres.",
    passwordMax: "A senha deve ter no máximo 72 caracteres.",
    passwordLetter: "A senha deve conter pelo menos uma letra.",
    passwordDigit: "A senha deve conter pelo menos um dígito.",
    confirmPasswordRequired: "Confirme sua senha.",
    passwordsMismatch: "As senhas não coincidem.",
    displayNameRequired: "O nome de exibição é obrigatório.",
    displayNameMax: "O nome de exibição deve ter no máximo 100 caracteres.",
  },
};

export default dict;
