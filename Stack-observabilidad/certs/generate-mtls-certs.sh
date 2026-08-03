#!/usr/bin/env bash
# Genera una CA local + certificado de servidor (otel-collector) + certificado
# de cliente (session-logger) para pruebas de transporte mTLS en local.
#
# Uso: bash Stack-observabilidad/certs/generate-mtls-certs.sh
#
# Los archivos generados son SOLO para desarrollo/pruebas locales.
# No usar en producción ni commitear las claves privadas (.key).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DAYS=825
CA_SUBJ="/CN=session-logger-local-ca"
SERVER_SUBJ="/CN=otel-collector"
CLIENT_SUBJ="/CN=session-logger-client"

echo "==> Generando CA local"
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days "$DAYS" \
  -subj "$CA_SUBJ" -out ca.crt

echo "==> Generando certificado de servidor (otel-collector)"
openssl genrsa -out server.key 4096
openssl req -new -key server.key -subj "$SERVER_SUBJ" -out server.csr
cat > server.ext <<EOF
subjectAltName = DNS:otel-collector, DNS:localhost, IP:127.0.0.1
extendedKeyUsage = serverAuth
EOF
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days "$DAYS" -sha256 -extfile server.ext

echo "==> Generando certificado de cliente (session-logger)"
openssl genrsa -out client.key 4096
openssl req -new -key client.key -subj "$CLIENT_SUBJ" -out client.csr
cat > client.ext <<EOF
extendedKeyUsage = clientAuth
EOF
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out client.crt -days "$DAYS" -sha256 -extfile client.ext

rm -f server.csr client.csr server.ext client.ext ca.srl
chmod 600 ca.key server.key client.key

echo "==> Certificados generados en $SCRIPT_DIR:"
ls -la "$SCRIPT_DIR"
