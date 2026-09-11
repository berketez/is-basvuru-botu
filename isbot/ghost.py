"""Tazelik + hayalet ilan tespiti.

DÜRÜST SINIR: Hayalet ilan tespiti kesin bir bilim değil. Sinyaller iki gruba ayrılır:

  ANINDA (ilk koşuda çalışır)
    - ilan yaşı (posted_at)          ← en güçlü tekil sinyal
    - "evergreen" başlık/metin kalıpları (yetenek havuzu, genel başvuru...)
    - konum enflasyonu, şirket içi başlık tekrarı, tarih alanının hiç olmaması

  ZAMANLA (en az 2 koşu, gerçek güç 2-3 hafta sonra)
    - sahte tazeleme: updated_at ilerledi ama içerik bit bit aynı
    - yeniden yayım: aynı başlık yeni kimlikle tekrar açıldı
    - hiç kapanmama: aylardır aynı ilan duruyor

Yani ilk koşuda skor "yaş + kalıp" ağırlıklıdır ve zayıftır; bot her koştuğunda
veritabanı büyüdükçe tespit keskinleşir. Bunu abartıp "hayaleti kesin buluyorum"
demiyoruz — skor bir risk göstergesi, yargı değil.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Job

# --- "evergreen" / havuz ilanı kalıpları (başlıkta) ---
HAVUZ_BASLIK = re.compile(
    r"(?i)\b(general application|talent (pool|community|network)|future opportunit|"
    r"speculative|expression of interest|open application|we'?re always|evergreen|"
    r"pipeline|genel ba[sş]vuru|yetenek havuzu|aday havuzu)\b"
)
# --- metinde geçen havuz ifadeleri ---
HAVUZ_METIN = re.compile(
    r"(?i)(no specific (opening|role)|on an ongoing basis|for future openings|"
    r"keep your (cv|resume) on file|when a (suitable )?position becomes available|"
    r"always accepting applications)"
)

BANT = [(0.70, "hayalet"), (0.45, "şüpheli"), (0.20, "normal"), (0.0, "taze")]


@dataclass
class HayaletSonuc:
    risk: float                      # 0..1
    bant: str                        # taze | normal | şüpheli | hayalet
    yas_gun: float | None
    gerekceler: list[str] = field(default_factory=list)
    kanit_gucu: str = "zayıf"        # zayıf (tek koşu) | orta | güçlü (geçmiş var)

    @property
    def temiz_mi(self) -> bool:
        return self.bant in ("taze", "normal")


def _bant(risk: float) -> str:
    for esik, ad in BANT:
        if risk >= esik:
            return ad
    return "taze"


def degerlendir(
    job: Job,
    *,
    gecmis: dict | None = None,        # Depo.kaydet() çıktısı
    yeniden_yayim: int = 0,
    sirket_ayni_baslik: int = 0,
    max_yas_gun: float = 120.0,        # bu yaşın üstü "bayat" sayılır
) -> HayaletSonuc:
    gecmis = gecmis or {}
    risk = 0.0
    ger: list[str] = []

    # 1) YAŞ — en güçlü anlık sinyal
    yas = job.age_days
    if yas is None:
        risk += 0.25
        ger.append("ilanda yayın tarihi yok (ATS gizliyor) — tazelik doğrulanamıyor")
    elif yas > 1095:
        risk += 0.85
        ger.append(f"{yas/365:.1f} YILDIR açık ({yas:.0f} gün) — kalıcı vitrin ilanı")
    elif yas > 730:
        risk += 0.70
        ger.append(f"{yas/365:.1f} yıldır açık ({yas:.0f} gün) — 2 yıldan eski, kadro gerçek değil")
    elif yas > 365:
        risk += 0.50
        ger.append(f"{yas/365:.1f} yıldır açık ({yas:.0f} gün) — neredeyse kesin havuz/hayalet")
    elif yas > 180:
        risk += 0.35
        ger.append(f"{yas:.0f} gündür açık (6 aydan fazla)")
    elif yas > max_yas_gun:
        risk += 0.20
        ger.append(f"{yas:.0f} gündür açık (bayat sayılır)")
    elif yas <= 14:
        risk -= 0.10
        ger.append(f"yeni yayımlanmış ({yas:.0f} gün)")

    # 2) HAVUZ İLANI KALIPLARI
    if HAVUZ_BASLIK.search(job.title):
        risk += 0.45
        ger.append("başlık bir havuz/genel başvuru ilanı ('talent pool' vb.)")
    if HAVUZ_METIN.search(job.description[:4000]):
        risk += 0.25
        ger.append("metin 'ileride açılacak pozisyonlar için' diyor — somut açık kadro yok")

    # 3) KONUM ENFLASYONU — 10+ konumlu ilan çoğu zaman gerçek tek kadro değil
    if len(job.locations) >= 10:
        risk += 0.15
        ger.append(f"{len(job.locations)} farklı konum listelenmiş — toplayıcı ilan olabilir")

    # 4) ŞİRKET İÇİ BAŞLIK TEKRARI
    if sirket_ayni_baslik >= 3:
        risk += 0.10
        ger.append(f"aynı şirkette bu başlıktan {sirket_ayni_baslik} adet açık")

    # --- ZAMANA DAYALI SİNYALLER (geçmiş varsa) ---
    kanit = "zayıf"
    if gecmis.get("gorulme_sayisi", 1) > 1:
        kanit = "orta"

    if gecmis.get("sahte_tazeleme"):
        risk += 0.35
        kanit = "güçlü"
        ger.append("SAHTE TAZELEME: güncelleme tarihi ilerledi ama ilan metni harfi harfine aynı")

    if yeniden_yayim > 0:
        risk += min(0.15 * yeniden_yayim, 0.35)
        kanit = "güçlü"
        ger.append(f"aynı başlık daha önce {yeniden_yayim} kez kapanıp yeniden açılmış (döngü)")

    risk = max(0.0, min(1.0, risk))
    return HayaletSonuc(risk=risk, bant=_bant(risk), yas_gun=yas, gerekceler=ger, kanit_gucu=kanit)
