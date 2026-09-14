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

# ÖNKONTROL — eksikler derleme ORTASINDA değil, en başta ve TEK SEFERDE söylensin.
# İlk sürümde PyInstaller yoksa `python3 -m PyInstaller` ham bir "No module named"
# hatası veriyordu; kullanıcı onu kurunca sıra flask/requests'e geliyordu. Zincir.
EKSIK=""
python3 -c "import PyInstaller" 2>/dev/null || EKSIK="$EKSIK pyinstaller"
python3 -c "import flask, requests, yaml, rich" 2>/dev/null || EKSIK="$EKSIK -r requirements.txt"
if [ -n "$EKSIK" ]; then
  echo "✗ Paketlemek için eksik bağımlılık var."
  echo
  echo "  Kur:   python3 -m pip install$EKSIK"
  echo
  echo "  Not: .app DERLEMEK istemiyorsan buna hiç gerek yok —"
  echo "       ./calistir.sh tek komutla kendi ortamını kurar ve paneli açar."
  exit 1
fi
command -v pdftotext >/dev/null 2>&1 || \
  echo "! pdftotext (poppler) yok — PDF okuma yedek yola düşer. macOS: brew install poppler"

# Uyum modeli .app'in İÇİNE gömülür (çevrimdışı çalışsın diye). Depoda durmadığı
# için derlemeden ÖNCE indirilir. İnternet yoksa paketleme yine sürer; o uygulama
# yalnız "hızlı arama" yapar ve panelde gelişmiş seçeneği görünmez.
if [ ! -f isbot/model/model_int8.onnx ] || [ ! -f isbot/model/tokenizer.json ]; then
  echo "• uyum modeli yok, indiriliyor (~129 MB, bir kereliğine)…"
  MK="https://huggingface.co/Xenova/multilingual-e5-small/resolve/main"
  mkdir -p isbot/model
  # Yarım inen dosya "var" sayılmasın: ancak ikisi de tamamlanınca adları konur.
  if curl -fL --progress-bar "$MK/onnx/model_int8.onnx" \
          -o isbot/model/model_int8.onnx.parca &&
     curl -fL --progress-bar "$MK/tokenizer.json" \
          -o isbot/model/tokenizer.json.parca; then
    mv isbot/model/model_int8.onnx.parca isbot/model/model_int8.onnx
    mv isbot/model/tokenizer.json.parca isbot/model/tokenizer.json
  else
    rm -f isbot/model/*.parca
    echo "! model indirilemedi — uygulama yalnız hızlı modda çalışacak"
  fi
fi

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
