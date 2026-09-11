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
# Flask/Jinja ve PDF okuyucular dinamik import kullanır; açıkça belirtmek gerekir.
GIZLI = ["flask", "jinja2", "werkzeug", "yaml", "requests", "pypdf",
         "isbot.sources.greenhouse", "isbot.sources.lever", "isbot.sources.ashby",
         "isbot.sources.workable", "isbot.sources.smartrecruiters",
         "isbot.sources.remotive", "isbot.sources.remoteok"]

a = Analysis(["uygulama.py"], pathex=["."], datas=VERI, hiddenimports=GIZLI,
             excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy",
                       "PyQt5", "PySide6", "IPython", "notebook", "torch"],
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
                             "CFBundleShortVersionString": "0.1.0",
                             "LSBackgroundOnly": False,
                             "NSHighResolutionCapable": True})
