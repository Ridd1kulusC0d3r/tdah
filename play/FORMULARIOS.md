# Respostas para o Play Console (app local, sem servidor)

Valem para o build sem `AGORA_API_URL`. Os nomes dos campos seguem o Console em português; se algum mudar de lugar, a pergunta é a mesma.

## Ficha da loja

| Campo | Resposta |
|---|---|
| Categoria do app | **Produtividade** |
| Tags (até 5) | Produtividade · Lista de tarefas · Organização · Bem-estar · Hábitos (escolha as que o Console oferecer mais próximas) |
| E-mail de contato | o mesmo de `AGORA_CONTATO_PUBLICO` (hoje: contato@psicologotech.com.br; **confirme**) |
| Site | endereço do site publicado (ex.: `https://ridd1kulusc0d3r.github.io/tdah/`) |
| Telefone | deixe em branco (opcional) |

Por que Produtividade e não Saúde: o uso principal é organizar tarefas e rotinas. Os recursos de saúde existem e são declarados abaixo, mas não são o centro do app.

## Política do app (Configurar o app)

### Política de privacidade
URL: o endereço público de `prototipo/privacidade.html` (o mesmo de `AGORA_PRIVACIDADE_URL`).

### Acesso ao app
**Todas as funcionalidades estão disponíveis sem restrições de acesso.** (Não há login.)

### Anúncios
**Não, meu app não contém anúncios.**

### Classificação do conteúdo (questionário IARC)
- E-mail para o certificado: o de contato.
- Categoria: **Todos os outros tipos de app** (utilitário, produtividade, comunicação).
- Violência, medo, sexualidade, linguagem, drogas, jogos de azar: **Não** em todas.
- Os usuários interagem ou trocam conteúdo entre si? **Não.**
- O app compartilha a localização do usuário com outros usuários? **Não.**
- Permite comprar produtos digitais? **Não.**
- É um navegador da Web ou mecanismo de pesquisa? **Não.**

Resultado esperado: classificação **Livre**. Isso é a classificação de conteúdo; quem pode usar é definido em *Público-alvo*.

### Público-alvo e conteúdo
- Faixas etárias: marque **apenas 18 anos ou mais**.
- O app pode atrair crianças sem querer? **Não.**

### Segurança dos dados
| Pergunta | Resposta |
|---|---|
| O app coleta ou compartilha algum dos tipos de dados do usuário exigidos? | **Não** |

Com "Não", o Console pula as demais perguntas e a ficha mostra "Nenhum dado coletado" e "Nenhum dado compartilhado com terceiros".

Por que é verdade neste build:
- tarefas, diário, rotinas e preferências ficam no armazenamento do próprio celular e não são enviados para nenhum servidor;
- o app não tem analytics, SDK de anúncios, relatório de falhas próprio nem login;
- o botão "Quero saber mais" abre o **aplicativo de e-mail da pessoa** com uma mensagem que ela pode editar e decide se envia. Pelo critério do Google, dado que sai por outro app, por ação do próprio usuário, não é coleta do nosso app;
- o backup automático do Android (conta Google da pessoa) é do sistema, não do app.

Se um dia entrar qualquer SDK (analytics, crash, anúncio) ou o servidor, esta resposta muda.

### Apps de saúde (declaração)
Todo app publicado precisa preencher, mesmo os que não são de saúde. Marque os recursos que o app tem:

| Grupo | Item | Por quê |
|---|---|---|
| Saúde e fitness | **Gerenciamento do sono** | o diário registra horas e qualidade do sono |
| Saúde e fitness | **Gerenciamento do estresse, relaxamento, acuidade mental** | sons para foco, rotinas, check-in de humor e energia |
| Médico | **Saúde mental e comportamental** | público com TDAH, diário de humor, preparo da sessão de terapia |
| Médico | **Serviços e gerenciamento de saúde** | a página Serviços mostra terapia on-line com psicólogo e o pedido é feito por e-mail |

Não marque: dispositivo médico, apoio à decisão clínica, pesquisa com seres humanos, gerenciamento de medicamentos (o "tomei a medicação" é uma caixa opcional do diário, sem dose, horário ou lembrete de remédio).

Se o Console pedir, o app **não** é regulado como dispositivo médico. O aviso exigido já está no fim de `textos/descricao-completa.txt`.

### Recursos financeiros · Apps governamentais · Notícias · Rastreamento de contato
**Não** em todos.

### Permissões
O app final pede **INTERNET**, **POST_NOTIFICATIONS** (lembretes), **RECEIVE_BOOT_COMPLETED** e **WAKE_LOCK** (para reagendar lembretes depois de reiniciar o celular). Nenhuma delas exige declaração no Console. A permissão de alarme exato, que o plugin de notificações traz, é retirada no `AndroidManifest.xml`.

## Quando o app Android passar a usar o servidor (AGORA_API_URL)

Aí a resposta de segurança dos dados muda para **Sim** e entram:

| Tipo de dado | Coletado | Compartilhado | Opcional? | Para quê |
|---|---|---|---|---|
| Nome, e-mail | sim | não | obrigatório para ter conta | gerenciamento da conta |
| IDs do usuário | sim | não | obrigatório para ter conta | gerenciamento da conta |
| Informações de saúde (diário, humor, sono) | sim, se a pessoa liga a cópia na nuvem ou o vínculo | não | opcional | funcionalidade do app |
| Mensagens no app (pedido de contato ao profissional) | sim | não | opcional | funcionalidade do app |
| Histórico de compras | sim, se houver assinatura | não | opcional | funcionalidade do app |

Mais: dados criptografados em trânsito (HTTPS) **sim**; a pessoa pode pedir exclusão **sim**, com o link de exclusão de conta (`/excluir-conta.html` do site), que o Console passa a exigir quando o app cria contas.
