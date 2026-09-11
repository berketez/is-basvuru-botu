#!/usr/bin/env python3
"""15 CV'lik benchmark. İki katman:

  A) YAPISAL — CV ayrıştırma çıktısı elle yazılmış beklentiyle karşılaştırılır.
     Objektif, otomatik, CI'da koşar. Bugüne kadarki hataların çoğu bu katmanda
     yakalanırdı (10 yıllık yeni mezun, PDF'te bölünmüş yıl, 0 yetenek...).

  B) ALAKA — tek ilan havuzu her profile karşı puanlanır, ilk sonuçlar denetlenir:
     - kendi eleme kalıbına uyan başlık geçmiş mi (sızıntı)
     - konum uygunluğu bozuk mu
     - alan anahtar kelimeleri tutuyor mu
     - negatif kontroller (makine müh., ürün yön.) gerçekten az sonuç alıyor mu

Havuz bir kez çekilip önbelleklenir; 15 profil aynı havuza karşı puanlanır.
Kullanım:  python tests/benchmark.py [--yenile]
"""
from __future__ import annotations

import pickle
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from isbot.cv_import import profil_uret
from isbot.ghost import degerlendir
from isbot.pipeline import idf_hesapla, tekilleştir
from isbot.scoring import puanla
from isbot.sources import KAYNAKLAR, SORGU_KAYNAKLARI

KOK = Path(__file__).resolve().parent.parent
CV_DIZIN = KOK / "test-cvs"
ONBELLEK = KOK / "data" / "benchmark-havuz.pkl"
TOLERANS = 1.5          # deneyim yılı toleransı


def havuz(yenile: bool = False) -> list:
    if ONBELLEK.exists() and not yenile and (time.time() - ONBELLEK.stat().st_mtime) < 43200:
        j = pickle.loads(ONBELLEK.read_bytes())
        print(f"havuz önbellekten: {len(j)} ilan")
        return j
    sirketler = yaml.safe_load((KOK / "config" / "companies.yaml").read_text(encoding="utf-8"))
    ham = []
    for kad, kalemler in sirketler.items():
        if kad not in KAYNAKLAR or not kalemler:
            continue
        k = KAYNAKLAR[kad]()
        for token, ad in kalemler.items():
            try:
                ham += k.cek(token, ad)
            except Exception as e:
                print(f"  ! {kad}/{token}: {type(e).__name__}")
            time.sleep(0.3)
    for kad, K in SORGU_KAYNAKLARI.items():
        k = K()
        for s in (["machine learning", "python", "backend", "data", "security", "mobile",
                   "game", "blockchain", "qa", "embedded"] if kad != "remoteok" else [""]):
            try:
                ham += k.cek(s)
            except Exception as e:
                print(f"  ! {kad}/{s}: {type(e).__name__}")
    ONBELLEK.parent.mkdir(parents=True, exist_ok=True)
    ONBELLEK.write_bytes(pickle.dumps(ham))
    print(f"havuz çekildi: {len(ham)} ilan")
    return ham


def main() -> int:
    bek = yaml.safe_load((KOK / "tests" / "beklenen.yaml").read_text(encoding="utf-8"))
    ilanlar = tekilleştir(havuz("--yenile" in sys.argv))
    print(f"tekil havuz: {len(ilanlar)} ilan\n")

    gecti = basarisiz = 0
    satirlar = []

    print("=" * 104)
    print("A) YAPISAL — CV ayrıştırma")
    print("=" * 104)
    print(f"{'CV':26} {'deneyim':>16} {'kıdem':>14}  {'yetenek':>9}  {'y.pozitif':>9}")
    profiller = {}

    for ad, b in bek.items():
        dosya = CV_DIZIN / f"{ad}.txt"
        if not dosya.exists():
            print(f"{ad:26} DOSYA YOK"); basarisiz += 1; continue
        p = profil_uret(dosya)
        profiller[ad] = p
        yil = p["kimlik"]["deneyim_yil"]
        kid = p["sert_filtreler"]["max_kidem"]
        guclu = set(p["yetenekler"]["guclu"]) | set(p["yetenekler"]["zayif"])

        y_ok = abs(yil - b["deneyim"]) <= TOLERANS
        k_ok = kid == b["kidem"]
        eksik = [x for x in b["olmali"] if x not in guclu]
        yanlis = [x for x in b["olmamali"] if x in guclu]

        for kosul in (y_ok, k_ok, not eksik, not yanlis):
            if kosul: gecti += 1
            else: basarisiz += 1

        print(f"{ad:26} {yil:6.1f}/{b['deneyim']:<4.1f}{'  OK ' if y_ok else ' HATA'} "
              f"{kid:>9}{'  OK ' if k_ok else ' HATA'}  "
              f"{('OK' if not eksik else 'eksik:' + ','.join(eksik[:3])):>9}  "
              f"{('OK' if not yanlis else ','.join(yanlis[:3])):>9}")
        if eksik: satirlar.append(f"  {ad}: tespit edilmeyen yetenek -> {', '.join(eksik)}")
        if yanlis: satirlar.append(f"  {ad}: YANLIŞ POZİTİF yetenek -> {', '.join(yanlis)}")
        if not y_ok: satirlar.append(f"  {ad}: deneyim {yil} (beklenen {b['deneyim']}±{TOLERANS})")
        if not k_ok: satirlar.append(f"  {ad}: kıdem {kid} (beklenen {b['kidem']})")

    print("\n" + "=" * 104)
    print("B) ALAKA — aynı havuz, 15 profil")
    print("=" * 104)
    print(f"{'CV':26} {'aday':>5} {'ilk5 alan':>10} {'sızıntı':>8} {'konum':>7}   ilk sonuç")

    for ad, b in bek.items():
        p = profiller.get(ad)
        if not p:
            continue
        # Negatif kontroller dışında konum kısıtını gevşetiyoruz ki alaka ölçülebilsin;
        # konum mantığı A katmanında ve ayrı testlerde zaten sınanıyor.
        p["sert_filtreler"]["zorunlu_konum_kosulu"] = ["turkey", "remote_global", "remote_emea"]
        idf = idf_hesapla(ilanlar, p)
        kaliplar = p["sert_filtreler"]["yasakli_baslik_kaliplari"]

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
        ilk5 = son[:5]

        sizinti = [j.title for _, j, _ in ilk5 if any(re.search(k, j.title) for k in kaliplar)]
        konum_hata = [j.title for _, j, pu in ilk5 if "izin yok" in pu.konum_durumu]
        alan_tut = sum(1 for _, j, _ in ilk5
                       if any(a.lower() in (j.title + " " + j.department).lower() for a in b["alan"]))

        neg = b.get("negatif", False)
        neg_ok = (len(son) <= 12) if neg else True
        if neg and not neg_ok:
            satirlar.append(f"  {ad}: NEGATİF KONTROL BAŞARISIZ — {len(son)} aday (≤12 olmalı)")
        if sizinti:
            satirlar.append(f"  {ad}: SIZINTI (kendi eleme kalıbına uyan başlık geçti) -> {sizinti[0][:52]}")
        if konum_hata:
            satirlar.append(f"  {ad}: KONUM HATASI -> {konum_hata[0][:52]}")
        for kosul in (not sizinti, not konum_hata, neg_ok):
            if kosul: gecti += 1
            else: basarisiz += 1

        ilk = f"{ilk5[0][1].company[:13]} / {ilk5[0][1].title[:34]}" if ilk5 else "—"
        print(f"{ad:26} {len(son):5} {alan_tut:>7}/5 {len(sizinti):>8} {len(konum_hata):>7}   {ilk}")

    print("\n" + "=" * 104)
    print(f"SONUÇ: {gecti} geçti, {basarisiz} başarısız  "
          f"({100 * gecti / max(gecti + basarisiz, 1):.0f}% geçiş)")
    if satirlar:
        print("\nBULGULAR:")
        for s in dict.fromkeys(satirlar):
            print(s)
    return 1 if basarisiz else 0


if __name__ == "__main__":
    sys.exit(main())
