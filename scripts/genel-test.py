#!/usr/bin/env python3
"""Genellik testi: TEK ilan havuzu, ÇOK profil.

Amaç: motorun kişiye özel olmadığını kanıtlamak. Aynı ilan havuzu farklı CV'lere
karşı puanlanır; her profil kendi alanından farklı kısa liste almalı.

İlan havuzu bir kez çekilip diske önbelleklenir (API'lere nazik + tekrar koşum hızlı).
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from isbot.cv_import import profil_uret
from isbot.ghost import degerlendir
from isbot.scoring import puanla
from isbot.sources import KAYNAKLAR

ONBELLEK = Path("data/havuz.pkl")


def havuz_al(yenile: bool = False) -> list:
    if ONBELLEK.exists() and not yenile:
        yas = (time.time() - ONBELLEK.stat().st_mtime) / 3600
        if yas < 12:
            ilanlar = pickle.loads(ONBELLEK.read_bytes())
            print(f"önbellekten: {len(ilanlar)} ilan ({yas:.1f} saat önce çekilmiş)")
            return ilanlar

    sirketler = yaml.safe_load(open("config/companies.yaml", encoding="utf-8"))
    ilanlar, hata = [], 0
    for kaynak_adi, kalemler in sirketler.items():
        if kaynak_adi not in KAYNAKLAR or not kalemler:
            continue
        kaynak = KAYNAKLAR[kaynak_adi]()
        for token, ad in kalemler.items():
            try:
                yeni = kaynak.cek(token, ad)
                ilanlar += yeni
                print(f"  {ad:14} {len(yeni):4} ilan", flush=True)
            except Exception as e:
                hata += 1
                print(f"  {ad:14} HATA {type(e).__name__}", flush=True)
            time.sleep(0.4)          # nazik ol
    ONBELLEK.parent.mkdir(exist_ok=True, parents=True)
    ONBELLEK.write_bytes(pickle.dumps(ilanlar))
    print(f"\nTOPLAM {len(ilanlar)} ilan çekildi ({hata} şirket hata verdi)")
    return ilanlar


def profilleri_hazirla() -> dict:
    """5 sahte CV + Berke. Sahte CV'lerde cv-import 'GÖZDEN GEÇİR' dediği konum
    alanını, gerçek kullanıcının yapacağı gibi elle dolduruyoruz (simülasyon)."""
    elle_konum = {
        "2_staff_ml":          (["remote_global", "usa"], "ABD, remote-global bakıyor"),
        "4_devops_sre":        (["remote_global", "remote_emea"], "remote-worldwide"),
        "5_security_pentester": (["remote_global", "remote_emea"], "remote EMEA"),
    }
    profiller = {}
    for f in sorted(Path("test-cvs").glob("*.txt")):
        ad = f.stem
        p = profil_uret(f)
        if ad in elle_konum:
            izin, not_ = elle_konum[ad]
            p["sert_filtreler"]["zorunlu_konum_kosulu"] = izin
            p["kimlik"]["calisma_izni"] = izin
            p["_elle_duzeltme"] = not_
        profiller[ad] = p
    profiller["0_BERKE(gercek)"] = yaml.safe_load(open("config/profile.local.yaml", encoding="utf-8"))
    return profiller


def main() -> int:
    ilanlar = havuz_al("--yenile" in sys.argv)
    profiller = profilleri_hazirla()
    ozet = {}

    for ad, profil in sorted(profiller.items()):
        sonuclar = []
        elenen = 0
        for j in ilanlar:
            p = puanla(j, profil)
            if p.elendi:
                elenen += 1
                continue
            h = degerlendir(j)
            if h.risk >= 0.70:
                continue
            nihai = round(p.toplam * (1 - 0.75 * h.risk), 1)
            if nihai >= 20:
                sonuclar.append((nihai, j, p, h))
        sonuclar.sort(key=lambda x: -x[0])
        ozet[ad] = (len(sonuclar), elenen)

        print(f"\n{'='*92}\n### {ad}   →   {len(sonuclar)} aday  ({elenen} elendi)")
        if profil.get("_elle_duzeltme"):
            print(f"    [konum elle düzeltildi: {profil['_elle_duzeltme']}]")
        if not sonuclar:
            print("    (eşiği geçen ilan yok)")
            continue
        for nihai, j, p, h in sonuclar[:5]:
            yas = f"{h.yas_gun:.0f}g" if h.yas_gun is not None else "?"
            print(f"  {nihai:5.1f}  {j.company:12} {j.title[:52]:54} {yas:>6} {h.bant}")
            print(f"         rol={p.rol_ailesi[:26]:28} yetenek: {', '.join(p.eslesen_yetenekler[:7])}")

    print(f"\n{'='*92}\nÖZET (aynı {len(ilanlar)} ilanlık havuz, farklı profiller):")
    for ad, (n, e) in sorted(ozet.items()):
        print(f"  {ad:26} {n:4} aday   {e:5} elendi")
    json.dump({k: v[0] for k, v in ozet.items()}, open("out/genel-test-ozet.json", "w"), indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
