# -*- mode: python ; coding: utf-8 -*-
# PyInstaller yapılandırması. Kullanım:
#   pyinstaller --noconfirm isbot-panel.spec
# Çıktı: macOS -> dist/IsBasvuruBotu.app   |   Windows -> dist/IsBasvuruBotu/*.exe
import sys

# DİKKAT: Veri dosyalarını TEK TEK yazma. İlk sürümde öyleydi ve sonradan eklenen
# isbot/data/roller.yaml pakete HİÇ girmedi; paketlenmiş uygulamada rol aileleri ve
# profil tazeleme sessizce çalışmadı. Dizinin tamamı toplanıyor.
from pathlib import Path as _P

VERI = [("isbot/web/index.html", "isbot/web"),
        ("config/companies.yaml", "config")]
VERI += [(str(y), "isbot/data") for y in sorted(_P("isbot/data").glob("*.yaml"))]
assert any("skills.yaml" in v[0] for v in VERI), "skills.yaml bulunamadı"
assert any("roller.yaml" in v[0] for v in VERI), "roller.yaml bulunamadı"

# --- uyum modeli (gelişmiş arama) ---
# Model .app'in İÇİNE gömülür: kullanıcı hiçbir şey indirmez, uygulama çevrimdışı
# çalışır. Dosyalar depoda DURMAZ (129 MB); kur.sh derlemeden önce indirir.
# Yoksa paketleme YİNE DE başarılı olur — uygulama o durumda yalnız hızlı modda
# çalışır ve panelde gelişmiş seçeneği hiç görünmez.
_MODEL = _P("isbot/model")
_MODEL_DOSYALARI = ["model_int8.onnx", "tokenizer.json"]
_model_tam = all((_MODEL / d).exists() for d in _MODEL_DOSYALARI)
if _model_tam:
    VERI += [(str(_MODEL / d), "isbot/model") for d in _MODEL_DOSYALARI]
    print(f"[spec] uyum modeli gömülüyor ({sum((_MODEL/d).stat().st_size for d in _MODEL_DOSYALARI)//(1024*1024)} MB)")
else:
    print("[spec] UYARI: isbot/model eksik — uygulama yalnız hızlı modda çalışacak. "
          "Modeli indirmek için: ./calistir.sh --model-indir")

# Flask/Jinja ve PDF okuyucular dinamik import kullanır; açıkça belirtmek gerekir.
GIZLI = ["flask", "jinja2", "werkzeug", "yaml", "requests", "pypdf",
         "isbot.sources.greenhouse", "isbot.sources.lever", "isbot.sources.ashby",
         "isbot.sources.workable", "isbot.sources.smartrecruiters",
         "isbot.sources.remotive", "isbot.sources.remoteok"]
if _model_tam:
    # onnxruntime kendi yerel kütüphanesini dinamik yükler; tokenizers Rust eklentisi.
    GIZLI += ["onnxruntime", "onnxruntime.capi", "onnxruntime.capi._pybind_state",
              "tokenizers", "numpy", "isbot.uyum"]

# DİKKAT: numpy ESKİDEN excludes içindeydi. Uyum modeli numpy'a bağlı olduğu için
# o hâliyle paketlenmiş uygulamada gelişmiş arama SESSİZCE çalışmazdı — kaynaktan
# çalıştırınca sorun görünmediği için gözden kaçması çok kolaydı.
DISLANAN = ["tkinter", "matplotlib", "pandas", "scipy",
            "PyQt5", "PySide6", "IPython", "notebook", "torch"]
if not _model_tam:
    DISLANAN.append("numpy")        # model yoksa numpy'ı taşımanın anlamı yok

a = Analysis(["uygulama.py"], pathex=["."], datas=VERI, hiddenimports=GIZLI,
             excludes=DISLANAN,
             noarchive=False)
pyz = PYZ(a.pure)
# Simge: macOS .icns, Windows .ico ister. Yoksa None verilir (varsayılan simge).
IKON = "simge/ikon.icns" if sys.platform == "darwin" else "simge/ikon.ico"
if not _P(IKON).exists():
    IKON = None

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="IsBasvuruBotu",
          console=False, disable_windowed_traceback=False, argv_emulation=False,
          target_arch=None, codesign_identity=None, entitlements_file=None,
          icon=IKON)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="IsBasvuruBotu")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="IsBasvuruBotu.app", icon=IKON,
                 bundle_identifier="dev.berketez.isbasvurubotu",
                 info_plist={"CFBundleDisplayName": "İş Başvuru Botu",
                             "CFBundleShortVersionString": "1.5.10",
                             "LSBackgroundOnly": False,
                             "NSHighResolutionCapable": True})
