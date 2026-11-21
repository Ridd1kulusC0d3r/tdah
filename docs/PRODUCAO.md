# Agora 2.0 — roteiro de produção

O passo a passo para colocar no ar, operar no dia a dia e agir quando algo dá errado. Faça um item por vez e marque.

## 1. Antes do primeiro deploy (uma vez)

| # | Tarefa | Comando ou onde | Feito |
|---|---|---|---|
| 1 | Criar o repositório privado no GitHub e subir a pasta | `git init && git add . && git commit -m "Agora 2.0"` e `git push` | ☐ |
| 2 | Contratar servidor (2 vCPU, 2 GB, Ubuntu 24.04, de preferência no Brasil) | Hostinger VPS, Magalu Cloud, Locaweb, AWS São Paulo | ☐ |
| 3 | Apontar o DNS: `agora.seudominio` e `homologacao.seudominio` para o IP | Painel do registro.br ou do provedor de DNS | ☐ |
| 4 | Instalar Docker no servidor | `curl -fsSL https://get.docker.com \| sh` | ☐ |
| 5 | Copiar `.env.example` para `.env` e preencher | ver seção 2 | ☐ |
| 6 | Gerar a chave de criptografia e **guardar uma cópia fora do servidor** | `docker compose run --rm agora python3 server/admin.py chave` | ☐ |
| 7 | Gerar as chaves de notificação | `docker compose run --rm agora python3 server/admin.py vapid` | ☐ |
| 8 | Conferir se falta algo | `docker compose run --rm agora python3 server/admin.py conferir` | ☐ |
| 9 | Subir | `docker compose up -d` e abrir `https://agora.seudominio/api/health` | ☐ |
| 10 | Criar sua conta de profissional no painel e virar administrador | `docker compose exec agora python3 server/admin.py promover SEU@EMAIL` | ☐ |
| 11 | Entrar em `/app/admin.html`, ligar a verificação em duas etapas e guardar os 8 códigos | navegador | ☐ |
| 12 | Configurar webhooks do Mercado Pago (ou Stripe) apontando para `/api/webhooks/...` | painel do provedor | ☐ |
| 13 | Fazer uma compra real de R$ 1 (ajuste o preço no Catálogo), conferir em Compras e estornar | `/app/admin.html` | ☐ |
| 14 | Restaurar um backup num arquivo novo e conferir | seção 5 | ☐ |
| 15 | Colocar os PDFs finais dos e-books em `/dados/ebooks/<id>.pdf` | `docker compose cp arquivo.pdf agora:/dados/ebooks/` | ☐ |
| 16 | Revisão de advogado: privacidade, termos, contrato com profissionais | `site/privacidade.html`, `site/termos.html` | ☐ |
| 17 | Revisão da publicidade com a orientação do CRP-04 | Catálogo e `/servicos` | ☐ |

## 2. Variáveis obrigatórias

O servidor **se recusa a ligar** em produção (`AGORA_AMBIENTE=producao`) sem estas:

- `AGORA_CHAVE`: chave de 32 bytes. Cifra diário, cópia na nuvem, mensagens, segredos de 2FA e backups.
- `AGORA_URL_PUBLICA` com `https://`.
- `AGORA_PAGAMENTO=mercadopago` (ou `stripe`) com as credenciais e o segredo do webhook.
- `AGORA_SMTP_*`: e-mail de senha, confirmações e avisos de turma.

Recomendadas: `AGORA_S3_*` (backup fora do servidor), `AGORA_VAPID_*` (lembretes com o app fechado), `AGORA_ALERTA_EMAIL` (aviso de erro interno).

## 3. Rotina de operação

| Quando | O quê | Onde |
|---|---|---|
| Todo dia, 5 min | Contatos novos: responder e mudar a situação | Administração › Contatos |
| Todo dia | Compras de sessão: escrever para marcar horário | Administração › Compras |
| Toda semana | Receita contra a meta, funil, erros | Administração › Resumo |
| Toda semana | Turmas: inscritos, missões, lista de espera, aviso aos confirmados | Administração › Turmas |
| Todo mês | Conferir que existe backup recente no S3 e restaurar um de teste | seção 5 |
| Todo mês | Atualizar o sistema do servidor e a imagem | `apt upgrade` · `docker compose build --pull && docker compose up -d` |
| A cada 12 meses | Trocar a `AGORA_CHAVE` | seção 6 |

Tarefas automáticas (já ligadas pelo `AGORA_AGENDADOR=1`): lembretes push a cada minuto, e-mails de conteúdo (dias 1, 4 e 10 de quem aceitou) e limpeza por prazo de retenção a cada hora. Para rodar à mão: `python3 server/admin.py tarefas`.

## 4. Atualizar para uma versão nova

```
git pull
docker compose build
docker compose up -d
docker compose logs -f agora     # procure "migração N" e nenhum erro
```

As migrações do banco rodam sozinhas na partida (`PRAGMA user_version`). Antes de atualizar, rode um backup manual: `docker compose run --rm backup python3 server/backup.py --db /dados/agora.db --destino /backups`.

## 5. Backup e restauração

- **Automático:** todo dia às 00:30 (Brasília). O arquivo sai **cifrado** (`.db.cifrado`), é conferido com `integrity_check` e enviado ao S3. Ficam 30 cópias locais em `./backups`.
- **Restaurar** (sempre para um arquivo novo, com o servidor desligado na hora da troca):

```
docker compose run --rm agora python3 server/backup.py --restaurar s3:agora-AAAAMMDD-HHMMSS.db.cifrado --db /dados/restaurado.db
docker compose stop agora
docker compose run --rm agora sh -c "mv /dados/agora.db /dados/agora-antes.db && mv /dados/restaurado.db /dados/agora.db"
docker compose start agora
```

Sem a `AGORA_CHAVE` que estava em uso no dia do backup, ele não abre. Guarde as chaves antigas junto com a data de troca.

## 6. Trocar a chave de criptografia

1. Gere uma nova: `python3 server/admin.py chave`.
2. No `.env`: mova a atual para `AGORA_CHAVES_ANTIGAS` e coloque a nova em `AGORA_CHAVE`.
3. `docker compose up -d` e depois `docker compose exec agora python3 server/admin.py recifrar`.
4. Mantenha a antiga em `AGORA_CHAVES_ANTIGAS` enquanto existir backup feito com ela (30 dias locais; o prazo do S3 que você configurou).

## 7. Acessos e contas

- Celular perdido de um administrador: `python3 server/admin.py zerar-2fa EMAIL` (encerra as sessões; a pessoa liga de novo).
- Tirar acesso: `python3 server/admin.py rebaixar EMAIL`.
- Ver estado do banco: `python3 server/admin.py estado`.

## 8. Quando algo dá errado

| Sintoma | O que fazer |
|---|---|
| Site fora do ar | `docker compose ps` · `docker compose logs --tail 200 agora` · `curl localhost:8765/api/health` dentro do contêiner |
| "AGORA_CHAVE não configurada" na partida | O `.env` não foi lido ou a variável está vazia |
| "Chave de criptografia desconhecida" | A chave mudou sem a antiga em `AGORA_CHAVES_ANTIGAS` |
| Pagamento aprovado mas acesso não liberou | Administração › Erros; painel do provedor › webhooks (status e reenvio). O processamento é idempotente: reenviar não duplica |
| Lembrete push não chega | `GET /api/health` mostra `push: true`? O navegador permitiu? Safari só aceita push em app instalado na tela inicial |
| Muitos 429 nos logs | Tentativa de força bruta: o limite já bloqueia. Se for um IP só, bloqueie no firewall |
| Suspeita de vazamento | `docs/INCIDENTES.md`, agora |

Logs: em produção cada acesso sai como uma linha JSON (sem query string, sem corpo). Erros internos vão para a tabela `erros` e, se configurado, para o `AGORA_ALERTA_EMAIL`.
