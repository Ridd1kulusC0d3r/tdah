# Relatório de testes — Agora 2.1

Executado em 2026-11-21 17:10:24 num ambiente Linux na nuvem.

| Suíte | Resultado |
|---|---|
| API e produção (`tests/test_api.py` e `tests/test_producao.py`, unittest) | **58/58** |
| Mesmos testes sem o pacote opcional `cryptography` (cifra em Python puro) | **58 testes ok (2 pulados: comparam com a própria cryptography)** |
| Ponta a ponta no navegador (`tests/test_ui.py`, Playwright + Chromium) | **121/121** |

## Ambiente

- Python 3.13.18 em Linux 6.18.44-fc-v726
- Playwright ?, Chromium headless
- Telas: 1280×860 e 1360×900 (computador), 390×844 (celular); temas claro, escuro, Matrix e Clean
- Modo Android simulado: AGORA_CONFIG de Android e plugin de notificações falso para conferir os lembretes agendados
- Não testado aqui: entrega real de Web Push pelos serviços do Google/Mozilla/Apple, envio real ao S3, build nativo do Android (o ambiente não tem o Android SDK; o build roda no GitHub Actions), pagamentos reais nos provedores e envio real de e-mail
- Fuso America/Sao_Paulo, locale pt-BR, relógio fixado em 10:05 para resultado determinístico
- Banco SQLite temporário com o caso de demonstração (`server/seed_demo.py`)

## O que a API cobre

Registro e validação, login e logout, limite de tentativas, recuperação de senha, exclusão e exportação de conta, senha em PBKDF2 e token só como hash, papéis, convite de uso único, filtro de consentimento aplicado no servidor (tarefas não liberadas nunca chegam ao profissional), revogação de consentimento, prescrição com limites, arquivamento, isolamento entre profissionais, pedido de contato, desvínculo apagando o snapshot, limite do plano grátis do profissional, checkout simulado (aprovado, recusado, Pix, idempotência, cancelamento e expiração), simulado desligado em produção, bloqueio de venda pelo Android, Mercado Pago (assinatura, renovação, Pix, estorno, assinatura HMAC igual ao SDK oficial), Stripe (assinatura, falha, cancelamento, Pix assíncrono, janela de tempo), Google Play (JWT RS256 conferido com o OpenSSL, compra, acknowledge, conta errada, RTDN), CORS do app Android, rotas do site, cabeçalhos de segurança, path traversal e JSON inválido. Na 2.0: ChaCha20-Poly1305 e Poly1305 contra os vetores da RFC 8439 e contra a biblioteca cryptography, TOTP contra a RFC 6238, ECDSA P-256 conferido pela cryptography, assinatura SigV4 contra os exemplos da AWS, migração de banco 1.3 com cifragem na partida, verificação em duas etapas com códigos de recuperação de uso único, limite de tentativas que sobrevive a reinício, CSP com hash de cada script, conflito de versão na nuvem, erro interno registrado sem vazar, catálogo por contexto (web, Android, paciente vinculado), formulário de interesse com armadilha para robôs, sequência de e-mails com descadastro assinado, eventos anônimos, turma com pagamento, missões, lista de espera e estorno, e-book com link assinado que expira, compra avulsa pelo Stripe, trava de publicidade no catálogo, lembrete Web Push com JWT VAPID, retenção, exportação e exclusão, backup cifrado com envio S3 e restauração, CLI de administração, recusa de partida em produção sem chave e sem o pacote cryptography. Na 2.1, no navegador: fim do foco com Concluí/Avancei/Retomar e o passo guardado em Onde você parou, dias em que voltei, triagem desligada até o texto validado, preparo da sessão (prévia, período, categorias, download e envio ao profissional vinculado), importação de cursos com prévia, atualização sem duplicar e expirados desmarcados, catálogo do app só com a linha Para você. No navegador, o teste confere também que nenhuma página pede arquivos a servidores de fora (as fontes ficam no próprio app).

| Teste da API | Resultado |
|---|---|
| `test_01_health_e_planos` | ✓ |
| `test_02_validacao_registro` | ✓ |
| `test_03_login_e_logout` | ✓ |
| `test_04_limite_de_tentativas` | ✓ |
| `test_05_senha_e_token_nao_ficam_em_claro` | ✓ |
| `test_06_recuperacao_de_senha` | ✓ |
| `test_07_papeis` | ✓ |
| `test_08_fluxo_clinico_completo` | ✓ |
| `test_09_limite_do_plano_gratis_do_profissional` | ✓ |
| `test_10_exclusao_de_conta` | ✓ |
| `test_11_estaticos_rotas_e_seguranca` | ✓ |
| `test_12_cors_para_o_app_android` | ✓ |
| `test_01_jwt_rs256_valido` | ✓ |
| `test_02_compra_no_app_e_rtdn` | ✓ |
| `test_01_assinatura_mensal_ponta_a_ponta` | ✓ |
| `test_02_pix_anual_e_estorno` | ✓ |
| `test_03_manifesto_igual_ao_sdk_oficial` | ✓ |
| `test_01_plus_mensal_libera_recursos` | ✓ |
| `test_02_recusado_nao_libera` | ✓ |
| `test_03_anual_soma_365_dias_e_acumula` | ✓ |
| `test_04_confirmar_duas_vezes_e_idempotente` | ✓ |
| `test_05_cancelar_mantem_ate_o_fim_e_expira` | ✓ |
| `test_06_plano_errado_para_o_papel_e_android` | ✓ |
| `test_07_pro_libera_pacientes_ilimitados` | ✓ |
| `test_seed_idempotente` | ✓ |
| `test_simulado_desligado_em_producao` | ✓ |
| `test_01_assinatura_renovacao_e_cancelamento` | ✓ |
| `test_02_pagamento_unico` | ✓ |
| `test_01_chacha20_poly1305_rfc8439` | ✓ |
| `test_02_poly1305_rfc8439` | ✓ |
| `test_03_igual_a_biblioteca_cryptography` | ✓ |
| `test_04_totp_rfc6238` | ✓ |
| `test_05_es256_conferido_pela_cryptography` | ✓ |
| `test_06_cofre_rotacao_e_arquivo` | ✓ |
| `test_07_sigv4_chave_de_assinatura_aws` | ✓ |
| `test_08_sigv4_exemplo_get_object_aws` | ✓ |
| `test_01_catalogo_por_contexto` | ✓ |
| `test_02_interesse_cifrado_sequencia_e_descadastro` | ✓ |
| `test_03_eventos_anonimos` | ✓ |
| `test_04_turma_pagamento_missoes_espera_e_estorno` | ✓ |
| `test_05_ebook_compra_e_download_assinado` | ✓ |
| `test_06_sessao_no_android_e_vinculado_bloqueado` | ✓ |
| `test_07_avulso_pelo_stripe` | ✓ |
| `test_08_admin_catalogo_veta_publicidade_irregular` | ✓ |
| `test_09_push_lembrete_vapid` | ✓ |
| `test_10_retencao_e_exclusao` | ✓ |
| `test_banco_da_versao_1_3_e_cifrado_na_partida` | ✓ |
| `test_admin_cli` | ✓ |
| `test_backup_cifrado_restaura_e_envia_para_s3` | ✓ |
| `test_producao_exige_cryptography` | ✓ |
| `test_producao_recusa_sem_chave` | ✓ |
| `test_01_health_completo` | ✓ |
| `test_02_dois_fatores_ponta_a_ponta` | ✓ |
| `test_03_limite_persiste_entre_reinicios` | ✓ |
| `test_04_cabecalhos_csp_e_estaticos` | ✓ |
| `test_05_nuvem_cifrada_e_conflito` | ✓ |
| `test_06_snapshot_e_pedido_cifrados_e_link_de_convite` | ✓ |
| `test_07_erro_interno_registrado_sem_vazar` | ✓ |

## Verificações no navegador

| # | Verificação | Resultado |
|---|---|---|
| 1 | abre com banner de dados de exemplo | ✓ |
| 2 | cartão Agora mostra uma próxima ação | ✓ |
| 3 | painel desenha os gráficos (foco×humor, sono, atividade, dia da semana) | ✓ |
| 4 | calendário do humor com carinhas | ✓ |
| 5 | período de 28 dias muda o gráfico | ✓ |
| 6 | painel mostra comparações | ✓ |
| 7 | tarefas agrupadas por prioridade | ✓ |
| 8 | tarefas mostram o tipo | ✓ |
| 9 | filtro por tipo | ✓ |
| 10 | lista de cursos com progresso | ✓ |
| 11 | +1 aula atualiza o progresso | ✓ |
| 12 | tema Matrix aplica fundo preto-esverdeado | ✓ |
| 13 | dados de exemplo somem | ✓ |
| 14 | primeira tarefa vira a próxima ação | ✓ |
| 15 | quebrar em passos cria 3 passos | ✓ |
| 16 | marcar passo avança o destaque | ✓ |
| 17 | duração muda o botão | ✓ |
| 18 | modo foco abre com relógio 15:00 | ✓ |
| 19 | sala de foco aparece (modo solo sem conta) | ✓ |
| 20 | fim do foco separa o tempo da tarefa (Concluí / Avancei / Retomar) | ✓ |
| 21 | sessão registrada (15 min no placar) | ✓ |
| 22 | onde parei aparece na próxima ação, com o passo guardado | ✓ |
| 23 | placar mostra dias em que voltei, sem exigir sequência | ✓ |
| 24 | agora não troca a tarefa | ✓ |
| 25 | fazer esta agora fixa a escolhida | ✓ |
| 26 | ideia rápida vira tarefa | ✓ |
| 27 | despejo cria várias tarefas | ✓ |
| 28 | humor com carinhas no diário | ✓ |
| 29 | diário salvo com sono 7,5 h e 30 min de caminhada | ✓ |
| 30 | humor 1 abre apoio com CVV 188 | ✓ |
| 31 | player mostra passo 1 de 2 | ✓ |
| 32 | rotina concluída marca 'feita hoje' | ✓ |
| 33 | triagem fica fora do app até o texto brasileiro validado | ✓ |
| 34 | ASRS (ligada por configuração): 4 na faixa de atenção → sugere avaliação | ✓ |
| 35 | seção de lembretes com rotina e diário | ✓ |
| 36 | preparo: a prévia mostra as respostas na hora | ✓ |
| 37 | preparo: período e categorias mudam o resumo | ✓ |
| 38 | preparo: tirar uma categoria tira do resumo | ✓ |
| 39 | preparo: baixa como texto | ✓ |
| 40 | importar cursos: lê a tabela e avisa o que já existe | ✓ |
| 41 | importar cursos: expirado vem desmarcado | ✓ |
| 42 | importar cursos: 2 novos, nenhum duplicado | ✓ |
| 43 | importar cursos: prazo lido da tabela | ✓ |
| 44 | paciente vinculada à Dra. Ana | ✓ |
| 45 | painel lista 4 pacientes | ✓ |
| 46 | quem pediu contato vem primeiro | ✓ |
| 47 | aviso de pedido de contato aparece | ✓ |
| 48 | profissional de demonstração tem o Agora Pro | ✓ |
| 49 | resumo para a sessão é gerado | ✓ |
| 50 | prescrição aparece como ativa no painel | ✓ |
| 51 | rotina prescrita chega ao app da paciente | ✓ |
| 52 | profissional recebe os minutos de foco da paciente | ✓ |
| 53 | plano grátis aparece na conta | ✓ |
| 54 | checkout mostra plano e valor | ✓ |
| 55 | Plus ativo depois do pagamento | ✓ |
| 56 | URL limpa depois do retorno | ✓ |
| 57 | cópia na nuvem salva | ✓ |
| 58 | cancelar mantém o Plus até o fim | ✓ |
| 59 | relatório do mês abre para quem tem Plus | ✓ |
| 60 | sala de foco mostra pessoas (paciente vinculada/Plus) | ✓ |
| 61 | plano grátis mostra 0 de 3 pacientes | ✓ |
| 62 | Pro ativo depois do pagamento | ✓ |
| 63 | pedido de nova senha responde sem revelar a conta | ✓ |
| 64 | senha nova funciona | ✓ |
| 65 | app mostra só a linha Para você (9 itens), com marca | ✓ |
| 66 | empresas e psicólogos ficam fora do app | ✓ |
| 67 | serviço psicológico mostra nome e CRP do responsável | ✓ |
| 68 | nenhum texto de desconto ou promessa | ✓ |
| 69 | minhas turmas mostra a turma confirmada com 8 missões | ✓ |
| 70 | link da sala só aparece para quem está confirmado | ✓ |
| 71 | marcar missão como feita | ✓ |
| 72 | turmas abertas com vagas e preço | ✓ |
| 73 | e-book comprado baixa em PDF | ✓ |
| 74 | interesse sem aceite é recusado | ✓ |
| 75 | interesse enviado e confirmado na tela | ✓ |
| 76 | checkout da turma mostra o programa e o valor | ✓ |
| 77 | depois do Pix a vaga aparece em Minhas turmas | ✓ |
| 78 | vinculado vê aviso e nenhum serviço psicológico | ✓ |
| 79 | humor baixo mostra acolhimento, sem oferta de serviço | ✓ |
| 80 | tela de ajuda traz CVV 188 e caminho pelo SUS | ✓ |
| 81 | vinculado envia o preparo ao profissional | ✓ |
| 82 | profissional vê 'enviou preparo' na lista | ✓ |
| 83 | preparo aparece na ficha com o texto | ✓ |
| 84 | site lista serviços com CRP do responsável | ✓ |
| 85 | pedido de proposta enviado pelo site | ✓ |
| 86 | página Começar com 3 caminhos e o 188 | ✓ |
| 87 | convite traz link que já preenche o código | ✓ |
| 88 | abrir o link do convite leva ao vínculo | ✓ |
| 89 | verificação em duas etapas ligada com 8 códigos de recuperação | ✓ |
| 90 | sem o código, a administração não abre | ✓ |
| 91 | resumo com receita, meta e funil | ✓ |
| 92 | contatos com mensagem decifrada | ✓ |
| 93 | inscritos com progresso das missões | ✓ |
| 94 | catálogo recusa publicidade irregular de serviço psicológico | ✓ |
| 95 | compras listadas com opção de estorno | ✓ |
| 96 | sem rolagem lateral no celular: agora | ✓ |
| 97 | sem rolagem lateral no celular: tarefas | ✓ |
| 98 | sem rolagem lateral no celular: rotinas | ✓ |
| 99 | sem rolagem lateral no celular: diario | ✓ |
| 100 | sem rolagem lateral no celular: painel | ✓ |
| 101 | sem rolagem lateral no celular: mais | ✓ |
| 102 | sem rolagem lateral no celular: serviços | ✓ |
| 103 | sem rolagem lateral no celular: /servicos | ✓ |
| 104 | sem rolagem lateral no celular: /comecar | ✓ |
| 105 | sem rolagem lateral no celular: /app/admin.html | ✓ |
| 106 | tema escuro aplica fundo escuro | ✓ |
| 107 | sem servidor, vínculo explica como fazer | ✓ |
| 108 | lembretes nativos agendados (3 rotinas + diário) | ✓ |
| 109 | Android não mostra botão de compra do Plus | ✓ |
| 110 | Android não tem link para pagamento externo | ✓ |
| 111 | Android: lembretes chegam com o app fechado | ✓ |
| 112 | página inicial com a promessa | ✓ |
| 113 | preços vindos da API | ✓ |
| 114 | botão principal abre o app | ✓ |
| 115 | página /privacidade.html abre | ✓ |
| 116 | página /termos.html abre | ✓ |
| 117 | página /excluir-conta.html abre | ✓ |
| 118 | exclusão de conta pela web funciona | ✓ |
| 119 | site sem rolagem lateral no celular | ✓ |
| 120 | nenhum erro de JavaScript em todo o percurso | ✓ |
| 121 | nenhum pedido a servidores externos (fontes hospedadas no próprio app) | ✓ |

## Como repetir

```bash
./rodar-testes.sh
# ou separadamente:
python3 -m unittest tests.test_api tests.test_producao -v
python3 tests/test_ui.py   # requer: pip install playwright && playwright install chromium
```

As capturas de tela do manual (`docs/capturas/`) são geradas pelo teste de navegador.
