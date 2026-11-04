# Glossary

Domain term → name in code → Portuguese product term. Every domain name in the code comes from here, and
a new term enters this file in the commit that introduces it.

The product is bilingual. Its interface text lives in `frontend/src/i18n/locales/en/` and
`frontend/src/i18n/locales/pt/`. The **Portuguese** column quotes those strings exactly. "—" means the
product shows no term for this concept in Portuguese, because it is internal.

## Naming conventions

| Where | Convention | Example |
|---|---|---|
| Python | `snake_case`, `PascalCase` for classes | `run_compile`, `TreeEntity` |
| TypeScript | `camelCase`, `PascalCase` for components and types | `useCompile`, `DiffReviewDialog` |
| Frontend files | module-local: new files `kebab-case`, older components `PascalCase` | `file-tree-panel.tsx`, `AgentPanel.tsx` |
| Database tables | plural `snake_case` | `revoked_sessions`, `compile_outputs` |
| API routes | `/api/v1/...`, plural `kebab-case` | `/api/v1/projects` |
| Environment variables | `UPPER_SNAKE_CASE`; never renamed once a server may set them | `RATE_LIMIT_LOGIN_IP` |

**What stays in the product's language on purpose:** interface strings, one locale file per namespace.
The terms `hunk`, `diff` and `editor` stay as they are in Portuguese. Backend error messages and e-mails
are English-only today ([known gaps](known-gaps.md)).

## Accounts and sessions

| Term | Code | Portuguese |
|---|---|---|
| Account, user | `User`, `users` | "conta" |
| Sign in | `login` | "Entrar" |
| Create account | `register` | "Criar conta" |
| Password | `password_hash` | "Senha" |
| Display name | `display_name` | "Nome de exibição" |
| Settings | module `settings` | "Configurações" |
| Profile | `/api/v1/me` | "Perfil" |
| Access and refresh token pair | `TokenPair` | — |
| Session | `sid`, equal to `family_id` | — |
| Account version | `users.session_version`, claim `sv` | — |
| Revoked session | `RevokedSession`, `revoked_sessions` | — |
| Deactivated account | `is_active=false` | — |
| Login limit | `LoginThrottle` | "Muitas tentativas. Tente novamente mais tarde." |
| Link token | `AuthToken`, `auth_tokens` | — |
| Magic link | `magic_login` | "Entrar com um link" |
| Password reset | `password_reset` | "Redefinir sua senha" |
| E-mail verification | `email_verify` | "Verifique seu email" |
| E-mail change | `pending_email` | "Confirmar alteração de email" |
| First admin | `ensure_initial_admin` | "Criar administrador" |

## Projects, files and documents

| Term | Code | Portuguese |
|---|---|---|
| Project | `Project` | "Projeto" |
| File tree | `TreeEntity` | "Arquivos" |
| Folder | `TreeEntityType.folder` | "Pasta" |
| File | `TreeEntity`, type `file` | "Arquivo" |
| Document (editable text) | `doc`, `DocumentContent` | "documento" |
| Upload | `upload_file` | "Enviar arquivo" |
| Root (of the tree) | `root` | "raiz" |
| Import | `import_project_zip` | "Importar um projeto" |
| Export | `export_project_zip` | "Baixar como .zip" |
| Delete (soft) | `soft_delete_project` | "Excluir" |
| Version conflict | `VersionConflictError` | "Conflito" |
| Keep mine | `resolveKeepMine` | "Manter minha versão" |
| Reload server version | `resolveReload` | "Recarregar versão do servidor" |
| Saved, saving | `SaveStatus` | "Salvo", "Salvando…" |
| Unsaved changes | `SaveStatus` | "Alterações não salvas" |

## Compile and preview

| Term | Code | Portuguese |
|---|---|---|
| Compile | `Compile`, `run_compile`, `CompileButton` | "Compilar", "compilação" |
| Queued | `CompileJobStatus.QUEUED` | "Na fila…" |
| Cancel compile | `cancel_compile` | "Cancelar compilação" |
| Compile log | `output.log` | "Registro da compilação" |
| Compile output | `compile_outputs` | "Saída da compilação" |
| Problems | `CompileProblems` | "Problemas" |
| Errors, warnings | `ProblemSeverity` | "Erros", "Avisos" |
| Typesetting (info severity) | `ProblemSeverity.info` | "Composição" |
| PDF preview | module `pdf-preview` | "Prévia do PDF" |
| Sandbox | `SandboxedTectonicRunner` | — |
| Coalesce (reuse an in-flight compile) | `compile_debounce_coalesce` | — |
| SyncTeX index | `SyncTexIndex` | — |

## Collaboration

| Term | Code | Portuguese |
|---|---|---|
| Room | `Room` | — |
| CRDT document | `YDocument` | — |
| Presence | `AwarenessRegistry` | "Pessoas online" |
| Connection status | `ProviderStatus` | "Ao vivo", "Conectando…", "Reconectando…", "Offline" |

## Sharing and authorization

| Term | Code | Portuguese |
|---|---|---|
| Role | `role`, `MembershipRole` | "papel" |
| Owner | `MembershipRole.owner` | "proprietário" |
| Editor | `MembershipRole.editor` | "editor" |
| Viewer | `MembershipRole.viewer` | "visualizador" |
| Member, collaborator | `ProjectMembership` | "membro", "colaborador" |
| Invite | `ProjectInvite` | "Convite" |
| Pending invites | `InviteStatus.pending` | "Convites pendentes" |
| Share | module `sharing` | "Compartilhar" |
| Read-only | `isReadOnly` | "Somente leitura" |
| Ownership transfer | `transfer_ownership` | "Transferir" |
| Leave project | `MembershipStatus.left` | "Sair do projeto" |
| Revoke | `revoke_invite` | "Revogar" |
| Accept, decline | `accept_invite`, `decline_invite` | "Aceitar", "Recusar" |
| Capability | `Capability` | — |

## History

| Term | Code | Portuguese |
|---|---|---|
| Version history | `HistoryUpdate`, `list_versions` | "Histórico de versões" |
| Version | `HistoryUpdate.version` | "versão" |
| Label | `HistoryLabel` | "rótulo" |
| Restore | `restore_document` | "Restaurar" |
| Version diff | `DiffResponse` | "Diferenças da versão" |
| Chunk | `HistoryChunk` | — |
| Snapshot | `base_snapshot`, `crdt_document_state` | — |
| Compaction | `compact_history` | — |

## Notifications and e-mail

| Term | Code | Portuguese |
|---|---|---|
| Notification | `Notification`, `AppNotification` | "Notificação" |
| Mark all read | `read_at` | "Marcar todas como lidas" |
| Dismiss | `dismissed_at` | "Dispensar notificação" |

## AI agent

| Term | Code | Portuguese |
|---|---|---|
| Agent | module `agent` | "Agente de IA" |
| Session (conversation) | `AgentSession`, `ChatSession` | "Sessões", "Conversa" |
| Run | `run_agent_turn`, `AgentRunState` | "execução" |
| Proposed changes | `ProposedDiff` | "Mudanças propostas" |
| Stage an edit | `StagedEdit`, `propose_edit` | "Propôs uma edição" |
| Review | `DiffReviewDialog` | "Revisar mudanças" |
| File operation | `ProposedFileOp`, `StagedFileOp`, `FileOpCard` | "Criar arquivo", "Excluir", "Renomear ou mover" |
| Selection sent to the agent | `AgentQuote`, `withQuote` | "Pedir ao agente" |
| File drawer | `FileDrawer` | "Arquivos" |
| Hunk | `hunks`, `hunk_count` | "hunk" |
| Budget | `agent_budget_exceeded` | "Orçamento atingido" |
| Rate limit | `agent_rate_limited` | "Limite de uso atingido" |

## Spell check

| Term | Code | Portuguese |
|---|---|---|
| Spell check | `spellcheck`, `SpellLanguage` | "Ortografia" |
| Personal dictionary | `user_dictionary_words`, `usePersonalDictionary` | "Dicionário pessoal" |

## Platform

| Term | Code | Portuguese |
|---|---|---|
| Unit of work | `get_db_session` | — |
| Connection deadlines | `db_lock_timeout_s`, `db_statement_timeout_s` | — |
| Composition root | `app`, `cli`, `main`, `models`, `router`, `worker` | — |
| Import exception | `ignore_imports` | — |
| Request id | `request_id_var`, `X-Request-ID` | — |

## Open inconsistencies in the Portuguese text

These are recorded, not settled. Decide with the user before changing a locale file.

| Concept | Both forms in use |
|---|---|
| E-mail | "email" (`auth`) and "e-mail" (`settings`, `sharing`) |
| Preview | "prévia" and "Pré-visualizar", "Pré-visualização" |
| Changes | "Mudanças" and "Alterações" |
| Try again | "Tentar de novo" and "Tentar novamente" |
| Sign out, leave | "Sair" means both |
