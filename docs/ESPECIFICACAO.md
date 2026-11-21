# Agora — especificação do produto (v2.1)

Documento de produto e engenharia. O manual ilustrado (`docs/manual.html`) explica o uso; este arquivo explica **o que foi construído, por quê e o que vem depois**.

## 1. Tese

Apps de TDAH resolvem pedaços (timer, lista, rotina, humor) e deixam o profissional de fora. O Dietbox mostrou, na nutrição, que o modelo **profissional assina e prescreve, paciente usa de graça** funciona. Ainda falta uma pesquisa de mercado que mostre se já existe algo equivalente para TDAH no Brasil.

O Agora junta as duas coisas:

1. **Ferramenta gratuita e completa para quem tem TDAH**, construída em torno de uma única pergunta: *qual é a próxima ação?*
2. **Ponte para o cuidado**: quando a base de usuários crescer, o mesmo app vira canal de chegada para terapia, com o profissional prescrevendo rotinas e acompanhando a adesão entre sessões.

## 2. Engenharia reversa das referências

| App | Mecânica que funciona | Lacuna observada | Como o Agora responde |
|---|---|---|---|
| **TDAH** (tk.tdah · 100 mil+ downloads · nota 3,7) | Triagem ASRS 1.1 e SNAP-IV; biblioteca de técnicas; fonte para dislexia | É quase todo leitura. A avaliação mais votada (523 votos) diz que ler tudo dá ansiedade; outra aponta dicas sem curadoria que prejudicam. Usa reconhecimento facial de humor. | Nada de biblioteca para ler: cada tela pede **uma ação**. Triagem ASRS mantida como rastreio. Humor por cor, sem câmera. Fonte de alta legibilidade (Atkinson Hyperlegible). |
| **Tiimo** | Linha do tempo visual contra cegueira temporal; humor junto das tarefas; web + celular + relógio | Sem profissional no circuito; foco em iOS | Tempo sempre visível (anel do timer, minutos por passo, relógio na aba). Humor entra na escolha da próxima tarefa. |
| **Motion / Sunsama** | IA reorganiza o dia; planejamento guiado; timeboxing | Caros, em inglês, pensados para trabalho de escritório | Priorização transparente por regras (o app diz *por que* escolheu), considerando energia do dia. |
| **Todoist** | Entrada rápida; prioridade visível | Lembretes pouco adaptados a TDAH | Despejo de várias linhas de uma vez e botão "+ ideia" que não tira da tela atual. |
| **Routinery** | Rotina em passos com cronômetro por passo | Premium já a partir da 3ª rotina (R$ 115,90/ano) | Player de rotina igual, **sem limite** no plano grátis. |
| **Focus Keeper / Forest** | Pomodoro; recompensa visual | Só foco, sem plano | Foco nasce da próxima ação, registra a sessão e pergunta "como foi?". |
| **Freedom / One Sec** | Bloqueio e pausa antes do app impulsivo | Exige permissões de sistema | Fora da v1 (precisa de app nativo). Check-in gentil "ainda na tarefa?" cobre parte do efeito. |
| **Flown / Focusmate** | Body doubling | Comunidade em inglês, por vídeo | Sala de foco: quem está focando agora, sem câmera. Modo solo com check-ins. |
| **Endel / ADHD White Noise** | Ruído branco, rosa e marrom | Commodity | Os três ruídos gerados no próprio navegador, sem baixar arquivos. |
| **How We Feel** | Check-in emocional por cor | Desligado das tarefas | Diário de humor, energia, sono e atividade alimenta a priorização e o painel. |
| **Sweepy** | Tarefas da casa por cômodo | Nicho doméstico | Fica para o roadmap como "pacotes de rotinas". |
| **Dietbox** (modelo de negócio) | Profissional prescreve; paciente usa app gratuito com plano, diário, lembretes, chat | — | Prescrição de rotinas, tarefas e recados; adesão e resumo para sessão no painel. |

A fonte do Reddit (r/ADHD_Programmers) bloqueou o acesso automatizado e ficou fora desta análise.

## 3. Princípios de design para TDAH

1. **Uma ação por vez.** A tela inicial mostra uma tarefa, o motivo da escolha e um botão grande. O resto fica atrás de "Depois, se der".
2. **Ler pouco.** Frases curtas, nenhuma tela de texto corrido no fluxo principal.
3. **Começar é a parte difícil.** "Quebrar em passos", "Sugerir um começo" (abrir o arquivo, fazer 2 minutos, decidir o próximo passo) e durações de 10 a 50 min.
4. **Sem culpa.** "Agora não" devolve a tarefa amanhã; rotina parada no meio conta como progresso.
5. **Tempo visível.** Anel de tempo, minutos por passo, relógio na aba do navegador.
6. **Energia, não só prazo.** O humor/energia do dia muda o que o app sugere.
7. **Configuração zero.** Abre funcionando, com exemplo; começar do zero pede só nome e o que está na cabeça.
8. **Recompensa imediata.** Placar de dias seguidos, minutos de hoje e feitas hoje.

## 4. O que a v2.0 entrega

**Pronto para produção.** Dados de saúde cifrados no banco (ChaCha20-Poly1305, RFC 8439, implementação própria conferida contra os vetores oficiais e contra a biblioteca `cryptography`, que é usada automaticamente quando instalada); rotação de chave sem parada; migrações versionadas (`PRAGMA user_version`) com cifragem dos dados antigos na partida; verificação em duas etapas (TOTP, RFC 6238) com 8 códigos de recuperação, obrigatória na administração; limite de tentativas gravado no banco (sobrevive a reinício); Content-Security-Policy com hash de cada script, sem `unsafe-inline`; HSTS e cabeçalhos de isolamento; logs JSON sem query string e sem corpo; tabela de erros com alerta por e-mail; backup diário conferido, cifrado e enviado a S3 (SigV4 próprio), com restauração testada; servidor recusa ligar em produção sem chave, HTTPS, pagamento e SMTP; workflow de testes no GitHub Actions com e sem `cryptography`; perfil de homologação no Docker Compose.

**Funil de cuidado.** Catálogo de serviços (terapia, grupos, treinos de habilidades sociais da Lume, e-books, empresas, psicólogos) com regras no servidor: paciente vinculado não vê serviço psicológico de terceiros; no Android só aparecem atendimentos individuais ao vivo e formulários (regra do Google Play); todo serviço psicológico leva nome e CRP do responsável técnico; o painel recusa desconto, promoção e promessa de resultado. Formulário de interesse com aceite explícito, armadilha para robôs e mensagem cifrada; 3 e-mails de conteúdo só para quem aceitou, com descadastro em um clique (RFC 8058); eventos de funil anônimos. Turmas com vagas, pagamento, lista de espera que chama o próximo quando abre vaga, link da sala só para confirmados e 8 missões semanais nos treinos da Lume. Compra avulsa de sessão e e-book pelos mesmos provedores, com link de download assinado de 10 minutos e estorno pelo painel. Painel de administração: receita de 30 dias contra a meta de R$ 30 mil, recorrente mensal, funil, contatos, turmas, compras, catálogo e erros.

**Para o paciente.** Lembretes com o app fechado no navegador (Web Push sem conteúdo: o texto vem do servidor do Agora, nada passa pelos serviços de push), conflito de cópia na nuvem resolvido pela pessoa, importação de tarefas de .txt/.md/.csv (Todoist, Trello, Notion), convite por link e, no aviso de semana pesada, só acolhimento e caminhos públicos (CVV 188, UBS, cadastro do CFP), sem oferta de serviço.

**Para o profissional.** Convite por link com envio pelo WhatsApp e verificação em duas etapas.

**Documentos de operação:** `docs/PRODUCAO.md` (roteiro), `docs/INCIDENTES.md` (resposta a incidentes, ANPD em 3 dias úteis) e `docs/RIPD.md` (relatório de impacto, rascunho para o encarregado).

### v1.3

**Novidades da v1.3 (visual):** uma família tipográfica só, a Atkinson Hyperlegible Next, desenhada pelo Braille Institute para leitura fácil (letras que não se confundem, como 0 e O). Papel pedra frio, tinta verde-escura, botão de ação em verde-pinho e um amarelo de marca-texto reservado para o que é "agora": o passo atual, a tela atual e o paciente selecionado no painel. Sem sombras pesadas, gradientes ou rótulos em maiúsculas; prioridade virou ponto colorido com a palavra. O único movimento automático é o marca-texto passando no passo atual, e ele some com "menos animação" ou com a preferência do sistema. As fontes ficam dentro do app (sem pedido ao Google Fonts), o que melhora a privacidade e faz o visual funcionar sem internet e no Android. Ícone e tela de abertura novos (`ferramentas/gerar_icones.py`).

### v1.2

**Novidades da v1.2:** site público (apresentação, preços, privacidade, termos e exclusão de conta pela web); pagamentos com Mercado Pago (Pix, cartão, boleto e assinatura recorrente) e Stripe, com modo simulado para testes; planos Plus mensal e anual e Agora Pro para profissionais (grátis até 3 pacientes); webhooks com assinatura HMAC, consulta à API do provedor e gravação idempotente; carência de 3 dias; cancelamento que mantém o acesso até o fim do período; validação de compras do Google Play com JWT RS256 próprio e notificações RTDN (fase 2); recuperação de senha por e-mail, limite de tentativas de login, exclusão e exportação de conta; cópia na nuvem, sala com pessoas, relatório do mês e sons extras para o Plus; lembretes (nativos no Android, no navegador com o app aberto); projeto Android com Capacitor e build automático no GitHub Actions; implantação com Docker, Caddy (HTTPS) e backup diário do banco.

### Regra do Google Play que define o pagamento no Android
Assinaturas digitais compradas dentro de um app distribuído pela Play precisam usar o Google Play Billing, e o app não pode direcionar o usuário para pagar fora. Por isso, na v1.2 o app Android não vende o Plus: quem assinou no site entra na conta e o Plus é liberado (o servidor também recusa checkout com o cabeçalho de plataforma Android). Sessões de terapia são serviços clínicos 1:1 e ficam fora dessa exigência. A venda do Plus pelo Play Billing é a fase 2 do plano; o lado do servidor já está pronto e testado.

### v1.1

**Novidades da v1.1:** humor por carinhas (no diário, na pergunta rápida, no calendário e no painel do profissional); tarefas tipificadas (trabalho, estudo, casa, saúde, finanças, pessoal) com prioridade alta/média/baixa, agrupamento por prioridade e filtro por tipo; módulo de **Cursos** (aulas totais e feitas, prazo, prioridade, ritmo semanal para o prazo, próxima aula no Agora, foco ligado ao curso); painel com período 7/14/28 dias, comparação com o período anterior, calendário do humor, distribuição do humor, sono com faixa de 7 a 9 h, atividade semanal contra a meta de 150 min da OMS, foco por dia da semana, foco por tipo e progresso dos cursos; **sete temas** (Automático, Claro, Clean, Escuro, Matrix, Oceano, Lavanda); acabamento visual revisado (cartão de ação com faixa do tipo, barra de passos segmentada, indicadores com minigráficos).


### App do paciente (web + celular, instalável como PWA)
| Módulo | Entregue |
|---|---|
| Agora | Próxima ação com motivo; passos marcáveis; foco 10/15/25/50 min; Terminei; Agora não; fila "Depois, se der" com "fazer esta agora"; humor em um toque; recado do profissional; placar |
| Tarefas | Despejo multilinha com tipo, prioridade e energia; agrupadas por prioridade; filtro por tipo; edição com prazo e passos; concluídas recolhidas |
| Cursos | Total/feitas, prazo, prioridade, plataforma, horas; ritmo para o prazo; +1 aula; estudar agora (foco ligado ao curso); próxima aula entra na priorização |
| Rotinas | Criar/editar ("passo \| minutos"); horário; player passo a passo com tempo e bipe; histórico de 7 dias; rotinas prescritas com selo |
| Foco | Anel de tempo; pausa; ruído branco/rosa/marrom; check-in gentil a cada 10 min; sala de foco (com conta) ou modo solo; registro "fluiu/ok/travei"; tela sempre acesa quando o navegador permite |
| Diário | Humor (carinhas), energia, horas e qualidade do sono, minutos e tipo de atividade física, medicação (opcional), nota; últimos 7 dias |
| Painel | Período 7/14/28 dias; 5 indicadores com tendência; foco × humor; calendário e distribuição do humor; sono (horas e qualidade); atividade semanal × meta OMS; foco por dia da semana e por tipo; cursos; comparações dos próprios dados (sono ≥ 7 h × foco; atividade × humor; noite boa × humor) com tamanho da amostra |
| Triagem | ASRS 1.1 parte A, corte por item, resultado com orientação, histórico |
| Planos e terapia | Grátis / Plus R$ 9,90 (lista de espera) / Com psicólogo; pedido de contato; orientação para achar psicólogo (CRP, SUS) |
| Segurança emocional | Humor 1 abre apoio com CVV 188 e SAMU 192; aviso gentil após semana de humor baixo, no máximo 1×/semana |
| Dados | Local-first (localStorage); backup por copiar/colar; apagar tudo com confirmação; tema claro/escuro; letra maior; menos animação |

### Painel do profissional
Login próprio; código de convite de uso único; lista ordenada por atenção (pedido de contato, humor baixo, pouca adesão); visão geral (6 indicadores de 7 dias, gráfico de 28 dias, adesão por rotina, histórico ASRS, tarefas); diário dia a dia; prescrição de rotina/tarefa/recado e arquivamento; pedidos de contato; resumo pronto para prontuário.

### Servidor da clínica
Python somente biblioteca padrão (`http.server` + `sqlite3`). Senhas PBKDF2-SHA256 (200 mil iterações), tokens guardados só como hash, consentimento por categoria aplicado no servidor (o que não foi autorizado nunca é gravado), desvincular apaga o snapshot, trilha de auditoria de visualizações e prescrições, proteção contra path traversal, limite de 2 MB por envio.

## 5. Modelo de dados (paciente, local)

```
profile {name}
tasks[] {id, title, type: trabalho|estudo|casa|saude|financas|pessoal, priority: alta|media|baixa, energy: baixa|media|alta, created, due?, steps[{t, done}], done, doneAt?, snooze?, pin?, from?, prescId?}
courses[] {id, name, platform, total, done, hours?, deadline?, priority, pin?, snooze?}
routines[] {id, name, time?, steps[{t, min}], from?, prescId?}
routineRuns[] {date, routineId, done, total, skipped?}
sessions[] {date, min, taskId? ("c:<id>" para curso), type, feel: fluiu|ok|travei}
checkins{YYYY-MM-DD: {mood 1-5, energy 1-5, sleepH, sleepQ 1-5, activityMin, activityType, meds, note}}
screenings[] {date, type: ASRS-A, answers[6], positives, positive}
notes[] {from, text, date, presc?}
settings {focusMin, showMeds, big, calm, gentle, sound, skin: auto|claro|clean|escuro|matrix|oceano|lavanda}
link {token, email, pro, consent{checkins, foco, rotinas, tarefas, triagem}, lastSync}
```

Consentimento → campos enviados: `checkins`→checkins · `foco`→sessions · `rotinas`→routines, routineRuns · `tarefas`→tasks, courses · `triagem`→screenings. Notas, ajustes e o próprio vínculo nunca saem do aparelho.

## 6. API

| Método | Caminho | Quem | Faz |
|---|---|---|---|
| GET | /api/health | todos | versão |
| POST | /api/registrar · /api/entrar · /api/sair | todos | conta e sessão |
| GET | /api/eu | logado | perfil, vínculo e prescrições ativas |
| POST | /api/paciente/vincular | paciente | usa código + consentimento |
| POST | /api/paciente/consentimento | paciente | muda o que é compartilhado |
| POST | /api/paciente/sync | paciente | envia snapshot (filtrado) e recebe prescrições |
| POST | /api/paciente/contato | paciente | pedido de contato |
| POST | /api/paciente/desvincular | paciente | encerra e apaga snapshot |
| POST | /api/pro/convite | profissional | gera código de 6 caracteres |
| GET | /api/pro/pacientes | profissional | lista com adesão de 7 dias |
| GET | /api/pro/pacientes/:id | profissional | ficha (7 e 28 dias) |
| POST | /api/pro/pacientes/:id/prescrever | profissional | rotina, tarefa ou recado |
| POST | /api/pro/prescricoes/:id/arquivar | profissional | encerra prescrição |
| POST | /api/pro/pedidos/:id/visto | profissional | marca pedido como visto |
| POST/GET | /api/sala/entrar · batimento · sair · /api/sala | logado | sala de foco |

## 7. Privacidade, ética e regulação

- **LGPD.** Humor, sono, medicação e triagem são dados pessoais sensíveis de saúde (art. 11). Por isso: consentimento por categoria, destacado e revogável; nada sai do aparelho sem vínculo; desvincular apaga a cópia da clínica; auditoria de acesso. Antes de produção: política de privacidade, registro das operações, encarregado (DPO), contrato de operador com a hospedagem e criptografia do banco em repouso.
- **Psicologia.** Serviços psicológicos mediados por tecnologia seguem a resolução do CFP sobre o tema (Res. CFP 11/2018 e atualizações; conferir a versão vigente e o cadastro e-Psi). O painel não armazena prontuário: o resumo é texto para o profissional colar no próprio prontuário.
- **Não é dispositivo médico.** O app se posiciona como apoio à organização e bem-estar. A ASRS é apresentada como rastreio, nunca como diagnóstico. Qualquer função que passe a diagnosticar ou indicar tratamento pode enquadrar o software como dispositivo médico (Anvisa, RDC 657/2022) e exige avaliação regulatória antes.
- **ASRS.** O texto em português do app é uma redação de trabalho. Antes de uso clínico ou comercial, substituir pela versão brasileira validada e conferir a licença de uso junto aos detentores do instrumento (OMS/Harvard).
- **Funil ético.** Humor baixo nunca dispara oferta paga. O aviso de semana pesada leva a "como falar com alguém" e aparece no máximo uma vez por semana. Em humor 1, o app mostra CVV 188 e SAMU 192 antes de qualquer outra coisa.
- **Sem biometria.** Reconhecimento facial de humor foi descartado de propósito.

## 8. Modelo de negócio

| Fase | Receita | Gatilho para avançar |
|---|---|---|
| 1. Base | Grátis completo. Plus R$ 9,90/mês (sincronização multi-aparelho, sala com pessoas, relatório mensal, temas). | Retenção D30 acima de 20% |
| 2. Profissionais | Assinatura do profissional no modelo Dietbox (faixa a validar: R$ 49 a R$ 99/mês) com pacientes ilimitados no app grátis. | 50 profissionais ativos |
| 3. Terapia | Pedidos de contato encaminhados a uma rede de psicólogos parceiros; o app vira canal de aquisição para atendimento. | Taxa de pedido de contato × conversão em 1ª sessão |

**Métricas de produto:** ativação (1ª sessão de foco no dia 1), dias com diário por semana, minutos de foco por semana, retenção D1/D7/D30, conversão para Plus, pedidos de contato, adesão a rotinas prescritas.

## 9. Estado de cada parte (tabela única, 21/11/2026)

Esta é a única fonte de verdade sobre o que existe. **Implementado** = código e testes automáticos no repositório. **Simulado** = funciona contra um provedor de teste ou falso, sem conta real. **Homologado** = testado com a conta real do provedor. **Publicado** = no ar para o público.

| Parte | Implementado | Simulado | Homologado | Publicado |
|---|---|---|---|---|
| App do paciente (tarefas, cursos, rotinas, foco, diário, painel, relatório) | Sim | — | — | Protótipo estático pronto, aguardando hospedagem |
| Preparar minha próxima sessão (roteiro, seleção, prévia, envio) | Sim (2.1) | — | — | Protótipo (sem o envio) |
| Importar cursos (Lista Magna, painéis .html, planilhas) | Sim (2.1) | — | — | Protótipo |
| Fim do foco com avanço parcial e "onde parei" | Sim (2.1) | — | — | Protótipo |
| Triagem ASRS | Sim, **desligada** | — | — | Não: falta o texto brasileiro validado e a licença |
| Contas, vínculo, consentimento, prescrições, resumo para a sessão | Sim | — | — | Não |
| Painel do psicólogo | Sim | — | — | Não (protótipo mostra convite para o piloto) |
| Pagamentos Mercado Pago e Stripe (assinatura, Pix, avulsos, estorno) | Sim | Sim (transporte falso nos testes) | Não | Não |
| Google Play Billing | Sim (servidor) | Sim | Não | Não |
| Catálogo, interesse, turmas, missões, e-books, administração | Sim | — | — | Catálogo em vitrine no protótipo |
| E-mail (senha, confirmações, sequência de conteúdo) | Sim | Sim (caixa de saída local) | Não | Não |
| Web Push | Sim | Sim (assinatura VAPID conferida; sem entrega real) | Não | Não |
| Backup cifrado + S3 | Sim | Sim (envio falso nos testes) | Não | Não |
| Cifra dos dados | Sim (`cryptography` obrigatória em produção) | — | — | Não |
| App Android (Capacitor) | Projeto pronto | — | Build nunca rodou (Actions bloqueado por cobrança da conta) | Não |
| Testes no GitHub Actions | Workflows prontos | — | Não rodaram (cobrança da conta) | — |

## 10. Limites conhecidos e próximos passos

- **Triagem:** trocar a redação de trabalho pela versão brasileira validada da ASRS-18 (OMS), conferir a licença e só então ligar `AGORA_CONFIG.triagem = true`.
- **Sincronização:** em conflito, a pessoa escolhe qual versão vale; a outra fica guardada no aparelho (até 3 cópias) e pode ser restaurada. Ainda não há mesclagem de históricos.
- **Afirmações de mercado:** nenhuma afirmação de exclusividade ("não existe equivalente", "nenhum concorrente") até haver pesquisa que a sustente.
- **Catálogo no app:** o app mostra só a linha "Para você". Empresas e psicólogos têm páginas próprias no site.
- O servidor embutido do Python atende uma clínica; para centenas de usuários simultâneos, trocar por um servidor de produção.
- As datas do resumo de adesão usam o fuso do servidor.
- Ordem de validação externa: GitHub Actions (resolver cobrança) → homologar pagamento com R$ 1 → e-mail real → build Android em aparelho real → push real.
