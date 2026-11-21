# Publicar o protótipo do Agora

Esta pasta é o Agora como site estático: não precisa de servidor, banco nem Python.
O app do paciente funciona completo, com dados de exemplo, e guarda tudo no aparelho de quem usa.
Contas, vínculo com o psicólogo, pagamentos e administração ficam para a versão de lançamento.

Todas as páginas têm a faixa amarela "Protótipo" e pedem para não aparecer no Google (noindex).

## Jeito mais rápido: Netlify Drop (2 minutos)

1. Abra https://app.netlify.com/drop e entre com sua conta (Google ou GitHub servem).
2. Arraste **esta pasta inteira** (agora-prototipo) para a área pontilhada.
3. Pronto: o Netlify mostra um endereço como `https://nome-aleatorio.netlify.app`.
   Em *Site configuration › Change site name* você troca para algo como `agora-prototipo`.

## Cloudflare Pages

1. https://dash.cloudflare.com › Workers & Pages › Create › Pages › **Upload assets**.
2. Dê um nome ao projeto, arraste esta pasta e clique em *Deploy*.
3. Para usar seu domínio: *Custom domains* › `prototipo.seudominio.com.br`.

## GitHub Pages (quando criar o repositório)

1. No repositório, crie a pasta `docs/` ou um repositório só para o protótipo e suba o conteúdo desta pasta.
2. Settings › Pages › Source: *Deploy from a branch* › branch `main`, pasta `/` (ou `/docs`).
3. O endereço fica `https://SEU-USUARIO.github.io/NOME-DO-REPO/`. Os links são relativos, então funciona em subpasta.

## Endereços

| Página | Caminho |
|---|---|
| Site | `index.html` |
| Por onde começar | `comecar.html` |
| Serviços (vitrine; pedidos viram e-mail) | `servicos.html` |
| App do paciente (instalável no celular) | `app/index.html` |
| Painel do psicólogo (convite para o piloto) | `app/pro.html` |

## Antes de divulgar

- [ ] Preencher os campos entre colchetes em `privacidade.html` e `termos.html` (ou tirar os links do rodapé).
- [ ] Conferir o e-mail de contato que aparece nos botões (vem de `AGORA_CONTATO_PUBLICO`).
- [ ] Abrir no celular e instalar o app pela opção "Adicionar à tela inicial".

Para gerar de novo depois de mudar o app: `python3 ferramentas/gerar_prototipo.py`.
