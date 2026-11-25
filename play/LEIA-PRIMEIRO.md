# Publicar o Agora na Google Play

Esta pasta tem tudo o que o Play Console pede: textos da ficha, imagens e as respostas dos formulários.
Siga na ordem. Cada passo diz onde clicar e o que colar.

| Arquivo | Para quê |
|---|---|
| `textos/titulo.txt` · `descricao-curta.txt` · `descricao-completa.txt` | Ficha da loja (28/30, 80/80 e ~2.500/4.000 caracteres) |
| `imagens/icone-512.png` | Ícone da ficha (512 × 512) |
| `imagens/destaque-1024x500.jpg` | Gráfico de destaque |
| `imagens/celular-01..06.jpg` | Capturas do celular (1080 × 1920) |
| `FORMULARIOS.md` | Respostas de segurança dos dados, saúde, classificação, público-alvo |

Para refazer as imagens depois de mudar o app: `python3 ferramentas/gerar_kit_play.py`.

## Que app vai para a loja

A primeira versão na Play é o **app local**: sem conta, sem servidor, tudo no celular.
É o build que o GitHub Actions gera quando o secret `AGORA_API_URL` **não** existe. Nesse modo:

- não aparecem conta, planos nem vínculo com o psicólogo (não há o que vender dentro do app);
- os sons extras e o relatório do mês vêm liberados;
- a página Serviços mostra só terapia individual, orientação de carreira e a aula aberta, com o pedido por e-mail;
- lembretes usam alarme aproximado (o app não pede a permissão "Alarmes e lembretes");
- o formulário de segurança dos dados fica simples: **o app não coleta dados**.

Quando o servidor estiver no ar e você quiser contas e vínculo no Android, cadastre `AGORA_API_URL` e refaça a seção de segurança dos dados (o fim de `FORMULARIOS.md` traz o que muda).

## Passo 1. Conta de desenvolvedor (uma vez)

1. Abra https://play.google.com/console/signup e escolha o tipo de conta.
   - **Pessoal:** pede documento e verificação de identidade. Contas pessoais criadas depois de 13/11/2023 precisam de um **teste fechado com pelo menos 12 testadores, inscritos sem parar por 14 dias**, antes de liberar a produção.
   - **Organização:** pede CNPJ e número D-U-N-S (gratuito, sai em alguns dias úteis). A regra dos 12 testadores é das contas pessoais.
2. Pague a taxa de registro (única) e conclua a verificação.

## Passo 2. Chave de assinatura (uma vez, no seu computador)

1. Com o Java instalado, rode `android/gerar-chave.sh`. Ele cria `android/chave-assinatura.jks`.
2. **Guarde o arquivo e a senha em dois lugares** (cofre de senhas e um pendrive). Sem eles você não atualiza o app.
3. No GitHub: *Settings › Secrets and variables › Actions › New repository secret*:
   - `AGORA_KEYSTORE_BASE64` = saída de `base64 -w0 android/chave-assinatura.jks` (no Mac: `base64 -i android/chave-assinatura.jks`)
   - `AGORA_KEYSTORE_SENHA` = a senha
4. Na aba *Variables* (mesma tela), crie `AGORA_PRIVACIDADE_URL` com o endereço público da política de privacidade (passo 3).
   Sem essa variável, o app aponta para `https://ridd1kulusc0d3r.github.io/tdah/privacidade.html`.
5. *Actions › Android › Run workflow*. Ao terminar, baixe o artefato **agora-release.aab**.

A chave **não** vai para o repositório: o `.gitignore` já ignora `*.jks`.

## Passo 3. Política de privacidade no ar

A Play exige um link público. A política do app local está em `prototipo/privacidade.html` (inclui a seção "No app para Android").
Publique o protótipo de um dos jeitos de `prototipo/PUBLICAR.md` (GitHub Pages ou Netlify Drop) e confira que o endereço abre no celular.

## Passo 4. Criar o app no Play Console

*Todos os apps › Criar app*:

| Campo | Resposta |
|---|---|
| Nome do app | conteúdo de `textos/titulo.txt` |
| Idioma padrão | Português (Brasil) – pt-BR |
| App ou jogo | App |
| Gratuito ou pago | Gratuito |
| Declarações | marcar as duas (políticas e leis de exportação dos EUA) |

## Passo 5. Configurar o app

No painel, a seção *Configurar o app* lista os formulários. Copie as respostas de `FORMULARIOS.md`.

## Passo 6. Ficha principal da loja

*Expandir › Ficha principal da loja*: cole os três textos e envie as imagens (ícone, destaque e as 6 capturas em *Telefone*).
Categoria e contato também estão em `FORMULARIOS.md`.

## Passo 7. Teste e lançamento

1. **Teste interno** (opcional, sai em minutos): *Testar e lançar › Teste interno › Criar versão*, envie o `.aab`, adicione o seu e-mail na lista de testadores e instale pelo link.
2. **Teste fechado** (obrigatório para conta pessoal): *Teste fechado › Criar faixa*, envie o mesmo `.aab`, cadastre os e-mails dos **12 ou mais testadores** (lista de e-mails ou Grupo do Google) e mande para eles o link de inscrição. Conte 14 dias a partir do dia em que o 12º aceitou.
   Boas fontes de testadores: colegas de profissão, pacientes adultos que aceitarem (sem obrigação), turma da Lume.
3. Depois dos 14 dias: *Painel › Solicitar acesso à produção*. O Google pergunta como foi o teste; responda com o que mudou a partir dos comentários.
4. **Produção:** crie a versão, escolha *Brasil* em países e envie para revisão (costuma levar de alguns dias a uma semana).

## Antes de enviar cada versão

- [ ] `python3 -m unittest tests.test_publicacao` passou (inclui o modo Android sem servidor).
- [ ] O e-mail de contato (`AGORA_CONTATO_PUBLICO`) é um endereço que alguém lê.
- [ ] A política de privacidade abre no endereço cadastrado.
- [ ] `versionName` em `android/android/app/build.gradle` mudou (o `versionCode` sobe sozinho pelo número da execução do Actions).

## Requisitos da Google Play que este projeto já cumpre

- **API alvo 36** (`android/android/variables.gradle`), exigida para envios a partir de 31/08/2026.
- **Formato AAB** assinado, com a assinatura de apps do Google Play (aceite quando o Console oferecer).
- **Aviso de saúde na descrição:** "não é um dispositivo médico e não diagnostica, trata, cura nem previne", com orientação para procurar um profissional.
- **Sem exclusão de conta a declarar:** o app local não cria contas.

Fontes: [teste para contas pessoais novas](https://support.google.com/googleplay/android-developer/answer/14151465),
[declaração de apps de saúde](https://support.google.com/googleplay/android-developer/answer/14738291),
[política de apps de saúde](https://support.google.com/googleplay/android-developer/answer/13996823),
[API alvo](https://developer.android.com/google/play/requirements/target-sdk).
