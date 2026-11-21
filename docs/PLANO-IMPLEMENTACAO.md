# Agora TDAH — Plano de implementação

Versão de 21/10/2026 · versão online com linha do tempo: https://claude.ai/artifact/51GahARXM9rMLzmYtyvXvG

## Resumo

O software da v1.2 está pronto e testado (28 testes de API e 73 de navegador, todos passando). O que falta para lançar é quase tudo fora do código: empresa, contas nos provedores, servidor, textos jurídicos e a aprovação do Google Play. Seguindo este plano, o lançamento público acontece em cerca de **12 semanas**, com um beta fechado na semana 6.

- **Pronto no código:** site, app do paciente (web e Android), painel do psicólogo, pagamentos (Mercado Pago, Stripe e modo de teste), validação de compras do Google Play, recuperação e exclusão de conta, backup e implantação com Docker.
- **Ainda não testado com o real:** cobrança nas contas de produção, envio de e-mail, imagem Docker e o build Android (roda no GitHub Actions).
- **Responsáveis:** Deivison (dono do produto), dev (pode ser o próprio Deivison), contador, advogado e um grupo de psicólogos parceiros para o beta.

## Decisões que guiam o plano

O Plus é vendido só no site no lançamento. O app Android libera o Plus para quem já assinou e não mostra botão de compra. O Play Billing entra na fase 5.

| Decisão | Motivo | Consequência |
| --- | --- | --- |
| Assinatura Plus só no site (Mercado Pago) | Assinatura digital comprada dentro do app tem de usar o Google Play Billing, e o app não pode levar a pessoa a pagar fora ([política de pagamentos](https://support.google.com/googleplay/android-developer/answer/9858738)) | O app Android não tem link nem preço do Plus; o servidor recusa checkout vindo do Android |
| Mercado Pago como provedor principal | Pix, boleto e cartão com assinatura recorrente em reais | Stripe fica como alternativa, já integrada |
| Sessões de terapia cobradas fora do Play | Serviços clínicos regulados não devem usar o Play Billing, e serviços 1:1 ao vivo sem gravação são isentos ([guia da política](https://support.google.com/googleplay/android-developer/answer/10281818)) | A fase 6 (venda de terapia) pode cobrar pelo site e pelo app |
| Conta de desenvolvedor como organização (CNPJ) | Contas pessoais novas precisam de teste fechado com 12 testadores por 14 dias antes de publicar ([requisitos de teste](https://support.google.com/googleplay/android-developer/answer/14151465)) | Exige CNPJ e número D-U-N-S antes da fase 4 |
| Plano anual por pagamento único (Pix) | Pix recorrente ainda não é o caminho mais simples | O anual não renova sozinho; a pessoa compra de novo ao vencer |

## Fases

Seis fases, quatro delas antes do lançamento público na semana 12. Fases 1 e 2 correm juntas; o Android (fase 4) começa assim que existir CNPJ e servidor no ar.

| Fase | Semanas |
| --- | --- |
| 1 · Empresa e jurídico | 1 a 4 |
| 2 · Servidor e pagamentos | 2 a 5 |
| 3 · Beta fechado na web | 6 a 9 |
| 4 · Android no Google Play | 5 a 11 |
| **Lançamento público** | **12** |
| 5 · Plus pelo Google Play | 13 a 21 (meses 4 e 5) |
| 6 · Terapia e sessões | 18 a 34 (meses 5 a 8) |

As fases 1, 2 e 4 se sobrepõem; o único caminho crítico é CNPJ → conta Play → teste fechado → revisão.

### Fase 1 — Empresa e jurídico (semanas 1 a 4)

| Tarefa | Responsável | Prazo | Pronto quando |
| --- | --- | --- | --- |
| Abrir CNPJ (ME no Simples Nacional; MEI não cobre desenvolvimento de software) e conta PJ | Deivison + contador | sem 1–2 | CNPJ ativo e conta bancária PJ |
| Definir CNAE e emissão de NFS-e no município | Contador | sem 2 | Primeira nota de teste emitida |
| Pedir número D-U-N-S (gratuito) | Deivison | sem 2–3 | Número recebido |
| Registrar domínio e e-mails (suporte@, privacidade@) | Deivison | sem 1 | E-mails recebendo |
| Revisar Política de Privacidade e Termos (rascunhos em `site/`) e preencher os colchetes | Advogado | sem 2–4 | Textos finais publicados, aviso de "versão preliminar" removido |
| Nomear encarregado de dados (DPO) e registrar o canal de atendimento | Deivison + advogado | sem 4 | Nome e e-mail na política |
| Pesquisa de marca no INPI para "Agora" | Advogado | sem 2–4 | Parecer de risco por escrito |

### Fase 2 — Servidor e pagamentos reais (semanas 2 a 5)

| Tarefa | Responsável | Prazo | Pronto quando |
| --- | --- | --- | --- |
| Contratar VPS no Brasil, apontar o domínio e subir com `docker compose up -d` | Dev | sem 2 | Site e app abrem com cadeado (HTTPS) |
| Configurar SMTP transacional e testar "esqueci a senha" | Dev | sem 3 | E-mail chega em Gmail e Outlook sem cair no spam |
| Criar aplicação no Mercado Pago, credenciais de teste e segredo do webhook | Deivison + dev | sem 3 | `.env` preenchido com credenciais de teste |
| Homologar no sandbox: assinatura mensal, Pix anual, recusa, estorno, cancelamento | Dev | sem 3–4 | Os cinco casos mudam o Plus corretamente; em especial, confirmar que a assinatura sem plano associado funciona no modo pendente |
| Virar para credenciais de produção e fazer uma compra real de R$ 9,90 com estorno | Deivison | sem 5 | Pagamento aparece no painel, webhook aplicado, estorno remove o Plus |
| Backup diário testado com restauração | Dev | sem 5 | Banco restaurado numa máquina limpa |
| Monitor de disponibilidade e alerta (endpoint `/api/health`) | Dev | sem 5 | Alerta chega quando o servidor cai |

### Fase 3 — Beta fechado na web (semanas 6 a 9)

| Tarefa | Responsável | Prazo | Pronto quando |
| --- | --- | --- | --- |
| Recrutar 5 psicólogos parceiros com Pro de cortesia | Deivison | sem 5–6 | 5 contas Pro ativas |
| Convidar 30 a 50 pacientes pelos parceiros e por comunidades de TDAH | Deivison + psicólogos | sem 6–7 | 30 contas com uso na primeira semana |
| Métricas sem dados sensíveis: cadastros, retenção D1/D7/D30, conversão para Plus | Dev | sem 6 | Painel interno com os números da semana |
| Entrevistas de 20 minutos com 10 usuários | Deivison | sem 8–9 | Lista priorizada de ajustes |
| Corrigir os 10 problemas mais citados | Dev | sem 8–10 | Lista zerada ou adiada com motivo |

### Fase 4 — Android no Google Play (semanas 5 a 11)

| Tarefa | Responsável | Prazo | Pronto quando |
| --- | --- | --- | --- |
| Criar conta de desenvolvedor como organização (CNPJ + D-U-N-S, taxa única de US$ 25) | Deivison | sem 5 | Conta verificada |
| Gerar a chave de assinatura e guardar em cofre; cadastrar secrets no GitHub | Dev | sem 5 | Workflow gera APK e AAB assinados |
| Testar o APK em 3 aparelhos (Android 8, 11 e 14 ou mais novo) | Dev | sem 6 | Lembretes chegam com o app fechado; login libera o Plus |
| Ficha da loja: textos, capturas, ícone, classificação etária | Deivison | sem 6–7 | Ficha completa sem avisos |
| Declaração de apps de saúde e seção de segurança dos dados | Deivison + advogado | sem 7 | Formulários enviados, coerentes com a política de privacidade |
| Teste fechado com os participantes do beta | Deivison | sem 7–9 | Sem falhas graves no relatório de pré-lançamento |
| Enviar para produção e aguardar revisão | Deivison | sem 10–11 | App aprovado |

### Lançamento público (semana 12)

Portão: só lança com a checklist do fim deste plano toda marcada.

### Fase 5 — Plus pelo Google Play (meses 4 e 5)

| Tarefa | Responsável | Prazo | Pronto quando |
| --- | --- | --- | --- |
| Criar o produto de assinatura no Play Console com o mesmo preço do site | Deivison | mês 4 | Produto ativo |
| Integrar um plugin de Play Billing no app (Capacitor) e mandar o token para `/api/pagamentos/google-play` | Dev | mês 4 | Compra de teste libera o Plus; o servidor já valida e confirma |
| Configurar notificações em tempo real (Pub/Sub) apontando para o webhook | Dev | mês 4 | Renovação e cancelamento de teste chegam ao servidor |
| Liberar a compra no Android | Dev | mês 5 | Primeira assinatura real pelo Play |

### Fase 6 — Terapia e receita de sessões (meses 5 a 8)

| Tarefa | Responsável | Prazo | Pronto quando |
| --- | --- | --- | --- |
| Validar com advogado o modelo (indicação, agenda ou marketplace) e as normas do CFP para atendimento online | Advogado + Deivison | mês 5 | Parecer e contrato com psicólogos |
| Agenda e pagamento de sessão com divisão automática (split) entre plataforma e psicólogo | Dev | mês 6–7 | Sessão paga e repasse conferido |
| Notificações push na web (com o app fechado) | Dev | mês 6 | Lembrete chega no navegador fechado |
| Avaliar a versão iOS | Deivison | mês 8 | Decisão tomada com os números do Android |

## Custos estimados

Para lançar, a estimativa é de **R$ 2.000 a R$ 7.200 de uma vez** e **R$ 300 a R$ 700 por mês**, sem contar o tempo do dev. Só a taxa do Google Play é valor oficial. Os outros são faixas de mercado aproximadas, para confirmar em orçamento.

| Item | Tipo | Valor estimado | Observação |
| --- | --- | --- | --- |
| Advogado: privacidade, termos, contrato com psicólogos | Único | R$ 1.500 a R$ 5.000 | Pedir orçamento fechado com escopo LGPD + saúde |
| Abertura de empresa | Único | R$ 0 a R$ 1.000 | Muitos contadores incluem na mensalidade |
| Pesquisa e registro de marca no INPI | Único | R$ 400 a R$ 1.000 | Taxas do INPI + honorários, se houver |
| Conta de desenvolvedor Google Play | Único | US$ 25 | Valor oficial |
| Contador | Mensal | R$ 250 a R$ 500 | Inclui NFS-e e Simples Nacional |
| Servidor VPS (2 vCPU, 2–4 GB) | Mensal | R$ 50 a R$ 150 | Aguenta milhares de usuários com SQLite |
| E-mail transacional | Mensal | R$ 0 a R$ 50 | Plano gratuito costuma bastar no início |
| Domínio .com.br | Anual | cerca de R$ 40 | Registro.br |
| Mercado Pago | Por venda | percentual por transação | Conferir a tabela atual no painel; Pix costuma ser o meio mais barato |

Ponto de equilíbrio dos custos mensais: cerca de **50 assinantes Plus mensais** (R$ 9,90) ou **8 psicólogos Pro** (R$ 69,00), antes de taxas e impostos.

## Riscos

O maior risco é de calendário: a revisão do Google Play e a homologação do Mercado Pago não dependem de nós. O plano já deixa 2 semanas de folga entre a aprovação do app e o lançamento.

| Risco | Chance | Impacto | Como reduzir |
| --- | --- | --- | --- |
| Google Play recusa ou pede ajustes (app de saúde, dados sensíveis) | Média | Atrasa o Android 1 a 3 semanas | Declaração de saúde e segurança dos dados revisadas pelo advogado; ficha diz claramente que o app não faz diagnóstico; site lança mesmo sem o Android |
| Play entende que o login que libera o Plus é desvio de pagamento | Baixa | App removido até corrigir | Nenhum preço, link ou menção à compra no app (já é assim); antecipar a fase 5 se houver aviso |
| Assinatura do Mercado Pago sem plano associado não funcionar no modo pendente | Média | Retrabalho de 2 a 3 dias | Testar na semana 3; alternativa pronta: criar um plano de assinatura no Mercado Pago e assinar por ele |
| Vazamento de dados de saúde | Baixa | Alto: dever de comunicar à ANPD e aos titulares | Senhas com PBKDF2, tokens só como hash, HTTPS, backup cifrado fora do servidor, acesso ao servidor só por chave SSH; plano de resposta escrito antes do lançamento |
| Perda da chave de assinatura Android | Baixa | Não dá mais para atualizar o app | Ativar a assinatura de apps pelo Google Play; guardar a chave de upload em cofre com cópia |
| Pouca conversão para o Plus | Média | Receita abaixo dos custos | Medir desde o beta; testar o anual em destaque; o negócio principal é a terapia (fase 6) |
| Conflito de marca "Agora" | Média | Troca de nome depois do lançamento | Pesquisa no INPI na fase 1, antes da ficha da Play (o identificador do app não muda depois) |
| Paciente em crise usando o app | Baixa | Alto | CVV 188 e SAMU 192 visíveis no app e no site (já estão); o psicólogo vinculado recebe pedido de contato |

## Checklist do lançamento

Só lança com tudo marcado.

**Empresa e jurídico**

- [ ] CNPJ ativo, conta PJ e NFS-e emitindo
- [ ] Política de Privacidade e Termos finais publicados, sem colchetes nem aviso de versão preliminar
- [ ] Encarregado de dados (DPO) nomeado, com e-mail de contato na política
- [ ] Contrato ou termo de uso aceito pelos psicólogos do painel

**Servidor**

- [ ] `AGORA_AMBIENTE=producao` no `.env` (desliga o checkout simulado)
- [ ] HTTPS válido em site, app e painel
- [ ] E-mail de "esqueci a senha" chegando na caixa de entrada
- [ ] Backup diário rodando e uma restauração testada
- [ ] Alerta de servidor fora do ar configurado
- [ ] Dados de demonstração fora do banco de produção

**Pagamentos**

- [ ] Credenciais de produção do Mercado Pago e segredo do webhook no `.env`
- [ ] Compra real de R$ 9,90 feita, Plus liberado e estorno conferido
- [ ] Cancelamento mantém o acesso até o fim do período
- [ ] Preços iguais no site, no checkout e nos termos

**Android**

- [ ] App aprovado no Google Play
- [ ] Nenhum preço, link ou botão de compra do Plus dentro do app
- [ ] URLs de privacidade e de exclusão de conta na ficha da loja
- [ ] Lembretes testados com o app fechado em 3 aparelhos

**Atendimento**

- [ ] E-mail de suporte respondido em até 1 dia útil
- [ ] Roteiro de resposta a incidente de dados escrito
- [ ] CVV 188 e SAMU 192 visíveis no app e no site

## Fontes

- [Google Play: política de pagamentos](https://support.google.com/googleplay/android-developer/answer/9858738)
- [Google Play: guia da política de pagamentos (serviços 1:1 e clínicos)](https://support.google.com/googleplay/android-developer/answer/10281818?hl=en)
- [Google Play: requisitos de teste para contas pessoais novas](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en)
- [Mercado Pago: assinaturas sem plano associado com pagamento pendente](https://www.mercadopago.com.br/developers/pt/docs/subscriptions/integration-configuration/subscription-no-associated-plan/pending-payments)
- [Mercado Pago: notificações de pagamento e validação da assinatura](https://mercadopago.com.br/developers/es/docs/checkout-pro/payment-notifications)
- [Contabilidade Zen: fim do cadastro e-Psi (Resolução CFP 09/2024)](https://www.contabilidadezen.com.br/blog/fim-cadastro-epsi-o-que-muda-2026/)
