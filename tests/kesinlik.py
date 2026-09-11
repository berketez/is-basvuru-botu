#!/usr/bin/env python3
"""KESİNLİK ölçümü: her CV için ilk N sonucun kaçı gerçekten o CV'nin alanında?

Ölçüt, motorun kendi sinyalini kullanır: bir ilan "alan içi" sayılır ancak ve ancak
BAŞLIĞI, o CV'den türetilen rol ailelerinden birinin kalıbına uyuyorsa. Yetenek
örtüşmesiyle gelen ama başlığı tutmayan ilanlar "alan dışı"dır.

Hedef: ilk 10'da alan dışı = 0. Az sonuç kabul edilir; alakasız sonuç kabul edilmez.
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from isbot.cv_import import profil_uret
from isbot.ghost import degerlendir
from isbot.pipeline import idf_hesapla, tekilleştir
from isbot.scoring import puanla

KOK = Path(__file__).resolve().parent.parent
ONBELLEK = KOK / "data" / "benchmark-havuz.pkl"
UST = 10


def main() -> int:
    if not ONBELLEK.exists():
        print("havuz önbelleği yok — önce tests/benchmark.py --yenile koş")
        return 1
    ilanlar = tekilleştir(pickle.loads(ONBELLEK.read_bytes()))
    print(f"havuz: {len(ilanlar)} tekil ilan\n")
    print(f"{'CV':26} {'sonuç':>6} {'ilk10':>6} {'alan dışı':>10}  ilk 3 başlık")
    print("=" * 118)

    toplam_disi = 0
    detay: list[str] = []
    for f in sorted(KOK.glob("test-cvs/*.txt"),
                    key=lambda x: int(x.name.split("_")[0])):
        p = profil_uret(f)
        p["sert_filtreler"]["zorunlu_konum_kosulu"] = ["turkey", "remote_global", "remote_emea"]
        idf = idf_hesapla(ilanlar, p)
        son = []
        for j in ilanlar:
            pu = puanla(j, p, idf)
            if pu.elendi:
                continue
            h = degerlendir(j)
            if h.risk >= 0.70:
                continue
            son.append((round(pu.toplam * (1 - 0.75 * h.risk), 1), j, pu))
        son.sort(key=lambda x: -x[0])
        ilk = son[:UST]
        disi = [(j.title, pu.rol_ailesi) for _, j, pu in ilk if pu.alan_disi]
        toplam_disi += len(disi)
        basliklar = " | ".join(j.title[:26] for _, j, _ in ilk[:3]) or "—"
        isaret = "" if not disi else "  <-- SORUN"
        print(f"{f.stem[:25]:26} {len(son):6} {len(ilk):6} {len(disi):10}  {basliklar[:52]}{isaret}")
        for t, rol in disi[:3]:
            detay.append(f"    {f.stem[:22]:24} ALAN DIŞI: {t[:52]:54} (rol: {rol})")

    print("=" * 118)
    print(f"TOPLAM alan dışı (ilk {UST}): {toplam_disi}   — hedef 0")
    if detay:
        print("\nayrıntı:")
        for d in detay:
            print(d)
    return 1 if toplam_disi else 0


if __name__ == "__main__":
    sys.exit(main())
