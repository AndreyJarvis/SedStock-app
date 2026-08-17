#!/bin/bash
# ---------------------------------------------------------------------------
# Подписывает и нотаризует .app для macOS (запускается в GitHub Actions).
# Ничего не трогает, если секреты не заданы — вызывающий workflow это проверяет.
#
# Использует переменные окружения (из GitHub Secrets):
#   MAC_CERT_P12_BASE64   — сертификат «Developer ID Application» (.p12) в base64
#   MAC_CERT_PASSWORD     — пароль от .p12
#   AC_API_KEY_P8_BASE64  — ключ App Store Connect API (.p8) в base64
#   AC_API_KEY_ID         — Key ID этого ключа
#   AC_API_ISSUER_ID      — Issuer ID (из App Store Connect → Integrations)
#   MAC_KEYCHAIN_PASSWORD — (необязательно) пароль временной связки ключей
#
# Аргумент: путь к .app (например dist/SedStock.app)
# ---------------------------------------------------------------------------
set -euo pipefail

APP="${1:?Укажите путь к .app}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENTITLEMENTS="$SCRIPT_DIR/../entitlements.plist"
TMP="${RUNNER_TEMP:-/tmp}"
KPW="${MAC_KEYCHAIN_PASSWORD:-ci-temp-$(date +%s)}"

echo "==> Импортирую сертификат во временную связку ключей"
KEYCHAIN="$TMP/build.keychain-db"
echo "$MAC_CERT_P12_BASE64" | base64 --decode > "$TMP/cert.p12"
security create-keychain -p "$KPW" "$KEYCHAIN"
security set-keychain-settings -lut 21600 "$KEYCHAIN"
security unlock-keychain -p "$KPW" "$KEYCHAIN"
security import "$TMP/cert.p12" -k "$KEYCHAIN" -P "$MAC_CERT_PASSWORD" \
    -T /usr/bin/codesign -T /usr/bin/security
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KPW" "$KEYCHAIN" >/dev/null
# делаем связку видимой для codesign
security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | sed s/\"//g)

IDENTITY=$(security find-identity -v -p codesigning "$KEYCHAIN" \
    | grep "Developer ID Application" | head -1 | awk '{print $2}')
if [ -z "$IDENTITY" ]; then
    echo "ОШИБКА: в сертификате не найден 'Developer ID Application'"; exit 1
fi
echo "    Подписываю идентичностью: $IDENTITY"

echo "==> Подписываю вложенные бинарники (.dylib/.so и исполняемые)"
# сначала всё вложенное, потом сам бандл (глубже -> выше)
find "$APP/Contents" -type f -print0 | while IFS= read -r -d '' f; do
    if file "$f" | grep -q "Mach-O"; then
        codesign --force --timestamp --options runtime -s "$IDENTITY" "$f" \
            >/dev/null 2>&1 || echo "    (пропущен: $f)"
    fi
done

echo "==> Подписываю сам .app с разрешениями"
codesign --force --timestamp --options runtime \
    --entitlements "$ENTITLEMENTS" -s "$IDENTITY" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "==> Отправляю на нотаризацию Apple (может занять 1–15 минут)"
echo "$AC_API_KEY_P8_BASE64" | base64 --decode > "$TMP/ac_api.p8"
ditto -c -k --keepParent "$APP" "$TMP/notarize.zip"
xcrun notarytool submit "$TMP/notarize.zip" \
    --key "$TMP/ac_api.p8" \
    --key-id "$AC_API_KEY_ID" \
    --issuer "$AC_API_ISSUER_ID" \
    --wait

echo "==> Прикрепляю штамп нотаризации (stapler)"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"

echo "==> Готово: приложение подписано и нотаризовано ✔"
