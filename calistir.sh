#!/usr/bin/env bash
# Tek komutla çalıştır:  ./calistir.sh
#
# NEDEN VAR: ilk sürümde kurulumun tek yolu ./kur.sh (PyInstaller ile .app derlemek)
# idi ve yeni bir makinede ZİNCİRLEME kırıldı — PyInstaller kurulu değil, ardından
# flask/requests/rich eksik, ardından pdftotext yok. Her adım ayrı bir hata mesajı
# verip durdu; kullanıcı tek tek kurmak zorunda kaldı. Bu betik o zincirin tamamını
# ÖNCEDEN denetler, eksikleri KENDİ İZOLE ORTAMINA kurar ve paneli açar.
# Sistem Python'ına hiçbir şey yazmaz (venv kullanır).
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
KIRMIZI=$'\033[31m'; YESIL=$'\033[32m'; SARI=$'\033[33m'; SIFIR=$'\033[0m'
bilgi() { echo "${YESIL}•${SIFIR} $*"; }
uyar()  { echo "${SARI}!${SIFIR} $*"; }
hata()  { echo "${KIRMIZI}✗${SIFIR} $*" >&2; }

# ---- 1) Python 3.10+ ----
PY=""
for aday in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$aday" >/dev/null 2>&1 && \
     "$aday" -c 'import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
    PY="$aday"; break
  fi
done
if [ -z "$PY" ]; then
  hata "Python 3.10 veya üstü bulunamadı."
  echo "  macOS  : brew install python@3.12"
  echo "  Ubuntu : sudo apt install python3 python3-venv"
  echo "  Windows: https://www.python.org/downloads/  (kurulumda 'Add to PATH' işaretle)"
  exit 1
fi
bilgi "Python: $("$PY" --version) ($PY)"

# ---- 2) Sanal ortam ----
if [ ! -d "$VENV" ]; then
  bilgi "sanal ortam kuruluyor ($VENV) — sistem Python'ına dokunulmaz"
  "$PY" -m venv "$VENV" || {
    hata "venv kurulamadı. Ubuntu'da eksik olan paket: sudo apt install python3-venv"
    exit 1; }
fi
VPY="$VENV/bin/python"
[ -x "$VPY" ] || VPY="$VENV/Scripts/python.exe"      # Windows (Git Bash)
[ -x "$VPY" ] || { hata "sanal ortam bozuk görünüyor. Sil ve tekrar dene: rm -rf $VENV"; exit 1; }

# ---- 3) Bağımlılıklar ----
# KURULUM, requirements.txt'in İÇERİĞİNE bakar — tek tek paket adına değil.
# ÖLÇÜLDÜ: kontrol "import flask, requests, yaml, rich" ile yapılıyordu; sonradan
# eklenen onnxruntime hiçbir makinede kurulmadı ve gelişmiş arama sessizce kapalı
# kaldı. Dosya değiştiyse kurulum tekrar koşar, değişmediyse hiç dokunulmaz.
DAMGA="$VENV/.requirements-damga"
YENI_DAMGA="$( (shasum -a 256 requirements.txt 2>/dev/null || sha256sum requirements.txt) | cut -d' ' -f1)"
if [ ! -f "$DAMGA" ] || [ "$(cat "$DAMGA" 2>/dev/null)" != "$YENI_DAMGA" ] \
   || ! "$VPY" -c "import flask, requests, yaml, rich" >/dev/null 2>&1; then
  bilgi "bağımlılıklar kuruluyor/güncelleniyor (bir kereliğine)…"
  "$VPY" -m pip install --quiet --upgrade pip
  if "$VPY" -m pip install --quiet -r requirements.txt; then
    echo "$YENI_DAMGA" > "$DAMGA"
  else
    hata "bağımlılıklar kurulamadı. İnternet bağlantını kontrol et."
    echo "  Elle denemek için: $VPY -m pip install -r requirements.txt"
    exit 1
  fi
fi
bilgi "bağımlılıklar hazır"

# ---- 4) pdftotext (zorunlu değil ama PDF kalitesini belirgin artırır) ----
if ! command -v pdftotext >/dev/null 2>&1; then
  uyar "pdftotext (poppler) yok — PDF okuma yedek yola (pypdf) düşecek."
  echo "  Sütunlu/iki kolonlu CV'lerde metin bozulabilir. Kurulumu:"
  case "$(uname -s)" in
    Darwin) echo "      brew install poppler" ;;
    Linux)  echo "      sudo apt install poppler-utils" ;;
    *)      echo "      https://github.com/oschwartz10612/poppler-windows (PATH'e ekle)" ;;
  esac
  echo
fi

# ---- 5) Uyum modeli (gelişmiş arama) ----
# Model depoda DURMAZ (129 MB). Yoksa uygulama yalnız "hızlı arama" ile çalışır;
# panelde gelişmiş seçeneği hiç görünmez. Bir kez indirilir, sonra çevrimdışı çalışır.
MODEL_DIZIN="isbot/model"
MODEL_KOK="https://huggingface.co/Xenova/multilingual-e5-small/resolve/main"
model_indir() {
  mkdir -p "$MODEL_DIZIN"
  bilgi "uyum modeli indiriliyor (~129 MB, bir kereliğine)…"
  curl -fL --progress-bar "$MODEL_KOK/onnx/model_int8.onnx" \
       -o "$MODEL_DIZIN/model_int8.onnx.parca" || { hata "model indirilemedi"; return 1; }
  curl -fL --progress-bar "$MODEL_KOK/tokenizer.json" \
       -o "$MODEL_DIZIN/tokenizer.json.parca" || { hata "tokenizer indirilemedi"; return 1; }
  # Yarım inen dosya "var" sayılmasın diye ancak tamamlanınca adı konur.
  mv "$MODEL_DIZIN/model_int8.onnx.parca" "$MODEL_DIZIN/model_int8.onnx"
  mv "$MODEL_DIZIN/tokenizer.json.parca" "$MODEL_DIZIN/tokenizer.json"
  bilgi "uyum modeli hazır"
}

if [ "${1:-}" = "--model-indir" ]; then
  model_indir || exit 1
  shift
fi

if [ ! -f "$MODEL_DIZIN/model_int8.onnx" ] || [ ! -f "$MODEL_DIZIN/tokenizer.json" ]; then
  uyar "Gelişmiş arama kapalı — uyum modeli yok (yalnız hızlı arama çalışır)."
  echo "  İndirmek için:  ./calistir.sh --model-indir"
  echo
fi

# ---- 6) Panel ----
bilgi "panel açılıyor — kapatmak için Ctrl+C"
exec "$VPY" -m isbot panel "$@"
