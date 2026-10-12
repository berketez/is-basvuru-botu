#!/usr/bin/env python3
"""Kısa liste ölçümü: her CV'nin ilk N sonucu — ağa çıkmadan, istenen kod köküne karşı.

NEDEN: motor değişikliğinin etkisi tek CV'de değil, bütün meslek CV'lerinde görülmeli
(bkz. hafıza: meslekten bağımsız). Bu araç aynı ilan havuzunu iki kod sürümüyle
puanlar; `karsilastir` alt komutu farkı listeler. Önceki oturumlarda bu düzenek geçici
dizinde kalıp kaybolmuştu.

Havuz: data/benchmark-havuz.pkl (yabancı ATS, tests/benchmark.py üretir) + verilen
jobs.db'deki Türk pano ilanları (kariyer.net, eleman.net). CV'ler: tests/meslek-cvleri,
test-cvs ve --ek ile verilenler (gerçek CV'ler depoya GİRMEZ, yalnız yerelde verilir).

    # bugünkü kod
    python scripts/kisa_liste_olcum.py olc yeni.json --db ~/is-basvuru-bot/data/jobs.db
    # önceki sürüm: git worktree add --detach /tmp/eski HEAD~1
    ISBOT_KOK=/tmp/eski python scripts/kisa_liste_olcum.py olc eski.json --db ...
    python scripts/kisa_liste_olcum.py karsilastir eski.json yeni.json
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

PROJE = Path(__file__).resolve().parent.parent
KOK = Path(os.environ.get("ISBOT_KOK", PROJE))
sys.path.insert(0, str(KOK))

# Uygulayıcı seviye ilan başlığı: teknisyen olmayan CV'nin ilk 10'unda görülmemeli.
UYGULAYICI = re.compile(r"(?i)\b(operatör\w*|operator|usta\w*|işçi\w*|kaynakçı|technician|"
                        r"teknisyen\w*|tekniker\w*|üretim personeli|şoför\w*|kurye|forklift)\b")


def _t(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def tr_ilanlar(db_yolu: str) -> list:
    from isbot.models import Job
    db = sqlite3.connect(db_yolu)
    db.row_factory = sqlite3.Row
    cikti = []
    for r in db.execute("SELECT * FROM jobs WHERE source IN ('kariyernet','elemannet')"):
        j = Job(source=r["source"], company=r["company"], board_token=r["board_token"],
                native_id=r["native_id"], title=r["title"], url=r["url"] or "",
                locations=json.loads(r["locations"] or "[]"), description=r["description"] or "",
                department=r["department"] or "", posted_at=_t(r["posted_at"]),
                updated_at=_t(r["updated_at"]))
        j.raw["detay_cekildi"] = bool(j.description)
        cikti.append(j)
    return cikti


def olc(a) -> int:
    from isbot.cv_import import profil_uret
    from isbot.ghost import degerlendir
    from isbot.pipeline import Sonuc, idf_hesapla, tekilleştir
    from isbot.scoring import puanla

    havuz = pickle.loads((PROJE / "data" / "benchmark-havuz.pkl").read_bytes())
    if a.db:
        havuz += tr_ilanlar(os.path.expanduser(a.db))
    ilanlar = tekilleştir(havuz)
    cvler = sorted((PROJE / "tests" / "meslek-cvleri").glob("*.txt"))
    cvler += sorted((PROJE / "test-cvs").glob("*.txt"))
    cvler += [Path(os.path.expanduser(x)) for x in (a.ek or [])]
    sonuc, t0 = {}, time.time()
    for cv in cvler:
        p = profil_uret(cv)
        p["sert_filtreler"]["zorunlu_konum_kosulu"] = ["turkey", "remote_global", "remote_emea"]
        idf = idf_hesapla(ilanlar, p)
        son = []
        for j in ilanlar:
            pu = puanla(j, p, idf)
            if pu.elendi:
                continue
            h = degerlendir(j)
            if h.risk < 0.70:
                son.append(Sonuc(j, pu, h))
        son.sort(key=lambda s: -s.nihai)
        sonuc[cv.stem] = {
            "aileler": {k: v.get("agirlik") for k, v in p["rol_aileleri"].items()},
            "tr": p.get("tr_arama_sorgulari"), "en": p.get("arama_sorgulari"),
            "yil": p["kimlik"]["deneyim_yil"], "teknisyen": p["kimlik"].get("teknisyen"),
            "n": len(son),
            "ilk": [[s.nihai, s.job.title[:70], s.job.company[:25], s.puan.rol_ailesi,
                     s.job.source, len(s.puan.eslesen_yetenekler), bool(s.job.description)]
                    for s in son[:15]],
        }
    Path(a.cikti).write_text(json.dumps(sonuc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(sonuc)} CV, {len(ilanlar)} ilan, {time.time() - t0:.0f} sn -> {a.cikti}")
    return 0


def _metrik(d: dict, ortak: list[str]) -> tuple[int, int, int]:
    uygulayici = sum(1 for k in ortak if not d[k].get("teknisyen")
                     for r in d[k]["ilk"][:10] if UYGULAYICI.search(r[1]))
    bos = sum(1 for k in ortak for r in d[k]["ilk"][:10] if r[5] == 0 and r[6])
    dolu = sum(min(10, d[k]["n"]) for k in ortak)
    return uygulayici, bos, dolu


def karsilastir(a) -> int:
    e = json.loads(Path(a.eski).read_text(encoding="utf-8"))
    y = json.loads(Path(a.yeni).read_text(encoding="utf-8"))
    ortak = [k for k in e if k in y]
    for ad, d in (("eski", e), ("yeni", y)):
        u, b, n = _metrik(d, ortak)
        print(f"{ad}: uygulayıcı olmayanın ilk 10'unda uygulayıcı ilan {u} | metni olup "
              f"0 yetenekli {b} | dolu ilk-10 yuvası {n}")
    print(f"\n{'CV':28} {'n eski':>7} {'n yeni':>7}  ilk 10 farkı")
    for k in ortak:
        ea = [r[1] for r in e[k]["ilk"][:10]]
        eb = [r[1] for r in y[k]["ilk"][:10]]
        cik, gir = [t for t in ea if t not in eb], [t for t in eb if t not in ea]
        if cik or gir or e[k]["n"] != y[k]["n"]:
            print(f"{k[:28]:28} {e[k]['n']:7} {y[k]['n']:7}  -{len(cik)} +{len(gir)}")
            if a.ayrinti:
                for t in cik:
                    print(f"{'':30}- {t[:70]}")
                for t in gir:
                    print(f"{'':30}+ {t[:70]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    alt = ap.add_subparsers(dest="komut", required=True)
    o = alt.add_parser("olc")
    o.add_argument("cikti")
    o.add_argument("--db", help="Türk pano ilanları için jobs.db (ör. ~/is-basvuru-bot/data/jobs.db)")
    o.add_argument("--ek", nargs="*", help="ek CV yolları (yerel, depoya girmez)")
    k = alt.add_parser("karsilastir")
    k.add_argument("eski")
    k.add_argument("yeni")
    k.add_argument("--ayrinti", action="store_true", help="çıkan/giren başlıkları da yaz")
    a = ap.parse_args()
    return olc(a) if a.komut == "olc" else karsilastir(a)


if __name__ == "__main__":
    sys.exit(main())
