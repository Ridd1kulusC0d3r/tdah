# Agora — sistema para TDAH

App gratuito para o paciente organizar o dia, painel para o psicólogo acompanhar entre as sessões
(modelo Dietbox) e funil para os serviços da equipe (terapia, treinos de habilidades sociais da Lume,
e-books, empresas). Servidor em Python só com a biblioteca padrão.

| Comece por | Para |
|---|---|
| [`COMECE-AQUI.md`](COMECE-AQUI.md) | Rodar no seu computador com dois cliques e o caso de demonstração |
| [`prototipo/`](prototipo/PUBLICAR.md) | Publicar o protótipo como site estático (sem servidor) |
| [`docs/manual.html`](docs/manual.html) | Manual ilustrado (baixe e abra no navegador) |
| [`docs/PRODUCAO.md`](docs/PRODUCAO.md) | Colocar no ar em produção, passo a passo |
| [`docs/RELATORIO-TESTES.md`](docs/RELATORIO-TESTES.md) | Resultado dos testes |

```bash
./rodar-testes.sh                         # testes da API, de produção e do navegador
python3 ferramentas/gerar_prototipo.py    # regenera prototipo/ depois de mudar app, site ou catálogo
```

Responsável técnico pelos serviços psicológicos: Deivison Mendes, CRP-04/65709.
Ferramenta de apoio à organização: não faz diagnóstico nem substitui tratamento. Em crise: CVV 188, SAMU 192.

## Retomada e preparação da sessão

O app agora guarda contexto para retomar tarefas e cursos, permite experimentar um plano menor sem alterar o original e oferece resumo editável antes do compartilhamento. Veja [comportamento e validação](docs/RETOMADA-E-PREPARO.md).
