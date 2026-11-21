# Comece aqui — Agora 2.1

Uma ação por vez. Faça só o passo 1 agora.

## 1. Dê dois cliques no lançador do seu sistema

| Sistema | Arquivo |
|---|---|
| Windows | `iniciar-windows.bat` |
| macOS | `iniciar-mac.command` (na 1ª vez: botão direito › Abrir) |
| Linux | `iniciar-linux.sh` |

O navegador abre sozinho no app (**http://localhost:8765/app/**). Deixe a janela preta aberta: ela é o servidor.

Precisa de **Python 3.9+** (python.org/downloads; no Windows marque *Add Python to PATH*). Nenhuma outra instalação.

## 2. Explore

| Endereço | O que é | Entrar com (senha `demo1234`) |
|---|---|---|
| http://localhost:8765/ | Site público | — |
| http://localhost:8765/servicos · /comecar | Catálogo de serviços e página de entrada do funil | — |
| http://localhost:8765/app/ | App do paciente (abre com dados de exemplo) | `bia@demo.agora` (turma da Lume e e-book) ou `lucas@demo.agora` (vinculado) |
| http://localhost:8765/app/pro.html | Painel do psicólogo | `ana@demo.agora` |
| http://localhost:8765/app/admin.html | Administração: receita, funil, contatos, turmas, compras | `admin@demo.agora` + código do autenticador (chave `JBSWY3DPEHPK3PXP`) |

Pagamentos começam em **modo de teste**: a página de checkout tem botões "aprovado", "Pix" e "recusado"; nenhum dinheiro de verdade é cobrado.

## 3. Quando for publicar

1. **Crie o repositório** privado no GitHub e suba esta pasta (o `.gitignore` já deixa de fora dados, `.env` e chaves).
2. **Siga `docs/PRODUCAO.md`**: chave de criptografia, `.env`, `docker compose up -d`, promover sua conta a administradora, webhooks, backup no S3.
3. **Antes de cobrar:** revisão do advogado (privacidade, termos, RIPD em `docs/RIPD.md`) e da publicidade com a orientação do CRP-04.

## O que tem na pasta

| Caminho | O que é |
|---|---|
| `docs/manual.html` | Manual ilustrado com capturas anotadas: uso, serviços, administração, pagamentos, publicação, segurança, problemas |
| `docs/PRODUCAO.md` · `docs/INCIDENTES.md` · `docs/RIPD.md` | Roteiro de produção · resposta a incidentes · relatório de impacto (LGPD) |
| `docs/ESPECIFICACAO.md` · `docs/PLANO-IMPLEMENTACAO.md` | Produto e plano de lançamento |
| `docs/RELATORIO-TESTES.md` | Resultado dos testes automáticos |
| `app/` · `site/` | App do paciente, painel, administração · site, serviços, páginas legais |
| `server/` | Servidor Python (biblioteca padrão; `cryptography` opcional acelera a cifra) |
| `server/admin.py` · `server/backup.py` | Linha de comando: chave, 2FA, administradores, tarefas · backup cifrado e restauração |
| `catalogo/catalogo.json` | Catálogo de serviços (a cópia usada pelo servidor fica em `server/catalogo_padrao.json`) |
| `android/` · `.github/` | Projeto Android (Capacitor) · testes a cada push e build do Android |
| `Dockerfile` · `docker-compose.yml` · `deploy/` · `.env.example` | Publicação com HTTPS, backup e homologação |
| `tests/` · `rodar-testes.sh` | Testes da API, de produção e de ponta a ponta no navegador |

Para zerar a demonstração: feche o servidor e apague a pasta `dados`.

> Ferramenta de apoio à organização. Não faz diagnóstico nem substitui tratamento. Em crise: CVV 188 (24 h) ou SAMU 192.
