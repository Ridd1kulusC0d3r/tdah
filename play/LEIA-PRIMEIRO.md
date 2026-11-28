# Publicar o Agora na Google Play

Esta pasta tem tudo o que o Play Console pede: textos da ficha, imagens e as respostas dos formulários.
Siga na ordem. Cada passo diz onde clicar e o que colar.

| Arquivo | Para quê |
|---|---|
| `textos/titulo.txt` · `descricao-curta.txt` · `descricao-completa.txt` | Ficha da loja (28/30, 80/80 e ~2.500/4.000 caracteres) |
| `imagens/icone-512.png` | Ícone da ficha (512 × 512) |
| `imagens/destaque-1024x500.jpg` | Gráfico de destaque |
| `imagens/celular-01..06.jpg` | Capturas do celular (1080 × 1920) |
| `textos/novidades.txt` | Notas da versão (campo "Notas da versão" de cada lançamento, até 500 caracteres) |
| `FORMULARIOS.md` | Respostas de segurança dos dados, saúde, classificação, público-alvo |
| `TESTADORES.md` | Teste fechado: Grupo do Google, mensagens de convite prontas, roteiro dos 14 dias e respostas para pedir a produção |

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

## Passo 0. Ver o app no seu celular hoje

No Android, abra https://github.com/Ridd1kulusC0d3r/tdah/releases/tag/teste-android, baixe `agora-2.2.0-teste.apk` e permita instalar quando o sistema pedir. É o mesmo app da loja, com assinatura de teste.

## Passo 1. Conta de desenvolvedor (uma vez)

1. Abra https://play.google.com/console/signup e escolha o tipo de conta.
   - **Pessoal:** pede documento e verificação de identidade. Contas pessoais criadas depois de 13/11/2023 precisam de um **teste fechado com pelo menos 12 testadores, inscritos sem parar por 14 dias**, antes de liberar a produção.
   - **Organização:** pede CNPJ e número D-U-N-S (gratuito, sai em alguns dias úteis). A regra dos 12 testadores é das contas pessoais.
2. Pague a taxa de registro (única) e conclua a verificação.

## Passo 2. Chave de assinatura (já criada: só colar no GitHub, 2 minutos)

A chave de upload já foi gerada e veio no arquivo `agora-chave-assinatura.zip` (fora do repositório). Dentro dele:

| Arquivo | O que fazer |
|---|---|
| `chave-assinatura.jks` | Guardar em dois lugares (cofre de senhas e pendrive). Sem ela você não atualiza o app. |
| `AGORA_KEYSTORE_SENHA.txt` | A senha. Guardar junto com a chave. |
| `AGORA_KEYSTORE_BASE64.txt` | A chave em texto, para colar no GitHub. |

1. No GitHub: *Settings › Secrets and variables › Actions › New repository secret*. Crie dois:
   - Nome `AGORA_KEYSTORE_BASE64`, valor = todo o conteúdo de `AGORA_KEYSTORE_BASE64.txt`
   - Nome `AGORA_KEYSTORE_SENHA`, valor = o conteúdo de `AGORA_KEYSTORE_SENHA.txt`
2. *Actions › Android › Run workflow*. Ao terminar, o AAB assinado aparece em **Releases › rascunho "Agora 2.2.0 para a Google Play"** (só você vê) e também na aba *Artifacts* da execução.

Por que não é arriscado: o Play Console usa a **Assinatura de apps do Google Play**. O Google guarda a chave que assina o app de verdade; esta é só a **chave de upload**. Se ela vazar ou se perder, você pede a troca em *Configuração › Integridade do app*.

Prefere criar a sua? Rode `android/gerar-chave.sh` no seu computador (precisa do Java) e cadastre os mesmos dois secrets.
A chave **não** vai para o repositório: o `.gitignore` já ignora `*.jks`.

## Passo 3. Política de privacidade (já pública)

A política do app está em `PRIVACIDADE.md`, na raiz do repositório, e o GitHub já a mostra como página pública:
https://github.com/Ridd1kulusC0d3r/tdah/blob/main/PRIVACIDADE.md

É esse o link que o app abre em Mais e o que vai no Play Console. Quando o site estiver no ar (GitHub Pages ou Netlify, veja `prototipo/PUBLICAR.md`), você pode trocar: crie a variável `AGORA_PRIVACIDADE_URL` em *Settings › Secrets and variables › Actions › Variables* com o novo endereço e rode o build de novo.
O texto sai de `ferramentas/prototipo_legal/privacidade-app.md`; ao mudar, rode `python3 ferramentas/gerar_prototipo.py`.

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

1. **Teste interno** (opcional, sai em minutos): *Testar e lançar › Teste interno › Criar versão*, envie o `.aab`, cole `textos/novidades.txt` em "Notas da versão", adicione o seu e-mail na lista de testadores e instale pelo link.
2. **Teste fechado** (obrigatório para conta pessoal): *Teste fechado › Criar faixa*, envie o mesmo `.aab` e siga `TESTADORES.md` (grupo, convites e roteiro dos 14 dias).
   Boas fontes de testadores: colegas de profissão, pacientes adultos que aceitarem (sem obrigação), turma da Lume.
3. Depois dos 14 dias: *Painel › Solicitar acesso à produção*. O Google pergunta como foi o teste; responda com o que mudou a partir dos comentários.
4. **Produção:** crie a versão, escolha *Brasil* em países e envie para revisão (costuma levar de alguns dias a uma semana).

## Antes de enviar cada versão

- [ ] `python3 -m unittest tests.test_publicacao` passou (inclui o modo Android sem servidor).
- [ ] O e-mail de contato (`AGORA_CONTATO_PUBLICO`) é um endereço que alguém lê.
- [ ] A política de privacidade abre no endereço cadastrado (`PRIVACIDADE.md` no GitHub, ou o site).
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
