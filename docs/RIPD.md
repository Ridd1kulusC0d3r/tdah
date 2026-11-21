# Relatório de Impacto à Proteção de Dados Pessoais (RIPD) — Agora 2.0

> Rascunho técnico para o encarregado e o advogado completarem. LGPD art. 5º, XVII, e art. 38. Campos entre colchetes a preencher.

**Controlador:** [RAZÃO SOCIAL], CNPJ [ ] · **Encarregado:** [NOME, e-mail] · **Responsável técnico pelos serviços psicológicos:** Deivison Mendes, CRP-04/65709 · **Data:** [ ] · **Versão do sistema:** 2.0.0

## 1. Por que este relatório

O Agora trata **dados pessoais sensíveis de saúde** (humor, sono, medicação, triagem de TDAH, mensagens a profissionais) de pessoas que podem estar em sofrimento, e conecta essas pessoas a serviços psicológicos pagos. Os dois fatos pedem avaliação de impacto.

## 2. Descrição do tratamento

| Operação | Titulares | Dados | Finalidade | Base legal | Onde fica | Prazo |
|---|---|---|---|---|---|---|
| Uso do app sem conta | Pacientes | Diário, tarefas, rotinas, foco, triagem | Funcionamento | Não há tratamento pelo controlador | Só no aparelho | Enquanto a pessoa quiser |
| Conta | Pacientes, profissionais | Nome, e-mail, hash de senha, registro (CRP), contato | Identificação | Execução de contrato (7º, V) | Servidor | Até a exclusão |
| Cópia na nuvem (Plus) | Pacientes | Todo o conteúdo do app | Trocar de aparelho | Consentimento específico (11, I) | Servidor, **cifrado** | Até a exclusão |
| Vínculo com profissional | Pacientes | Só as categorias liberadas | Acompanhamento entre sessões | Consentimento específico (11, I) e tutela da saúde (11, II, f) | Servidor, **cifrado** | Até desvincular |
| Pedido de contato ao profissional | Pacientes | Motivo (texto livre) | Atendimento | Tutela da saúde (11, II, f) | Servidor, **cifrado** | Até a exclusão |
| Formulário de interesse | Público | Nome, e-mail, telefone, mensagem | Responder ao pedido | Consentimento (7º, I) | Servidor, mensagem **cifrada** | 24 meses sem conversão |
| E-mails de conteúdo | Quem aceitou | E-mail, nome | Conteúdo educativo | Consentimento (7º, I) | Servidor | Até descadastro + 24 meses |
| Turmas e missões | Inscritos | Inscrição, missões feitas, anotações | Programa em grupo | Contrato e tutela da saúde | Servidor, anotações **cifradas** | Até a exclusão |
| Compras | Compradores | Produto, valor, referência do provedor | Entrega, obrigação fiscal | Contrato e obrigação legal (7º, II e V) | Servidor | 5 anos (anonimizado após exclusão) |
| Notificações | Quem ligou | Endpoint do navegador, horários | Lembretes | Consentimento | Servidor | Até desligar |
| Métricas do funil | Visitantes | Evento, item, origem, plataforma — **sem identificação** | Melhorar o produto | Legítimo interesse; dado anônimo | Servidor | 13 meses |
| Auditoria | Profissionais, pacientes | Quem viu o quê, quando | Segurança e guarda profissional | Obrigação legal e legítimo interesse | Servidor | 5 anos |
| Logs de acesso | Todos | IP, rota (sem query), status | Segurança | Marco Civil art. 15 | Saída do contêiner | 6 meses |

**Operadores:** hospedagem [ ], provedor de pagamento [Mercado Pago/Stripe], Google Play, SMTP [ ], armazenamento S3 [ ] (recebe só backup cifrado), serviços de push dos navegadores (recebem só um aviso vazio).

## 3. Necessidade e proporcionalidade

- **Local primeiro:** sem conta, nada sai do aparelho.
- **Minimização no vínculo:** o servidor filtra o que o profissional vê por categoria consentida (`filtra_snapshot`); notas pessoais nunca são enviadas.
- **Funil anônimo:** eventos de visita e clique não guardam id de usuário nem IP.
- **Separação clínica × comercial:** nenhuma oferta é disparada por dado clínico; o aviso de humor baixo mostra só caminhos públicos de cuidado (CVV 188, UBS, cadastro do CFP). Paciente vinculado não vê serviços psicológicos de terceiros.

## 4. Riscos e medidas

| Risco | Probabilidade | Impacto | Medidas implementadas | Risco residual |
|---|---|---|---|---|
| Cópia do banco (invasão do servidor, backup exposto) | Média | Alto | Campos de saúde cifrados com ChaCha20-Poly1305 e AAD por tipo; backup cifrado em blocos autenticados; chave fora do banco | Baixo se a chave não vazar junto |
| Roubo de conta de administrador | Média | Alto | 2FA (TOTP) obrigatória na administração; códigos de recuperação só como hash; código de uso único | Baixo |
| Força bruta em login | Alta | Médio | Limite persistente por IP e e-mail; resposta igual para e-mail inexistente; PBKDF2 200 mil iterações | Baixo |
| Injeção de script (XSS) | Baixa | Alto | CSP com hash por script, sem `unsafe-inline`/`eval`; escape de toda saída; `frame-ancestors 'none'` | Baixo |
| Profissional vê mais do que o consentido | Baixa | Alto | Filtro no servidor; auditoria de cada visualização; desvínculo apaga a cópia | Baixo |
| Uso comercial de dado clínico | Baixa | Alto (ético e legal) | Regra no código e no teste automático; catálogo veta termos de desconto/promessa | Baixo |
| Perda de dados | Baixa | Alto | Backup diário verificado, cópia externa, roteiro de restauração testado | Baixo |
| Vazamento por log | Baixa | Médio | Logs sem corpo e sem query string; erros guardam só a pilha | Baixo |
| Transferência internacional | [ ] | Médio | [Avaliar país do S3/hospedagem; cláusulas-padrão da ANPD se fora do Brasil] | [ ] |
| Menores de idade | Baixa | Alto | Termos: uso por adultos; [definir verificação] | [ ] |

## 5. Direitos dos titulares

Acesso e portabilidade (`Ver meus dados guardados`, JSON completo), correção (no app), exclusão (no app e pela web, com cancelamento de assinatura e anonimização de pagamentos), revogação de consentimentos (vínculo, conteúdo por e-mail com descadastro em um clique, notificações).

## 6. Conclusão

[Parecer do encarregado: o tratamento é necessário e proporcional? Riscos residuais aceitáveis? Ações pendentes com prazo.]

**Pendências antes do lançamento:** preencher operadores e países; revisão jurídica; definir política de verificação de idade; aprovação formal deste relatório.
