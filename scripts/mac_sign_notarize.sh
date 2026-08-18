#!/bin/bash
set -euo pipefail

APP="${1:?Укажите путь к .app}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENTITLEMENTS="$SCRIPT_DIR/../entitlements.plist"
TMP="${RUNNER_TEMP:-/tmp}"
RC_VER="0.29.0"
RC_URL="https://github.com/indygreg/apple-platform-rs/releases/download/apple-codesign/${RC_VER}/apple-codesign-${RC_VER}-aarch64-apple-darwin.tar.gz"

echo "==> Скачиваю rcodesign ${RC_VER}"
curl -sL "$RC_URL" -o "$TMP/rc.tar.gz"
tar -xzf "$TMP/rc.tar.gz" -C "$TMP"
RC="$(find "$TMP" -name rcodesign -type f | head -1)"
chmod +x "$RC"
"$RC" --version

echo "==> Готовлю сертификат и ключ нотаризации"
echo "$MAC_CERT_P12_BASE64" | base64 --decode > "$TMP/cert.p12"
echo "$AC_API_KEY_P8_BASE64" | base64 --decode > "$TMP/authkey.p8"
"$RC" encode-app-store-connect-api-key -o "$TMP/api-key.json" \
    "$AC_API_ISSUER_ID" "$AC_API_KEY_ID" "$TMP/authkey.p8"

echo "==> Подписываю $APP (hardened runtime + разрешения)"
"$RC" sign \
    --p12-file "$TMP/cert.p12" --p12-password "" \
    --code-signature-flags runtime \
    --entitlements-xml-path "$ENTITLEMENTS" \
    "$APP"

echo "==> Отправляю на нотаризацию Apple и прикрепляю штамп (1–15 минут)"
"$RC" notary-submit --api-key-path "$TMP/api-key.json" --staple "$APP"

echo "==> Проверка подписи"
"$RC" verify "$APP" || true

echo "==> Готово: приложение подписано и нотаризовано ✔"
