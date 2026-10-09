#!/usr/bin/env python3
"""Türkiye meslek kapsamı: kariyer.net pozisyonlarının kaçı bir rol ailesine giriyor?

Amaç: rol ailelerinin (isbot/data/roller.yaml) Türkiye iş piyasasını ne kadar
kapsadığını TAHMİNLE değil veriyle görmek ve yeni aile/kalıp eklerken neyin eksik
olduğunu sıralı listelemek. Ağ istemez: kariyer.net site haritasının önbelleğini okur
(data/kariyernet-sitemap.json, tarama sırasında 7 günde bir tazelenir).

Site haritası yolları "il-ilçe-pozisyon" biçimindedir; son parça pozisyondur. Bir
pozisyonun kaç ilde ayrı sayfası olduğu, yaygınlığının vekilidir. En az 3 ilde
açılmış pozisyonlar sayılır (tek ilçeli tuhaf yollar elenir).

Ölçüldü (2026-10-08, v1.5.5): 2.858 pozisyonun %34'ü (il sayısıyla ağırlıklı %46)
bir aileye giriyor. Boşluk ağırlıkla mavi yaka ve hizmet tarafında.
v1.5.7 (2026-10-09, var olan ailelere Türkçe unvanlar): %40 (ağırlıklı %58).

    python scripts/tr_kapsam.py [--ilk 70]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parent.parent
TR_ASCII = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a",
                          "î": "i", "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u"})
EN_AZ_IL = 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ilk", type=int, default=70, help="listelenecek boşluk sayısı")
    ap.add_argument("--harita", default=str(KOK / "data" / "kariyernet-sitemap.json"))
    a = ap.parse_args()

    harita = Path(a.harita)
    if not harita.exists():
        print(f"site haritası önbelleği yok: {harita} — önce bir tarama koş")
        return 1
    yollar = json.loads(harita.read_text(encoding="utf-8"))
    roller = yaml.safe_load((KOK / "isbot" / "data" / "roller.yaml").read_text(encoding="utf-8"))
    # Yollar ASCII yazılı ("makine+muhendisi"); kalıplar Türkçe harfli. Kalıp katlanır.
    kalip = {ad: [re.compile(k.translate(TR_ASCII)) for k in t["basliklar"]]
             for ad, t in roller.items()}

    sayac = collections.Counter(y.rsplit("/", 1)[-1].split("-")[-1].replace("+", " ")
                                for y in yollar)
    poz = {p: n for p, n in sayac.items() if n >= EN_AZ_IL and " " in p}
    aile = {p: [ad for ad, ks in kalip.items() if any(k.search(p) for k in ks)] for p in poz}

    agirlikli = sum(n for p, n in poz.items() if aile[p]) / max(1, sum(poz.values()))
    sade = sum(1 for p in poz if aile[p]) / max(1, len(poz))
    print(f"pozisyon (≥{EN_AZ_IL} ilde): {len(poz)} | kapsam: %{100 * sade:.0f} "
          f"(il sayısıyla ağırlıklı %{100 * agirlikli:.0f})\n")

    bos = sorted(((n, p) for p, n in poz.items() if not aile[p]), reverse=True)
    print(f"HİÇBİR AİLEYE GİRMEYEN en yaygın {a.ilk} pozisyon (il sayısı):")
    for n, p in bos[:a.ilk]:
        print(f"  {n:4}  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
