#!/usr/bin/env bash
# Gera a chave de assinatura do app (uma vez só). SEM ESTA CHAVE VOCÊ NÃO CONSEGUE ATUALIZAR O APP.
# Guarde o arquivo .jks e as senhas num cofre de senhas e numa cópia offline.
# Com a "Assinatura de apps do Google Play" ativada, esta vira a chave de upload (dá para trocar se perder).
set -e
cd "$(dirname "$0")"
read -r -p "Nome para o certificado (ex.: Agora TDAH): " NOME
read -r -s -p "Crie uma senha forte para a chave: " SENHA; echo
keytool -genkeypair -v -keystore chave-assinatura.jks -alias agora -keyalg RSA -keysize 4096 -validity 10000 \
  -storepass "$SENHA" -keypass "$SENHA" -dname "CN=$NOME, O=$NOME, C=BR"
echo
echo "Chave criada: android/chave-assinatura.jks"
echo "Para o GitHub Actions, cadastre em Settings > Secrets and variables > Actions:"
echo "  AGORA_KEYSTORE_BASE64  = conteúdo de: base64 -w0 chave-assinatura.jks"
echo "  AGORA_KEYSTORE_SENHA   = a senha que você digitou"
echo "  AGORA_API_URL          = https://seu-dominio (endereço do servidor do Agora)"
keytool -list -v -keystore chave-assinatura.jks -storepass "$SENHA" | grep -E "SHA256:" || true
