"""Dosya yolları — hem kaynaktan hem paketlenmiş (.app/.exe) çalışırken doğru.

SORUN: PyInstaller ile paketlenince (a) uygulama paketinin İÇİ salt-okunurdur, oraya
profil/veritabanı yazılamaz; (b) çalışma dizini belirsizdir (macOS'ta "/" olabilir);
(c) paket içindeki veri dosyaları `sys._MEIPASS` altındaki geçici dizindedir.

ÇÖZÜM: iki ayrı kök.
  KAYNAK_KOK  -> salt-okunur paket verisi (skills.yaml, index.html, hazır companies.yaml)
  VERI_KOK    -> kullanıcıya ait yazılabilir alan (profil, veritabanı, çıktılar)
                 paketlenmişse ~/is-basvuru-bot, kaynaktan çalışıyorsa proje dizini
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

PAKETLI = getattr(sys, "frozen", False)


def kaynak_kok() -> Path:
    """Paket içi salt-okunur veri kökü."""
    if PAKETLI:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def veri_kok() -> Path:
    """Yazılabilir kullanıcı alanı."""
    if PAKETLI:
        k = Path.home() / "is-basvuru-bot"
        k.mkdir(parents=True, exist_ok=True)
        return k
    return Path.cwd()


def kaynak_dosya(*parca: str) -> Path:
    return kaynak_kok().joinpath(*parca)


def veri_dosya(*parca: str) -> Path:
    y = veri_kok().joinpath(*parca)
    y.parent.mkdir(parents=True, exist_ok=True)
    return y


def ilk_kurulum() -> list[str]:
    """Paketlenmiş uygulamanın ilk açılışında hazır ayar dosyalarını
    kullanıcı alanına kopyalar. Var olanların üstüne YAZMAZ."""
    kopyalanan = []
    for ad in ("companies.yaml",):
        hedef = veri_kok() / "config" / ad
        kaynak = kaynak_dosya("config", ad)
        if not hedef.exists() and kaynak.exists():
            hedef.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(kaynak, hedef)
            kopyalanan.append(str(hedef))
    for ad in ("out", "data"):
        (veri_kok() / ad).mkdir(parents=True, exist_ok=True)
    return kopyalanan


# Uygulamanın çalışması için pakette BULUNMASI ZORUNLU veri dosyaları.
# Eksik biri sessiz arızaya yol açıyordu (roller.yaml pakete girmemişti ve
# rol aileleri + profil tazeleme çalışmıyordu, kimse fark etmedi).
ZORUNLU_VERI = [
    ("isbot", "data", "skills.yaml"),
    ("isbot", "data", "roller.yaml"),
    ("isbot", "web", "index.html"),
]


def oz_denetim() -> list[str]:
    """Eksik paket verilerinin listesini döndürür. Boş liste = her şey yerinde."""
    return [str(kaynak_dosya(*p)) for p in ZORUNLU_VERI if not kaynak_dosya(*p).exists()]
