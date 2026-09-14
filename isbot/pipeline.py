"""Tarama hattı: ilanları çek → geçmişe yaz → hayalet skorla → CV'ye göre puanla → sırala."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import concurrent.futures as cf
import math
import re
import time

from dataclasses import dataclass, field

import yaml

from .ghost import HayaletSonuc, degerlendir
from .models import Job
from .scoring import ULKELER, Puan, puanla
from .sources import (AKIS_KAYNAKLARI, KAYNAKLAR, SORGU_KAYNAKLARI, TR_KAYNAKLARI,
                      KaynakHatasi)
from .store import Depo

# Eşzamanlı istek sayısı — nazik kalmak için düşük.
IS_PARCACIGI = 6


@dataclass
class Sonuc:
    job: Job
    puan: Puan
    hayalet: HayaletSonuc

    @property
    def nihai(self) -> float:
        """Uygunluk puanı, hayalet riskiyle cezalandırılır.
        Hayalet ilana başvurmak zaman israfı; skorun tamamını silmek yerine
        riskle orantılı kısıyoruz ki 'belki gerçektir' ilan tamamen kaybolmasın."""
        taban = self.puan.toplam * (1.0 - 0.75 * self.hayalet.risk)
        u = self.puan.uyum
        if u is not None:
            # UYUM DÜZELTMESİ dar tutulur (±%18). Model ELEMEZ, yalnız sıralamayı
            # düzeltir — kendisi de yanılabiliyor (ölçümde bir pazarlama ilanına
            # pozitif skor verdi). Ölçülen kontrast aralığı ±0,04 olduğu için
            # 4,5 ile ölçeklenip bu banda oturtulur.
            taban *= max(0.82, min(1.18, 1.0 + 4.5 * u))
        return round(taban, 1)


@dataclass
class TaramaRaporu:
    sonuclar: list[Sonuc] = field(default_factory=list)
    cekilen: int = 0
    elenen: int = 0
    hayalet_elenen: int = 0
    hatalar: list[str] = field(default_factory=list)
    kapanan: int = 0
    uyum_denetlenen: int = 0
    tekrar_atilan: int = 0
    tr_detay_cekilen: int = 0
    eleme_dagilimi: dict = field(default_factory=dict)


def idf_hesapla(ilanlar: list[Job], profil: dict, ornek: int = 1500) -> dict[str, float]:
    """Yeteneklerin AYIRT EDİCİLİĞİ. Havuzun %30'unda geçen 'Python' ile %0,1'inde
    geçen 'Ghidra' aynı puanı getirmemeli; yoksa herkes her ilana uyar.

    ağırlık = ln(1 / oran), [0.3, 4.0] aralığına sıkıştırılır.
    """
    from .scoring import _yetenek_ara
    yet = profil.get("yetenekler", {})
    adlar = list((yet.get("guclu") or {})) + list((yet.get("zayif") or {}))
    if not ilanlar or not adlar:
        return {}
    n = min(len(ilanlar), ornek)
    adim = max(1, len(ilanlar) // n)
    metinler = [j.text for j in ilanlar[::adim]][:n]
    idf: dict[str, float] = {}
    for ad in adlar:
        gecen = sum(1 for m in metinler if _yetenek_ara(m, ad))
        oran = max(gecen / len(metinler), 1.0 / (len(metinler) * 4))
        idf[ad] = round(min(max(math.log(1.0 / oran), 0.3), 4.0), 2)
    return idf


# Başlığın sonuna eklenen ülke/şehir eki: "... - Germany", "... (Netherlands)".
# Bunlar AYNI ilanın ülke varyantıdır; ayrı sayılırsa kısa liste şişer
# (ölçüldü: ElevenLabs'ın tek ilanı 8 satır olarak görünüyordu).
# Ülke adları scoring.ULKELER kataloğundan TÜRETİLİR. Burada ikinci bir elle
# yazılmış liste durursa katalog büyüdükçe ikisi ayrışır: kataloğa eklenen ülkenin
# başlık varyantı tekilleştirilmez ve aynı ilan listede birkaç satır görünür.
# "us" bilerek dışarıda: "... - Us" diye biten başlık yok, ama "US" kısaltması
# başlık ortasında sık geçiyor ve yanlış kırpma riski taşıyor.
_ULKE_SOZCUKLERI = sorted(
    {t for _, _, _, takma in ULKELER for t in takma if len(t) >= 2 and t != "us"}
    | {"emea", "europe", "apac", "latam", "remote", "worldwide", "global", "anywhere"},
    key=len, reverse=True)
_ULKE_EKI = re.compile(
    r"(?i)[\s\-–—(,|/]+(" + "|".join(re.escape(a) for a in _ULKE_SOZCUKLERI) + r")\)?\s*$")

# Ayraç sınıfına "|" ve "/" DAHİL olmak zorunda: ülke başlığın sonunda değil ORTASINDA
# olabiliyor — "Senior Backend Engineer - Databases Pyroscope | Germany | Remote".
# Eksikken zincir bir adımda kırılıyordu ve Grafana'nın tek ilanı 5 satır görünüyordu.


def _varyant_anahtari(j: Job) -> str:
    t = j.title
    for _ in range(3):                      # "- Software Engineer - Germany" gibi zincirler
        yeni = _ULKE_EKI.sub("", t).strip(" -–—(,|/")
        if yeni == t:
            break
        t = yeni
    # Anahtar ŞİRKET ADI ile kurulur, board_token ile DEĞİL. İki sebep:
    #  1) Aynı şirket iki ATS'te birden ilan verebiliyor (Dream Games: greenhouse + lever).
    #  2) Toplayıcılarda aynı ilan farklı arama sorgularıyla gelince token değişiyor
    #     ("remotive:qa" vs "remotive:game") ve aynı ilan 3 kez listeye giriyordu.
    sirket = re.sub(r"[^a-z0-9]+", "", j.company.lower())
    return f"{sirket}|{re.sub(r'[^a-z0-9+#]+', ' ', t.lower()).strip()}"


def tekilleştir(ilanlar: list[Job]) -> list[Job]:
    """Aynı ilan birden çok kayıtla gelir (çok konumlu ilanlar ayrı kimlik alır,
    ülke varyantları ayrı başlık taşır). Şirket + çıplak başlık başına en TAZE olanı tutuyoruz."""
    en_iyi: dict[str, Job] = {}
    for j in ilanlar:
        k = _varyant_anahtari(j)
        v = en_iyi.get(k)
        if v is None:
            en_iyi[k] = j
            continue
        # HANGİ KOPYA TUTULUR: en TAZE değil, en ZENGİN METİNLİ olan.
        # Aynı ilan iki ATS'te birden durabiliyor ve biri kısaltılmış metin veriyor.
        # Ölçüldü: Dream Games'in "AI Engineer" ilanı Lever'da 737, Greenhouse'ta 2075
        # karakter. Kısa kopya seçilince Python/LLM/RAG yetenekleri görünmedi ve ilan
        # "hiçbir yetenek eşleşmedi" diye işaretlendi — halbuki hepsi ilanda yazıyordu.
        nj, nv = len(j.description), len(v.description)
        if nj > nv * 1.2:                      # belirgin şekilde daha zengin metin
            en_iyi[k] = j
            continue
        if nv > nj * 1.2:                      # mevcut kopya daha zengin, koru
            continue
        yj = j.age_days if j.age_days is not None else 9e9
        yv = v.age_days if v.age_days is not None else 9e9
        if yj < yv or (yj == yv and len(j.locations) > len(v.locations)):
            en_iyi[k] = j
    return list(en_iyi.values())


def yukle(yol: str) -> dict:
    with open(yol, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def tara(
    profil_yolu: str = "config/profile.local.yaml",
    sirket_yolu: str = "config/companies.yaml",
    db_yolu: str = "data/jobs.db",
    *,
    min_puan: float = 25.0,
    hayalet_esigi: float = 0.70,
    tr_detay_siniri: int = 30,
    gelismis: bool = False,
    ilerleme=None,
    asama_bildir=None,
) -> TaramaRaporu:
    def _asama(ad: str) -> None:
        """Hangi aşamadayız. Çekim bitip puanlama başlayınca arayüz 'ilanlar
        çekiliyor' yazısında donuyordu; kullanıcı taramanın takıldığını sanıyordu."""
        if asama_bildir:
            asama_bildir(ad)

    _asama("ilanlar çekiliyor")
    profil = yukle(profil_yolu)
    sirketler = yukle(sirket_yolu)
    depo = Depo(db_yolu)
    run_id = depo.kosu_baslat(f"profil={profil_yolu}")
    rapor = TaramaRaporu()
    tokenlar: list[str] = []

    # 1) ÇEK — tüm havuz, PARALEL.
    #
    # Sıralı çekim 73 şirkette 3+ dakika sürüyordu. Paralelleştirme kaynak başına
    # değil İSTEK başına yapılır; her iş parçacığı KENDİ oturumunu açar çünkü
    # requests.Session iş parçacıkları arasında paylaşılmaya uygun değildir.
    #
    # Eşzamanlılık bilinçli olarak düşük tutuluyor (IS_PARCACIGI): 38 şirket aynı
    # sunucuyu (boards-api.greenhouse.io) paylaşıyor; nazik davranmak istiyoruz.
    # 429 alınırsa taban sınıftaki geri çekilme devreye giriyor.
    isler: list[tuple[str, str, str]] = []
    for kaynak_adi, kalemler in sirketler.items():
        if kaynak_adi not in KAYNAKLAR or not kalemler:
            continue
        for token, sirket_adi in kalemler.items():
            isler.append((kaynak_adi, token, sirket_adi))

    sorgular = profil.get("arama_sorgulari") or []
    for kaynak_adi in SORGU_KAYNAKLARI:          # arama terimi başına bir istek
        for sorgu in sorgular:
            isler.append((kaynak_adi, sorgu, ""))
    for kaynak_adi in AKIS_KAYNAKLARI:           # tüm akış, sorgu almaz
        isler.append((kaynak_adi, "", ""))

    # Türk panoları: Türkçe pozisyon sorgusu + isteğe bağlı şehir ("pozisyon@şehir").
    # Bunlar kendi içlerinde hız sınırlı olduğu için paralel havuzda ayrı iş olarak
    # gitmeleri sorun değil; her biri kendi sınırını uygular.
    tr_sorgular = profil.get("tr_arama_sorgulari") or []
    sehirler = profil.get("tr_sehirler") or [""]
    for kaynak_adi in TR_KAYNAKLARI:
        if kaynak_adi == "elemannet":            # eleman.net sorgu almıyor, tek akış
            isler.append((kaynak_adi, "", ""))
            continue
        for sorgu in tr_sorgular:
            for sehir in sehirler:
                isler.append((kaynak_adi, f"{sorgu}@{sehir}" if sehir else sorgu, ""))

    ham: list[Job] = []

    def cek_tek(is_: tuple[str, str, str]) -> tuple[str, str, str, list[Job], str | None]:
        kaynak_adi, anahtar, ad = is_
        try:
            K = (KAYNAKLAR.get(kaynak_adi) or SORGU_KAYNAKLARI.get(kaynak_adi)
                 or AKIS_KAYNAKLARI.get(kaynak_adi) or TR_KAYNAKLARI[kaynak_adi])
            return (kaynak_adi, anahtar, ad or anahtar, K().cek(anahtar, ad), None)
        except Exception as e:
            return (kaynak_adi, anahtar, ad or anahtar, [], f"{type(e).__name__}: {str(e)[:60]}")

    with cf.ThreadPoolExecutor(max_workers=IS_PARCACIGI) as havuz_ip:
        for kaynak_adi, anahtar, ad, ilanlar, hata in havuz_ip.map(cek_tek, isler):
            if hata:
                rapor.hatalar.append(f"{kaynak_adi}/{ad}: {hata}")
                continue
            if kaynak_adi in KAYNAKLAR:
                # ATS ANAHTARI eklenir, şirketin okunur adı değil: kapanan ilan sorgusu
                # jobs.board_token ile eşleşir. Eskiden buraya "Databricks" yazılıyordu,
                # tabloda ise "databricks" duruyordu — hiçbir satır eşleşmiyor, dolayısıyla
                # "kapandı" işaretlemesi ve ona dayanan yeniden-yayım sinyali ölü kalıyordu.
                tokenlar.append(anahtar)
            ham += ilanlar
            if ilerleme:
                ilerleme(f"{ad or kaynak_adi}", len(ilanlar))

    rapor.cekilen = len(ham)
    _asama("tekrarlar ayıklanıyor")
    havuz = tekilleştir(ham)
    rapor.tekrar_atilan = len(ham) - len(havuz)
    idf = idf_hesapla(havuz, profil)

    # 2) PUANLA
    _asama(f"{len(havuz)} ilan CV'ye göre puanlanıyor")
    ayni_baslik: dict[str, int] = {}
    for j in havuz:
        ayni_baslik[j.title_key] = ayni_baslik.get(j.title_key, 0) + 1

    for job in havuz:
        gecmis = depo.kaydet(job, run_id)
        p = puanla(job, profil, idf)
        if p.elendi:
            rapor.elenen += 1
            rapor.eleme_dagilimi[p.eleme_sebebi.split("(")[0].strip()] = \
                rapor.eleme_dagilimi.get(p.eleme_sebebi.split("(")[0].strip(), 0) + 1
            continue
        h = degerlendir(job, gecmis=gecmis,
                        yeniden_yayim=depo.yeniden_yayim_sayisi(job),
                        sirket_ayni_baslik=ayni_baslik.get(job.title_key, 0))
        if h.risk >= hayalet_esigi:
            rapor.hayalet_elenen += 1
            continue
        s_ = Sonuc(job, p, h)
        if s_.nihai >= min_puan:
            rapor.sonuclar.append(s_)
    depo.commit()

    # --- İKİNCİ AŞAMA (yalnız Türk panoları) ---
    # Liste sayfası ilan METNİ vermiyor; yetenek eşleştirmesi onsuz çalışmaz.
    # Ama 50 ilanın 50'si için detay çekmek hem yavaş hem nezaketsiz. Bu yüzden
    # yalnızca SERT FİLTRELERİ GEÇEN ilanlar için detay çekilip yeniden puanlanıyor.
    tr_adaylar = [s_ for s_ in rapor.sonuclar if s_.job.source in TR_KAYNAKLARI
                  and not s_.job.raw.get("detay_cekildi")]
    if tr_adaylar:
        _asama(f"Türk panolarında {len(tr_adaylar)} ilanın metni çekiliyor")
        for kaynak_adi, K in TR_KAYNAKLARI.items():
            kume = [s_.job for s_ in tr_adaylar if s_.job.source == kaynak_adi]
            if not kume:
                continue
            kaynak = K()
            try:
                n = kaynak.detaylari_cek(kume, ust_sinir=tr_detay_siniri)
                rapor.tr_detay_cekilen += n
                for h in getattr(kaynak, "detay_hatalari", [])[:3]:
                    rapor.hatalar.append(f"{kaynak_adi} detay: {h}")
            except Exception as e:
                rapor.hatalar.append(f"{kaynak_adi} detay: {type(e).__name__}")
        # metin geldi -> yeniden puanla
        yeniden: list[Sonuc] = []
        for s_ in rapor.sonuclar:
            if s_.job.source in TR_KAYNAKLARI and s_.job.raw.get("detay_cekildi"):
                p2 = puanla(s_.job, profil, idf)
                if p2.elendi:
                    rapor.elenen += 1
                    continue
                h2 = degerlendir(s_.job)
                if h2.risk >= hayalet_esigi:
                    rapor.hayalet_elenen += 1
                    continue
                s_ = Sonuc(s_.job, p2, h2)
            if s_.nihai >= min_puan:
                yeniden.append(s_)
        rapor.sonuclar = yeniden

    # --- ÜÇÜNCÜ AŞAMA: uyum hakemi (yalnız "gelişmiş arama" seçiliyse) ---
    # Motor sözcüğe bakar, anlama bakmaz. Bu katman kısa listeye giren ilanların
    # adayın İŞİNE ait olup olmadığını denetler ve sıralamayı düzeltir.
    # Yalnız kısa listeye uygulanır: 10.000 ilanı gömmek gereksiz, elenenler zaten
    # listeye girmiyor. Model yoksa/yüklenemezse sessizce atlanır.
    if gelismis and rapor.sonuclar:
        try:
            from .uyum import hakem
            h = hakem()
            if h is not None:
                _asama(f"{len(rapor.sonuclar)} ilan uyum açısından denetleniyor")
                skorlar = h.skorla(profil, [s_.job for s_ in rapor.sonuclar])
                for s_, u in zip(rapor.sonuclar, skorlar):
                    if u is None:          # sınır dışında kaldı (zayıf donanım koruması)
                        continue
                    s_.puan.uyum = u
                    if u < 0:
                        s_.puan.uyarilar.append(
                            "uyum denetimi: bu ilan senin alanınla aynı sözcükleri "
                            "kullanıyor ama başka bir mesleği tarif ediyor olabilir")
                rapor.uyum_denetlenen = sum(1 for x in skorlar if x is not None)
            else:
                rapor.hatalar.append("gelişmiş arama istendi ama model yüklenemedi — "
                                     "yalnız motor sonuçları gösteriliyor")
        except Exception as e:
            rapor.hatalar.append(f"uyum denetimi atlandı: {type(e).__name__}")

    rapor.kapanan = depo.kapananlari_isaretle(run_id, tokenlar)
    depo.kosu_bitir(run_id, rapor.cekilen)
    depo.close()
    # min_puan eşiği uyum düzeltmesinden ÖNCE uygulanmıştı; düzeltme sonrası
    # eşiğin altına düşenler listede kalır (kullanıcı neden düştüğünü görsün).
    rapor.sonuclar.sort(key=lambda s: -s.nihai)
    return rapor

def sonuc_sozlugu(s: "Sonuc") -> dict:
    """Bir sonucu arayüzün filtreleyebileceği düz sözlüğe çevirir."""
    from .siniflandir import calisma_sekli, istihdam_turu
    j, p, h = s.job, s.puan, s.hayalet
    return {
        "uid": j.uid,
        "puan": s.nihai,
        "ham_puan": p.toplam,
        "sirket": j.company,
        "baslik": j.title,
        "url": j.url,
        "kaynak": j.source,
        "konumlar": j.locations,
        "konum_durumu": p.konum_durumu,
        "bolum": j.department,
        "calisma_sekli": calisma_sekli(j),
        "istihdam_turu": istihdam_turu(j),
        "kidem": p.kidem,
        "istenen_yil": p.istenen_yil,
        "yas_gun": round(h.yas_gun) if h.yas_gun is not None else None,
        "yayin": j.posted_at.isoformat() if j.posted_at else None,
        "hayalet_bant": h.bant,
        "hayalet_risk": round(h.risk, 2),
        "hayalet_gerekce": h.gerekceler,
        "rol_ailesi": p.rol_ailesi,
        "rol_puan": round(p.rol_puan),
        "yetenek_puan": round(p.yetenek_puan),
        "eslesen": p.eslesen_yetenekler,
        "eksik": p.eksik_yetenekler,
        "uyarilar": p.uyarilar,
        # Gelişmiş aramada dolu; None ise o tarama hızlı modda koşmuştur.
        "uyum": round(p.uyum, 4) if p.uyum is not None else None,
        "maas": j.raw.get("salary") or (
            f"{j.raw['salary_min']}-{j.raw['salary_max']} USD"
            if j.raw.get("salary_min") else None),
        "aciklama": j.description[:12000],
    }


def json_yaz(rapor: "TaramaRaporu", yol: str = "out/sonuclar.json") -> str:
    """Tarama sonucunu arayüz için diske yazar.

    Rapordaki her sonuç yazılır. Panel taramayı min_puan=0 ile başlatır; böylece
    kullanıcı arayüzdeki puan kaydırıcısını indirince yeniden tarama gerekmez.
    (CLI'nin varsayılan eşiği 25'tir, orada eşik altı zaten rapora girmez.)"""
    h = Path(yol)
    h.parent.mkdir(parents=True, exist_ok=True)
    govde = {
        "olusturma": datetime.now(timezone.utc).isoformat(),
        "cekilen": rapor.cekilen,
        "elenen": rapor.elenen,
        "hayalet_elenen": rapor.hayalet_elenen,
        "tekrar_atilan": rapor.tekrar_atilan,
        "eleme_dagilimi": rapor.eleme_dagilimi,
        "hatalar": rapor.hatalar,
        "uyum_denetlenen": rapor.uyum_denetlenen,
        "ilanlar": [sonuc_sozlugu(s) for s in rapor.sonuclar],
    }
    h.write_text(json.dumps(govde, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(h)
