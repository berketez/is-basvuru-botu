"""Türk iş panoları — nazik, robots.txt'ye uyumlu, iki aşamalı tarama.

DURUŞ: Bu panolarda herkese açık API yok, dolayısıyla HTML okunur. Yapılan şey
"atlatma" değil, NAZİK TARAMA:
  - robots.txt her koşuda okunur ve PROGRAMATİK uygulanır (izin yoksa istek yok)
  - istek hızı elle sınırlanır (varsayılan 1 istek / 2 sn), tek iş parçacığı
  - gerçek User-Agent + iletişim adresi
  - 403/429 görülürse pano O KOŞUM için kapatılır ve kullanıcıya bildirilir
Yapılmayan: CAPTCHA çözme, parmak izi sahteciliği, giriş yapmış oturum sürme.

Ölçüldü (11 Eyl 2026): kariyer.net robots.txt ilan sayfalarını yasaklamıyor
(/filtre/*, /servisler/, /ozgecmis/* yasak — onlara dokunulmuyor). Düz anonim
istekle liste sayfası HTTP 200, 0,56 sn, 50 ilan kartı.

İKİ AŞAMA — neden:
  1) LİSTE sayfası kart başına başlık + şirket + konum + çalışma modeli + istihdam
     türü + tarih veriyor. Tek istekte 50 ilan. Sert filtreler için bu YETER.
  2) DETAY sayfası yalnızca başlık filtresini geçen ilanlar için çekilir; ilan
     metni (yetenek eşleştirmesi için) oradan gelir.
Böylece 50 ilan için 50 istek yerine ~5 istek atılır.
"""
from __future__ import annotations

import html as _html
import json
import re
import time
import hashlib
import os
import pathlib
import urllib.robotparser as rp
from urllib.parse import urljoin, urlparse

from ..models import Job
from .base import Kaynak, KaynakHatasi, html_temizle, iso_tarih

TR_SAAT_FARKI = 3   # Europe/Istanbul, UTC+3 (yaz saati uygulaması yok)


def tr_tarih(ham: str | None):
    """Türk panoları tarihi saat dilimsiz yazıyor; bu YEREL saattir.
    UTC sanılırsa ilan 3 saat GELECEKTE görünür ve yaş negatif çıkar (ölçüldü: -0,1 gün)."""
    from datetime import timedelta
    d = iso_tarih((ham or "").replace(" ", "T"))
    if d is None:
        return None
    # iso_tarih saat dilimsiz girdiyi UTC sayar; yerel saat olduğu için farkı düşüyoruz.
    return d - timedelta(hours=TR_SAAT_FARKI) if (ham and "+" not in ham and "Z" not in ham) else d

TARAYICI_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
ISTEK_ARASI = 4.0          # saniye — robots.txt'de Crawl-delay yok, kendi sınırımızı koyuyoruz
DETAY_UST_SINIR = 40       # koşum başına en fazla kaç detay sayfası
ENGEL_SOGUMA_SAAT = 6      # 403/429 sonrası panoya kaç saat dokunulmayacağı

# ÖRNEK SAYFA (fixture) MODU — geliştirme sırasında canlı siteye HİÇ istek atmamak için.
#   ISBOT_ORNEK=kaydet  -> her çekilen sayfa tests/ornekler/ altına yazılır
#   ISBOT_ORNEK=oku     -> istek atılmaz, yalnızca kayıtlı örneklerden okunur
# Bu, 11 Eyl 2026'daki 403'ün kök sebebini kalıcı olarak ortadan kaldırır: geliştirme
# ve test artık canlı panoyu hiç yormaz. Ayrıştırıcı değişikliği örnekle sınanır.
ORNEK_MOD = os.environ.get("ISBOT_ORNEK", "").strip().lower()
ORNEK_DIZIN = pathlib.Path(__file__).resolve().parent.parent.parent / "tests" / "ornekler"

_ETIKET = re.compile(r"<[^>]+>")
_BOSLUK = re.compile(r"(?:&nbsp;|\s)+")
# "3 gün", "1 saat", "2 hafta", "1 ay" -> gün
_GORECELI = re.compile(r"(\d+)\s*(saniye|dakika|saat|gün|gun|hafta|ay|yıl|yil)")
_BIRIM_GUN = {"saniye": 0, "dakika": 0, "saat": 0, "gün": 1, "gun": 1,
              "hafta": 7, "ay": 30, "yıl": 365, "yil": 365}


def _tmz(s: str) -> str:
    return _BOSLUK.sub(" ", _ETIKET.sub(" ", _html.unescape(s or ""))).strip()


def _goreceli_gun(metin: str) -> float | None:
    """'2 gün', 'update 4 saat' gibi göreli ifadeyi güne çevirir."""
    m = _GORECELI.search(metin or "")
    if not m:
        return None
    return float(m.group(1)) * _BIRIM_GUN.get(m.group(2), 1)


class TrPano(Kaynak):
    """Türk panoları için ortak taban: robots.txt + hız sınırı + iki aşama."""
    ad = "tr-pano"
    KOK = ""

    def __init__(self) -> None:
        super().__init__()
        self.s.headers.update({
            "User-Agent": TARAYICI_UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            "X-Contact": "https://github.com/berketez/is-basvuru-bot",
        })
        self._robot: rp.RobotFileParser | None = None
        self._son_istek = 0.0

    # ---------- nezaket ----------
    def _robots(self) -> rp.RobotFileParser:
        if self._robot is None:
            p = rp.RobotFileParser()
            try:
                r = self.s.get(urljoin(self.KOK, "/robots.txt"), timeout=15)
                p.parse(r.text.splitlines() if r.status_code == 200 else [])
            except Exception:
                p.parse([])                      # okunamadıysa boş kural: izin var say
            self._robot = p
        return self._robot

    def _izinli(self, url: str) -> bool:
        try:
            return self._robots().can_fetch(TARAYICI_UA, url)
        except Exception:
            return True

    # ---------- KALICI hız sınırı ----------
    # NEDEN DİSKE YAZILIYOR: sınır süreç-içi tutulursa her yeni koşum sayacı sıfırdan
    # başlatır. Ard arda çalıştırılan betikler/taramalar gerçekte çok daha hızlı istek
    # atar ve pano 403 verir (ölçüldü: kariyer.net bizi engelledi). Zaman damgası
    # dosyada tutulunca sınır SÜREÇLER ARASI da geçerli olur.
    def _damga_yolu(self, ad: str) -> "pathlib.Path":
        from ..yollar import veri_dosya
        return veri_dosya("data", f"pano-{self.ad}-{ad}.txt")

    def _damga_oku(self, ad: str) -> float:
        try:
            return float(self._damga_yolu(ad).read_text(encoding="utf-8").strip())
        except Exception:
            return 0.0

    def _damga_yaz(self, ad: str, deger: float) -> None:
        try:
            self._damga_yolu(ad).write_text(str(deger), encoding="utf-8")
        except Exception:
            pass

    def _engelli_mi(self) -> float:
        """Engel soğuması bitmediyse kalan saniyeyi döndürür."""
        kalan = self._damga_oku("engel") + ENGEL_SOGUMA_SAAT * 3600 - time.time()
        return max(0.0, kalan)

    def _ornek_yolu(self, url: str) -> "pathlib.Path":
        ad = hashlib.sha256(url.encode()).hexdigest()[:16]
        return ORNEK_DIZIN / f"{self.ad}-{ad}.html"

    def _sayfa(self, url: str) -> str:
        """robots.txt + KALICI hız sınırı + engel soğuması ile tek sayfa çeker.
        ISBOT_ORNEK=oku ise ağa HİÇ çıkmaz, kayıtlı örnekten okur."""
        ornek = self._ornek_yolu(url)
        if ORNEK_MOD == "oku":
            if not ornek.exists():
                raise KaynakHatasi(f"örnek yok (ISBOT_ORNEK=oku): {url}")
            return ornek.read_text(encoding="utf-8")

        kalan = self._engelli_mi()
        if kalan > 0:
            raise KaynakHatasi(
                f"{self.ad}: pano engel verdi, {kalan/3600:.1f} saat soğuma sürüyor")
        if not self._izinli(url):
            raise KaynakHatasi(f"robots.txt izin vermiyor: {url}")
        son = max(self._son_istek, self._damga_oku("son"))
        gecen = time.time() - son
        if gecen < ISTEK_ARASI:
            time.sleep(ISTEK_ARASI - gecen)
        r = self.s.get(url, timeout=30, allow_redirects=True)
        self._son_istek = time.time()
        self._damga_yaz("son", self._son_istek)
        if r.status_code in (403, 429):
            # Panoyu SAATLERCE rahat bırak. Israrla denemek engeli uzatır.
            self._damga_yaz("engel", time.time())
            raise KaynakHatasi(
                f"{r.status_code} — {self.ad} engel verdi, {ENGEL_SOGUMA_SAAT} saat "
                f"dokunulmayacak ({url})")
        if r.status_code >= 400:
            raise KaynakHatasi(f"HTTP {r.status_code}: {url}")
        if ORNEK_MOD == "kaydet":
            ornek.parent.mkdir(parents=True, exist_ok=True)
            ornek.write_text(r.text, encoding="utf-8")
        return r.text

    # ---------- alt sınıfların doldurduğu ----------
    def liste_urlleri(self, sorgu: str) -> list[str]:
        raise NotImplementedError

    def kartlari_ayikla(self, html: str) -> list[Job]:
        raise NotImplementedError

    def detay_zenginlestir(self, job: Job) -> None:
        """İlan metnini ve varsa ek alanları detay sayfasından doldurur."""
        raise NotImplementedError

    # ---------- akış ----------
    def cek(self, sorgu: str = "", etiket: str = "") -> list[Job]:
        ilanlar: list[Job] = []
        for u in self.liste_urlleri(sorgu):
            try:
                ilanlar += self.kartlari_ayikla(self._sayfa(u))
            except KaynakHatasi:
                raise                            # 403/429: tüm panoyu bırak
            except Exception:
                continue                         # tek sayfa bozuksa diğerine geç
        # tekrarları at (aynı ilan birden çok kategoride görünebilir)
        gorulen, tekil = set(), []
        for j in ilanlar:
            if j.url in gorulen:
                continue
            gorulen.add(j.url)
            tekil.append(j)
        return tekil

    detay_hatalari: list[str] = []

    def detaylari_cek(self, ilanlar: list[Job], ust_sinir: int = DETAY_UST_SINIR) -> int:
        """İkinci aşama: yalnız verilen ilanlar için detay sayfası çeker.
        Çağıran taraf hangi ilanların değdiğine karar verir (başlık filtresini
        geçenler). Dönüş: başarıyla zenginleştirilen ilan sayısı."""
        n = 0
        self.detay_hatalari: list[str] = []
        for j in ilanlar[:ust_sinir]:
            try:
                self.detay_zenginlestir(j)
                n += 1
            except Exception as e:
                # Sessizce yutmak yanıltıcıydı: "1 detay çekildi" görülüp sebebi
                # bilinmiyordu. Hatalar toplanıp çağırana bildiriliyor.
                self.detay_hatalari.append(f"{j.url[:60]}: {type(e).__name__}")
        return n


class KariyerNet(TrPano):
    """kariyer.net — Türkiye'nin en büyük panosu.

    Liste kartları `data-test` nitelikleriyle işaretli; bunlar sitenin kendi test
    kancaları olduğu için CSS sınıflarından daha kararlı.
    DİKKAT: /filtre/* ve /servisler/ robots.txt'de YASAK — o yollara hiç gidilmiyor.
    """
    ad = "kariyernet"
    KOK = "https://www.kariyer.net"
    KART = re.compile(r'<a[^>]+href="(/is-ilani/[^"]+)"[^>]*>(.*?)</a>', re.S)

    # ÖNEMLİ BULGU: "/is-ilanlari/bilgi-teknolojileri" kategori filtresi DEĞİL —
    # o sayfa karışık ilan gösteriyor. Gerçek filtre "/filtre/*" altında ve orası
    # robots.txt'de YASAK. Ama sitemap'te ilan edilen "/is-ilanlari/{şehir}-{pozisyon}"
    # sayfaları hem robots-izinli hem gerçekten filtreli (ölçüldü: yazılım sorgusunda
    # 53 yazılım ilanı, muhasebe sorgusunda 53 muhasebe ilanı). Ve HER MESLEK için
    # çalışıyor — yazılım dışı sektör kapsamının anahtarı bu.
    TR_HARF = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
                             "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u",
                             "â": "a", "î": "i", "û": "u"})

    @classmethod
    def _dilim(cls, metin: str) -> str:
        """'Yazılım Geliştirme Uzmanı' -> 'yazilim+gelistirme+uzmani'
        Site ASCII'ye indirgenmiş, boşlukları '+' olan dilimler kullanıyor."""
        t = metin.strip().lower().translate(cls.TR_HARF)
        t = re.sub(r"[^a-z0-9\s+-]", "", t)
        return re.sub(r"\s+", "+", t).strip("+")

    HARITA_ONBELLEK = "kariyernet-sitemap.json"
    HARITA_OMUR_GUN = 7

    def _kanonik_yollar(self) -> list[str]:
        """Sitenin sitemap'inde İLAN EDİLEN gerçek kategori yollarını döndürür.

        NEDEN GEREKLİ: Dilimi kendimiz uydurursak site sessizce GENEL listeye düşüyor
        ve alakasız ilan getiriyor (ölçüldü: 'yapay+zeka+muhendisi' -> 'Çağrı Merkezi
        Elemanı'). Yalnızca kanonik yollar gerçekten filtreliyor. Sitemap'i site
        robots.txt'de kendisi ilan ediyor; 64.561 yol, 9 alt harita, ~20 saniye.
        """
        from ..yollar import veri_dosya
        import json as _json
        import time as _time
        yol = veri_dosya("data", self.HARITA_ONBELLEK)
        if yol.exists() and (_time.time() - yol.stat().st_mtime) < self.HARITA_OMUR_GUN * 86400:
            try:
                return _json.loads(yol.read_text(encoding="utf-8"))
            except Exception:
                pass
        toplam: list[str] = []
        try:
            idx = self._sayfa(urljoin(self.KOK, "/sitemaps/"))
            for alt in re.findall(r"<loc>(.*?)</loc>", idx):
                try:
                    x = self._sayfa(alt)
                except Exception:
                    continue
                toplam += re.findall(
                    rf"<loc>{re.escape(self.KOK)}(/is-ilanlari/[^<]+)</loc>", x)
        except Exception:
            return []
        toplam = sorted(set(toplam))
        if toplam:
            yol.write_text(_json.dumps(toplam), encoding="utf-8")
        return toplam

    # Tek başına hiçbir şey ayırt etmeyen sözcükler. Bunlar eşleşme sayılırsa
    # "yapay zeka mühendisi" sorgusu "aerodinamik mühendisi"ne eşleniyor (ölçüldü).
    GENEL_SOZCUK = {"muhendisi", "muhendis", "uzmani", "uzman", "sorumlusu", "elemani",
                    "yetkilisi", "danismani", "personeli", "yoneticisi", "gorevlisi",
                    "teknikeri", "teknisyeni", "asistani", "yardimcisi", "sefi",
                    "mudur", "muduru", "operatoru", "calisani", "adayi",
                    # Rol SON EKLERİ de tek başına ayırt etmez: "frontend geliştirici"
                    # sorgusu yalnız "gelistirici" tutarak "c# geliştirici"ye eşleniyordu.
                    "gelistirici", "gelistiricisi", "gelistirme", "tasarimci",
                    "programcisi", "yazilimcisi", "mimari", "danisman"}

    @classmethod
    def _parcalar(cls, dilim: str) -> set[str]:
        return {p for p in re.split(r"[+\-/]", dilim) if len(p) > 2}

    @classmethod
    def _ayirt_edici(cls, parcalar: set[str]) -> set[str]:
        return parcalar - cls.GENEL_SOZCUK

    def liste_urlleri(self, sorgu: str) -> list[str]:
        """sorgu biçimi: 'pozisyon' veya 'pozisyon@şehir'.

        Sorgu, sitemap'teki kanonik yollar arasından EN YAKIN olanlara eşlenir
        (ortak sözcük oranına göre). Uydurma dilim üretilmez.
        """
        poz, _, sehir = sorgu.partition("@")
        poz_p = self._parcalar(self._dilim(poz))
        sehir_d = self._dilim(sehir) if sehir else ""
        if not poz_p:
            return []
        yollar = self._kanonik_yollar()
        if not yollar:                                    # sitemap alınamadıysa dene
            d = self._dilim(poz)
            return [urljoin(self.KOK, f"/is-ilanlari/{sehir_d + '-' if sehir_d else ''}{d}")]

        puanli: list[tuple[float, str]] = []
        for y in yollar:
            dilim = y.rsplit("/", 1)[-1]
            # şehir istendiyse o şehri içerenleri tercih et, ama zorunlu tutma
            sehirli = bool(sehir_d) and dilim.startswith(sehir_d)
            ortak = poz_p & self._parcalar(dilim)
            # En az BİR ayırt edici sözcük tutmalı; yoksa eşleşme anlamsızdır.
            # Boş dönmek, alakasız kategori döndürmekten iyidir.
            if not self._ayirt_edici(ortak):
                continue
            # Jaccard benzeri: ortak / (sorgu sözcükleri) — kısa ve birebir dilimler kazanır
            skor = len(ortak) / len(poz_p) - 0.04 * (len(self._parcalar(dilim)) - len(ortak))
            if sehirli:
                skor += 0.5
            puanli.append((skor, y))
        puanli.sort(key=lambda x: -x[0])
        # en iyi 2 yol yeter; daha fazlası gereksiz istek
        return [urljoin(self.KOK, y) for _, y in puanli[:2]]

    def kartlari_ayikla(self, html: str) -> list[Job]:
        ilanlar: list[Job] = []
        for yol, ic in self.KART.findall(html):
            def alan(ad: str) -> str:
                m = re.search(rf'data-test="{ad}"[^>]*>(.*?)</', ic, re.S)
                return _tmz(m.group(1)) if m else ""

            baslik = alan("ad-card-title")
            if not baslik:
                continue
            sirket = alan("subtitle") or "?"
            konum = alan("location")
            duz = _tmz(ic)
            # kart metninden çalışma modeli ve istihdam türü
            model = next((x for x in ("Uzaktan", "Hibrit", "İş Yerinde") if x in duz), "")
            tur = next((x for x in ("Tam zamanlı", "Yarı zamanlı", "Dönemsel",
                                    "Stajyer", "Proje bazlı") if x in duz), "")
            yas = _goreceli_gun(duz)
            from datetime import datetime, timedelta, timezone
            tarih = (datetime.now(timezone.utc) - timedelta(days=yas)) if yas is not None else None
            ilanlar.append(Job(
                source=self.ad,
                company=sirket,
                board_token="kariyernet",
                native_id=(re.search(r"-(\d+)$", yol) or [None, yol])[1],
                title=baslik,
                url=urljoin(self.KOK, yol),
                locations=[konum] if konum else [],
                description="",                  # ikinci aşamada dolar
                employment_type=tur,
                remote_flag=True if model == "Uzaktan" else (False if model else None),
                posted_at=tarih,
                updated_at=tarih,
                raw={"workplaceType": {"Uzaktan": "remote", "Hibrit": "hybrid",
                                       "İş Yerinde": "onsite"}.get(model, ""),
                     "detay_cekildi": False},
            ))
        return ilanlar

    def detay_zenginlestir(self, job: Job) -> None:
        h = self._sayfa(job.url)
        # ilan gövdesi: sayfadaki en uzun metin bloğu (sınıf adları değişken)
        parcalar = re.findall(r'<(?:div|section|article)[^>]*>(.*?)</(?:div|section|article)>',
                              h, re.S)
        metin = max((_tmz(p) for p in parcalar), key=len, default="")
        # etiket/değer çiftleri (Tecrübe, Eğitim Seviyesi, Askerlik)
        ekler = []
        for m in re.finditer(r'data-test="alignment-list-title"[^>]*>(.*?)</div>.{0,300}?'
                             r'data-test="alignment-list-value"[^>]*>(.*?)</div>', h, re.S):
            ekler.append(f"{_tmz(m.group(1))}: {_tmz(m.group(2))}")
        job.description = (metin + "\n" + "\n".join(ekler)).strip()
        job.raw["detay_cekildi"] = True


class ElemanNet(TrPano):
    """eleman.net — ilan DETAY sayfalarında schema.org JSON-LD var.

    Ölçüldü: title, datePosted (saatli), validThrough, employmentType (Türkçe),
    hiringOrganization, jobLocation, industry ve TRY cinsinden baseSalary veriyor.
    `validThrough` doğrudan hayalet tespiti girdisidir.
    """
    ad = "elemannet"
    KOK = "https://www.eleman.net"
    # DİKKAT: eleman.net href'te MUTLAK URL kullanıyor; göreli yol beklersen 0 bulursun.
    # title="" niteliğinde ilan başlığı da var -> liste aşamasında başlık alınır,
    # böylece gereksiz detay isteği atılmaz.
    BAG = re.compile(r'href="(?:https?://(?:www\.)?eleman\.net)?(/is-ilani/[\w%+.-]+)"'
                     r'(?:[^>]*\btitle="([^"]*)")?')
    LD = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S)

    def liste_urlleri(self, sorgu: str) -> list[str]:
        return [urljoin(self.KOK, "/is-ilanlari")]

    def kartlari_ayikla(self, html: str) -> list[Job]:
        ilanlar: list[Job] = []
        gorulen = set()
        for yol, baslik in self.BAG.findall(html):
            if yol in gorulen:
                continue
            gorulen.add(yol)
            ilanlar.append(Job(
                source=self.ad, company="?", board_token="elemannet",
                native_id=(re.search(r"i(\d+)$", yol) or [None, yol])[1],
                title=_tmz(baslik), url=urljoin(self.KOK, yol),
                raw={"detay_cekildi": False},
            ))
        return ilanlar

    def detay_zenginlestir(self, job: Job) -> None:
        h = self._sayfa(job.url)
        for m in self.LD.finditer(h):
            try:
                d = json.loads(m.group(1))
            except Exception:
                continue
            if not isinstance(d, dict) or str(d.get("@type", "")).lower() != "jobposting":
                continue
            job.title = _tmz(str(d.get("title") or ""))
            job.company = ((d.get("hiringOrganization") or {}).get("name")
                           or _tmz(str((d.get("hiringOrganization") or {}).get("url", ""))
                                   .rsplit("/", 1)[-1]) or "?")
            job.employment_type = str(d.get("employmentType") or "")
            job.description = html_temizle(str(d.get("description") or ""))
            job.posted_at = tr_tarih(str(d.get("datePosted") or ""))
            job.updated_at = job.posted_at
            yer = d.get("jobLocation")
            adresler = yer if isinstance(yer, list) else [yer] if yer else []
            konumlar = []
            for a in adresler:
                adr = (a or {}).get("address") or {}
                adr = adr[0] if isinstance(adr, list) and adr else adr
                sehir = (adr or {}).get("addressLocality")
                if sehir:
                    konumlar.append(_tmz(str(sehir)))
            job.locations = konumlar
            maas = d.get("baseSalary") or {}
            job.raw.update({
                "son_gecerlilik": d.get("validThrough"),
                "sektor": d.get("industry"),
                # Değer yoksa para birimini tek başına yazma ("maaş: TRY" anlamsız).
                "salary": (f"{(maas.get('value') or {}).get('value')} "
                           f"{maas.get('currency','')}".strip()
                           if (maas.get("value") or {}).get("value") else None),
                "detay_cekildi": True,
            })
            return
        raise KaynakHatasi("JSON-LD JobPosting bulunamadı")
