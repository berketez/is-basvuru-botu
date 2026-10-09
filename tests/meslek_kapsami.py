#!/usr/bin/env python3
"""Meslek kapsamı testi — motor yazılım DIŞI alanları da doğru okuyor mu?

NEDEN AYRI DOSYA: benchmark (tests/benchmark.py) 16 yazılım/mühendislik CV'siyle
ALAKA ölçüyor ve ilan havuzu gerektiriyor. Bu test ise yalnız AYRIŞTIRMAYI ölçer,
ağ istemez, saniyeler sürer: 38 sentetik CV (19 Türkçe + 19 İngilizce; mühendislik, teknisyenlik,
mimarlık, muhasebe, sağlık, hukuk, denizcilik, madencilik, tekstil, turizm,
bankacılık, İK, İSG, çevre, gıda, lojistik, eğitim, pazarlama) doğru rol ailesine gidiyor mu?

Türkçe CV'ler bilerek NFD (ayrıştırılmış Unicode) yazılmıştır — pdftotext gerçeği.
Normalizasyon kaldırılırsa bu testler anında kırmızıya döner.

CV'lerin tamamı UYDURMADIR; hiçbir gerçek kişiye ait bilgi içermez.

    python tests/meslek_kapsami.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from isbot.cv_import import profil_uret

CV_DIZIN = Path(__file__).resolve().parent / "meslek-cvleri"

# (dosya, beklenen rol ailesi, en az kaç güçlü yetenek, beklenen deneyim ±1.5 yıl)
# Beklentiler CV metni ELLE okunarak yazıldı, motor çıktısına bakılarak değil.
BEKLENEN = [
    ("tr_makine_muh",   "makine_tasarim",    4, 7.1),
    ("tr_insaat_muh",   "insaat",            5, 9.0),
    ("tr_muhasebe",     "muhasebe",          5, 9.9),
    ("tr_hemsire",      "saglik",            5, 8.1),
    ("tr_teknisyen",    "bakim_teknik",      5, 8.0),
    ("tr_lojistik",     "lojistik",          5, 7.9),
    ("tr_mimar",        "insaat",            3, 8.0),
    ("tr_ogretmen",     "egitim",            4, 9.8),
    ("en_mechanical",   "makine_tasarim",    5, 8.0),
    ("en_civil",        "insaat",            5, 10.0),
    ("en_accountant",   "muhasebe",          5, 10.9),
    ("en_nurse",        "saglik",            4, 9.1),
    ("en_technician",   "bakim_teknik",      4, 9.0),
    ("en_supply_chain", "lojistik",          5, 8.9),
    ("en_chemical",     "kimya",             4, 9.0),
    ("en_marketing",    "pazarlama",         5, 9.0),
    # --- ikinci grup: ilk grupta kapsanmayan alanlar ---
    ("tr_avukat",       "hukuk",             4, 8.9),
    ("tr_denizci",      "denizcilik",        3, 9.0),
    ("tr_maden",        "madencilik",        4, 10.0),
    ("tr_tekstil",      "tekstil",           5, 9.0),
    ("tr_otel",         "turizm",            5, 11.3),
    ("tr_bankaci",      "bankacilik",        5, 9.9),
    ("tr_ik",           "ik",                6, 9.0),
    ("tr_isg",          "isg",               5, 9.9),
    ("en_lawyer",       "hukuk",             5, 9.9),
    ("en_marine",       "denizcilik",        3, 10.0),
    ("en_mining",       "madencilik",        4, 11.0),
    ("en_hotel",        "turizm",            4, 11.3),
    ("en_banker",       "bankacilik",        5, 9.9),
    ("en_hr",           "ik",                5, 9.0),
    ("en_environmental","enerji_cevre",      4, 10.9),
    ("en_food",         "gida_tarim",        5, 10.0),
    # --- üçüncü grup: teknik servis (fabrika bakımı dışındaki teknisyen kolları) ---
    ("tr_servis_teknisyeni", "bakim_teknik",  6, 10.2),
    ("en_field_technician",  "bakim_teknik",  4, 11.2),
    # --- dördüncü grup: üretim operatörlüğü (operatör, tezgah, kaynak, paketleme) ---
    ("tr_uretim_elemani",    "uretim_operator", 5, 11.7),
    ("en_cnc_machinist",     "uretim_operator", 5, 12.1),
    # --- beşinci grup: müşteri hizmetleri / çağrı merkezi ---
    ("tr_cagri_merkezi",     "musteri_hizmetleri", 4, 9.6),
    ("en_customer_service",  "musteri_hizmetleri", 4, 11.1),
]

# Hiçbir CV'de çıkmaması gereken yetenekler. "C"/"Go"/"R" Unicode NFD hatasının
# imzasıdır: Türkçe "Gömülü/Çift/sensör" içinden sahte dil çıkarsa buradan görülür.
YASAK = ("Go", "C", "R", "Solidity", "Unity", "PyTorch")

TOLERANS = 1.5


def main() -> int:
    gecti = basarisiz = 0
    hatalar: list[str] = []
    print(f"{'CV':18} {'yıl':>6} {'yetenek':>8}  {'beklenen rol':20} sonuç")
    print("-" * 74)
    for ad, bek_rol, en_az_yetenek, bek_yil in BEKLENEN:
        yol = CV_DIZIN / f"{ad}.txt"
        if not yol.exists():
            hatalar.append(f"{ad}: CV dosyası yok ({yol})")
            basarisiz += 1
            continue
        p = profil_uret(yol)
        roller = list(p["rol_aileleri"])
        guclu = p["yetenekler"]["guclu"]
        yil = p["kimlik"]["deneyim_yil"]

        sorun = []
        if bek_rol not in roller[:3]:
            sorun.append(f"rol '{bek_rol}' ilk 3'te yok -> {roller[:3]}")
        if len(guclu) < en_az_yetenek:
            sorun.append(f"yetenek az: {len(guclu)} < {en_az_yetenek}")
        if abs(yil - bek_yil) > TOLERANS:
            sorun.append(f"deneyim {yil} != {bek_yil} (±{TOLERANS})")
        kacak = [y for y in YASAK if y in guclu]
        if kacak:
            sorun.append(f"SAHTE yetenek: {kacak}")

        if sorun:
            basarisiz += 1
            hatalar.append(f"{ad}: " + "; ".join(sorun))
        else:
            gecti += 1
        print(f"{ad:18} {yil:6} {len(guclu):8}  {bek_rol:20} {'OK' if not sorun else 'BAŞARISIZ'}")

    print("-" * 74)
    print(f"{gecti} geçti, {basarisiz} başarısız")
    if hatalar:
        print("\nBAŞARISIZ:")
        for h in hatalar:
            print("  " + h)
    return 1 if basarisiz else 0


if __name__ == "__main__":
    sys.exit(main())
