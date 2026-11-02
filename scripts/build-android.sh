#!/usr/bin/env bash
# Build the « EMB Relais » Android app (release APK, signed).
#
#   scripts/build-android.sh            → android/dist/emb-relais-<version>.apk
#
# Needs a JDK 17 and the Android SDK (ANDROID_HOME, default ~/Android/Sdk).
# The signing key is created on first run in ~/.android/emb-relais.jks (outside
# the repo). Keep it: an update must be signed with the same key to install over
# the previous version (otherwise uninstall, reinstall and pair again).
set -euo pipefail
cd "$(dirname "$0")/../android"

export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
[[ -d "$ANDROID_HOME/platforms" ]] || { echo "Android SDK not found in $ANDROID_HOME" >&2; exit 1; }

PROPS="${EMB_RELAIS_SIGNING:-$HOME/.android/emb-relais.properties}"
if [[ ! -f "$PROPS" ]]; then
    KEYSTORE="$(dirname "$PROPS")/emb-relais.jks"
    PASS="$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)"
    mkdir -p "$(dirname "$PROPS")"
    keytool -genkeypair -keystore "$KEYSTORE" -alias emb-relais -keyalg RSA -keysize 3072 \
        -validity 10000 -storepass "$PASS" -keypass "$PASS" \
        -dname "CN=EMB Relais, O=Etic'Monts, C=FR" >/dev/null 2>&1
    printf 'storeFile=%s\nstorePassword=%s\nkeyAlias=emb-relais\nkeyPassword=%s\n' "$KEYSTORE" "$PASS" "$PASS" > "$PROPS"
    chmod 600 "$PROPS" "$KEYSTORE"
    echo "created signing key: $KEYSTORE (back it up)"
fi
export EMB_RELAIS_SIGNING="$PROPS"

./gradlew --console=plain -q :app:testReleaseUnitTest :app:assembleRelease

VERSION="$(grep -E 'versionName = ' app/build.gradle.kts | sed -E 's/.*"(.*)".*/\1/')"
mkdir -p dist
OUT="dist/emb-relais-$VERSION.apk"
cp app/build/outputs/apk/release/app-release.apk "$OUT"
APKSIGNER="$(ls -d "$ANDROID_HOME"/build-tools/*/ | sort -V | tail -1)apksigner"
"$APKSIGNER" verify --print-certs "$OUT" | grep -E "Signer #1 certificate (DN|SHA-256)" || { echo "APK not signed" >&2; exit 1; }
echo "APK: $(pwd)/$OUT ($(du -h "$OUT" | cut -f1))"
echo "sha256: $(sha256sum "$OUT" | cut -d' ' -f1)"
