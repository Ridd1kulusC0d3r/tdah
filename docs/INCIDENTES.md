# Plano de resposta a incidentes de segurança

Para quando houver suspeita de acesso indevido, vazamento, perda de dados ou indisponibilidade longa. Base: LGPD art. 48 e Resolução CD/ANPD nº 15/2024 (comunicação de incidente em até **3 dias úteis** quando houver risco ou dano relevante aos titulares).

**Responsável pela resposta:** [NOME] · **Encarregado (DPO):** [NOME, e-mail] · **Apoio técnico:** [NOME, telefone] · **Advogado:** [NOME, telefone]

## Hora 0: conter

1. Anote a hora em que soube e por qual canal. Abra um arquivo `incidente-AAAAMMDD.md` fora do servidor e registre tudo o que fizer, com hora.
2. Se houver acesso indevido em andamento: `docker compose stop agora` (o site sai do ar; os dados ficam).
3. Troque as senhas e chaves que podem ter vazado:
   - credenciais do servidor e do provedor de nuvem;
   - `MP_ACCESS_TOKEN` / `STRIPE_SECRET_KEY` e segredos de webhook (gere novos no painel do provedor);
   - `AGORA_CHAVE` (siga `docs/PRODUCAO.md` seção 6, mantendo a antiga para abrir os dados);
   - derrube todas as sessões: `docker compose exec agora python3 -c "import sqlite3;c=sqlite3.connect('/dados/agora.db');c.execute('DELETE FROM tokens');c.commit()"`.
4. Faça uma cópia do banco e dos logs **como estão** (evidência), antes de mexer: `python3 server/backup.py --sem-s3 --destino /backups/incidente`.

## Até 24 h: entender

- Quais dados? Use a tabela abaixo para classificar.
- De quantas pessoas? Consulte `auditoria`, `erros` e os logs JSON de acesso (IP, rota, horário).
- Os dados estavam cifrados? Diário, cópia na nuvem, mensagens, anotações e segredos de 2FA ficam cifrados no banco; um banco copiado **sem** a `AGORA_CHAVE` não expõe esses campos. Nome, e-mail e registros de compra **não** são cifrados.

| Dado afetado | Risco | Comunicar ANPD e titulares? |
|---|---|---|
| Campos cifrados, chave não vazou | Baixo | Registrar internamente; avaliar com o encarregado |
| Nome e e-mail | Médio (phishing) | Avaliar; em geral comunicar titulares |
| Dados de saúde em claro (chave vazou junto) | Alto: dado sensível | **Sim**, ANPD e titulares, em até 3 dias úteis |
| Credenciais de pagamento do provedor | Alto financeiro | Comunicar o provedor imediatamente |

## Até 3 dias úteis: comunicar

- **ANPD:** formulário de comunicação de incidente no site da ANPD (gov.br/anpd). Informe: natureza dos dados, titulares afetados, medidas técnicas de proteção (cifra, 2FA), riscos, motivo de eventual demora e medidas tomadas.
- **Titulares:** e-mail em linguagem simples: o que aconteceu, quais dados, o que já foi feito, o que a pessoa pode fazer, canal para dúvidas. Modelo:

> Assunto: Aviso de segurança sobre sua conta no Agora
>
> Olá. Em [data], identificamos [descrição curta]. Os dados envolvidos foram [lista]. Seus registros de diário [estavam / não estavam] protegidos por criptografia. Já [medidas]. Recomendamos [trocar a senha / desconfiar de e-mails pedindo dados]. Dúvidas: [e-mail do encarregado].

- **Profissionais vinculados:** avisar quando dados de pacientes deles estiverem envolvidos (eles têm dever de sigilo e podem precisar comunicar o paciente).
- **CRP:** consulte o advogado se o incidente envolver prontuário ou sigilo profissional.

## Depois: corrigir e aprender

1. Corrija a causa, rode os testes (`./rodar-testes.sh`) e publique.
2. Restaure o serviço e confira `GET /api/health`.
3. Em até 15 dias, escreva o relatório: linha do tempo, causa, dados e pessoas afetadas, comunicações feitas, o que muda para não repetir. Guarde por 5 anos.

## Treino

Uma vez por semestre, simule: restaure um backup num servidor novo, troque a chave e derrube as sessões. Cronometre.
