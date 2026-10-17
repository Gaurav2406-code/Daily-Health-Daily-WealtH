#!/usr/bin/env bash
set -e

echo "=== HealthTrack Android Build Process ==="

mkdir -p assets src/assets
if [ -f "icon.png" ]; then
    cp -f icon.png assets/icon.png
    cp -f icon.png src/assets/icon.png
elif [ -f "assets/icon.png" ]; then
    cp -f assets/icon.png icon.png
    cp -f assets/icon.png src/assets/icon.png
fi

mkdir -p android_res/values android_res/drawable android_res/mipmap-anydpi-v26
mkdir -p android_res/mipmap-mdpi android_res/mipmap-hdpi android_res/mipmap-xhdpi android_res/mipmap-xxhdpi android_res/mipmap-xxxhdpi

[ -f "colors.xml" ] && cp -f colors.xml android_res/values/colors.xml || true
[ -f "ic_launcher_background.xml" ] && cp -f ic_launcher_background.xml android_res/drawable/ic_launcher_background.xml || true
[ -f "ic_launcher.xml" ] && cp -f ic_launcher.xml android_res/mipmap-anydpi-v26/ic_launcher.xml || true
[ -f "ic_launcher_round.xml" ] && cp -f ic_launcher_round.xml android_res/mipmap-anydpi-v26/ic_launcher_round.xml || true

for m in mdpi hdpi xhdpi xxhdpi xxxhdpi; do
    [ -f "ic_launcher.png" ] && cp -f ic_launcher.png "android_res/mipmap-$m/ic_launcher.png" || true
    [ -f "ic_launcher_round.png" ] && cp -f ic_launcher_round.png "android_res/mipmap-$m/ic_launcher_round.png" || true
    [ -f "ic_launcher_foreground.png" ] && cp -f ic_launcher_foreground.png "android_res/mipmap-$m/ic_launcher_foreground.png" || true
done

if ! command -v flet &> /dev/null; then
    echo "Flet CLI install kiya ja raha hai..."
    pip install "flet[all]"
fi

echo "1. Flutter Android project initialize ho raha hai..."
yes | flet build apk --yes -v

echo "2. Building Release AAB (Google Play Store)..."
yes | flet build aab --yes -v || true

echo "=== Build Complete! Branded APK ready in build/apk/ ==="
