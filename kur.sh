#!/usr/bin/env bash
# Derle ve KUR. Tek kopya bırakır.
#
# NEDEN dist/ temizleniyor: derleme çıktısı da ~/Applications'daki kurulu kopya da
# aynı adı taşıyor ve Launchpad İKİSİNİ de gösteriyordu. Kurulumdan sonra derleme
# çıktısı siliniyor; sistemde tek "İş Başvuru Botu" kalıyor.
#
# NEDEN ~/Applications: proje dizini masaüstünde, yani iCloud içinde. 88 MB'lık
# uygulama "dataless" olup buluta çekilirse açılış takılır. ~/Applications iCloud dışı.
set -euo pipefail
cd "$(dirname "$0")"

HEDEF="$HOME/Applications/IsBasvuruBotu.app"

echo "1/4 derleniyor…"
python3 -m PyInstaller --noconfirm --log-level ERROR isbot-panel.spec >/dev/null

echo "2/4 imzalanıyor…"
find dist/IsBasvuruBotu.app -exec xattr -c {} \; 2>/dev/null || true
codesign -s - --force dist/IsBasvuruBotu.app >/dev/null 2>&1 || true

echo "3/4 kuruluyor: $HEDEF"
pkill -f IsBasvuruBotu 2>/dev/null || true
sleep 1
mkdir -p "$HOME/Applications"
rm -rf "$HEDEF"
ditto dist/IsBasvuruBotu.app "$HEDEF"
xattr -cr "$HEDEF" 2>/dev/null || true
codesign -s - --force "$HEDEF" >/dev/null 2>&1 || true

echo "4/4 derleme çıktısı temizleniyor (tek kopya kalsın)"
rm -rf dist build

echo
echo "Kuruldu. Çift tıkla:  $HEDEF"
echo "Veya:  open \"$HEDEF\""
