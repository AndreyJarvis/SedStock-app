#!/bin/bash
# ---------------------------------------------------------------------------
# Подписывает и нотаризует .app через rcodesign (запускается в GitHub Actions).
# rcodesign читает .p12 сам, без macOS-связки ключей, поэтому нет капризов
# `security import` (MAC verification failed и т.п.).
#
# Переменные окружения (из GitHub Secrets):
#   MAC_CERT_P12_BASE64   — сертификат Developer ID Application (.p12, leaf) в base64
#   MAC_CERT_PASSWORD     — пароль от .p12
#   AC_API_KEY_P8_BASE64  — ключ App Store Connect API (.p8) в base64
#   AC_API_KEY_ID         — Key ID
#   AC_API_ISSUER_ID      — Issuer ID
#
# Аргумент: путь к .app (например dist/SedStock.app)
# ---------------------------------------------------------------------------
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
# ВАЖНО: секрет AC_API_KEY_P8_BASE64 теперь содержит base64 ГОТОВОГО api-key.json
# (issuer+key-id+ключ уже внутри, собран и проверен заранее). Раньше собирали из
# трёх отдельных секретов — это давало опечатки и ошибку "Unauthenticated".
echo "$AC_API_KEY_P8_BASE64" | base64 --decode > "$TMP/api-key.json"

echo "==> Подписываю $APP (hardened runtime: главный + вложенные executables)"
# Пароль пустой намеренно: .p12 сделан без пароля.
# ВАЖНО: rcodesign НЕ переносит --code-signature-flags на вложенные файлы,
# поэтому hardened runtime навешиваем ЯВНО по пути на каждый вложенный
# исполняемый Mach-O (ffmpeg и т.п.) — иначе нотаризация Apple их отклоняет.
APPNAME="$(basename "$APP" .app)"
SIGN_FLAGS=(--code-signature-flags runtime)   # главный исполняемый файл
while IFS= read -r f; do
    rel="${f#$APP/}"
    [ "$rel" = "Contents/MacOS/$APPNAME" ] && continue   # главный уже покрыт
    if file "$f" | grep -q "Mach-O.*executable"; then
        SIGN_FLAGS+=(--code-signature-flags "${rel}:runtime")
        echo "    + runtime -> $rel"
    fi
done < <(find "$APP/Contents" -type f)

"$RC" sign "${SIGN_FLAGS[@]}" \
    --p12-file "$TMP/cert.p12" --p12-password "" \
    --entitlements-xml-path "$ENTITLEMENTS" \
    "$APP"

echo "==> Отправляю на нотаризацию Apple и прикрепляю штамп (1–15 минут)"
"$RC" notary-submit --max-wait-seconds 15000 --api-key-path "$TMP/api-key.json" --staple "$APP"

echo "==> Проверка подписи"
"$RC" verify "$APP" || true

echo "==> Готово: приложение подписано и нотаризовано ✔"
