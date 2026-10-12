"""Türk iş panoları — nazik, robots.txt'ye uyumlu, iki aşamalı tarama.

DURUŞ: Bu panolarda herkese açık API yok, dolayısıyla HTML okunur. Yapılan şey
"atlatma" değil, NAZİK TARAMA:
  - robots.txt okunur ve PROGRAMATİK uygulanır (izin yoksa istek yok)
  - istek hızı pano başına sınırlanır ve istekler TEK sıradan geçer (bkz. pano_onbellek)
  - sayfa önbelleği + kayan pencereli istek bütçesi: aynı sayfa yeniden istenmez
  - 403/429 görülürse pano saatlerce rahat bırakılır, o sürede önbellek kullanılır
Yapılmayan: CAPTCHA çözme, parmak izi sahteciliği, IP değiştirme, giriş yapmış oturum.
kariyer.net PerimeterX (HUMAN) bot koruması arkasındadır (ölçüldü 2026-10-12);
koruma atlatılmaz, ona takılmayacak kadar az istek atılır.

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
import functools
import urllib.robotparser as rp
from urllib.parse import urljoin, urlparse

from ..models import Job
from . import pano_onbellek as onbellek
from .base import Kaynak, KaynakHatasi, html_temizle, iso_tarih


class PanoEngeli(KaynakHatasi):
    """Pano 403/429 verdi ya da soğuma süresi sürüyor. Israr engeli uzatır."""


class ButceDoldu(KaynakHatasi):
    """Panonun kayan pencereli istek bütçesi doldu (engel DEĞİL, kendi sınırımız)."""

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
                           # (pano sınıfı kendi istek_arasi'nı koyabilir; bkz. KariyerNet)
DETAY_UST_SINIR = 40       # koşum başına en fazla kaç detay sayfası
ENGEL_SOGUMA_SAAT = 6      # 403/429 sonrası panoya kaç saat dokunulmayacağı
# Önbellek ömürleri. Liste sayfası (kategori) gün içinde yavaş değişir; ilan metni
# yayından kalkana kadar neredeyse hiç değişmez. robots.txt günde bir okunur — eskiden
# her sorgu için ayrı okunuyordu (kariyer.net'e taramada 7 fazladan istek).
LISTE_OMRU_SN = 12 * 3600
DETAY_OMRU_SN = 14 * 86400
ROBOTS_OMRU_SN = 24 * 3600
# Engel ya da bütçe varken bu yaşa kadar BAYAT önbellek kullanılır (kullanıcıya söylenir).
BAYAT_UST_SN = 72 * 3600

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
    istek_arasi = ISTEK_ARASI
    # Kayan pencerede (BUTCE_PENCERE_SN) ağa çıkan en çok istek. Önbellekten okunan sayfa
    # sayılmaz. Pano sınıfı kendi değerini koyar (bkz. KariyerNet).
    saatlik_butce = 60
    BUTCE_PENCERE_SN = 3600
    # Tek taramanın kullanabileceği en çok istek. None = saatlik bütçenin tamamı.
    kosu_butcesi: int | None = None

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
        # Bu nesnenin tarama boyunca ne yaptığı — panelde "pano durumu" olarak gösterilir.
        self.sayac = {"ag": 0, "onbellek": 0, "bayat": 0}
        self.uyari = ""                  # engel/bütçe nedeniyle yarım kaldıysa sebebi

    # ---------- nezaket ----------
    def _robots(self) -> rp.RobotFileParser:
        if self._robot is None:
            p = rp.RobotFileParser()
            url = urljoin(self.KOK, "/robots.txt")
            kayit = onbellek.oku(url)
            if kayit and time.time() - kayit[0] < ROBOTS_OMRU_SN:
                p.parse(kayit[1].splitlines())
            else:
                try:
                    with onbellek.pano_kilidi(self.ad):
                        self._bekle()
                        r = self.s.get(url, timeout=15)
                        self._istek_bitti()
                    if r.status_code == 200:
                        onbellek.yaz(url, r.text)
                    elif r.status_code in (403, 429):    # robots.txt bile engelli: pano kapalı
                        self._damga_yaz("engel", time.time())
                    p.parse(r.text.splitlines() if r.status_code == 200 else
                            (kayit[1].splitlines() if kayit else []))
                except Exception:
                    # okunamadıysa: eski kopya varsa o, yoksa boş kural (izin var say)
                    p.parse(kayit[1].splitlines() if kayit else [])
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

    def _bekle(self) -> None:
        """Panoya giden son istekten bu yana istek_arasi geçene kadar bekler.
        Çağıran pano_kilidi içinde olmalı; yoksa iki iş parçacığı aynı damgayı okur."""
        son = max(self._son_istek, self._damga_oku("son"))
        gecen = time.time() - son
        if gecen < self.istek_arasi:
            time.sleep(self.istek_arasi - gecen)

    def _istek_bitti(self) -> None:
        self._son_istek = time.time()
        self._damga_yaz("son", self._son_istek)
        onbellek.istek_kaydet(self.ad)
        self.sayac["ag"] += 1

    def _butce_mesaji(self) -> str:
        if self.kosu_butcesi and self.sayac["ag"] >= self.kosu_butcesi:
            return (f"{self.ad}: bu tarama için istek sınırı ({self.kosu_butcesi}) doldu — "
                    "bot korumasına takılmamak için")
        return (f"{self.ad}: saatlik istek sınırı ({self.saatlik_butce}) doldu — bot "
                "korumasına takılmamak için; kalan sayfalar bir saat içinde açılır")

    def _taze_mi(self, url: str, omur_sn: float = LISTE_OMRU_SN) -> bool:
        kayit = onbellek.oku(url)
        return bool(kayit) and time.time() - kayit[0] < omur_sn

    def butce_kalan(self) -> int:
        saatlik = self.saatlik_butce - onbellek.istek_sayisi(self.ad, self.BUTCE_PENCERE_SN)
        kosu = (self.kosu_butcesi - self.sayac["ag"]) if self.kosu_butcesi else saatlik
        return max(0, min(saatlik, kosu))

    def _sayfa(self, url: str, omur_sn: float = LISTE_OMRU_SN) -> str:
        """Tek sayfa: önce önbellek, sonra robots.txt + bütçe + kilitli hız sınırı +
        engel soğuması ile ağ. Engel/bütçe varken BAYAT önbellek (≤ BAYAT_UST_SN) döner.
        ISBOT_ORNEK=oku ise ağa HİÇ çıkmaz, kayıtlı örnekten okur."""
        ornek = self._ornek_yolu(url)
        if ORNEK_MOD == "oku":
            if not ornek.exists():
                raise KaynakHatasi(f"örnek yok (ISBOT_ORNEK=oku): {url}")
            return ornek.read_text(encoding="utf-8")

        kayit = None if ORNEK_MOD == "kaydet" else onbellek.oku(url)
        yas = time.time() - kayit[0] if kayit else None
        if kayit and yas < omur_sn:
            self.sayac["onbellek"] += 1
            return kayit[1]

        def bayat_ya_da(hata: KaynakHatasi) -> str:
            if kayit and yas < BAYAT_UST_SN:
                self.sayac["bayat"] += 1
                return kayit[1]
            raise hata

        kalan = self._engelli_mi()
        if kalan > 0:
            return bayat_ya_da(PanoEngeli(
                f"{self.ad}: pano bot korumasıyla engel verdi, {kalan/3600:.1f} saat "
                f"dokunulmayacak"))
        if not self._izinli(url):
            raise KaynakHatasi(f"robots.txt izin vermiyor: {url}")
        if self.butce_kalan() <= 0:
            return bayat_ya_da(ButceDoldu(self._butce_mesaji()))
        with onbellek.pano_kilidi(self.ad):
            # Kilidi beklerken başka iş parçacığı engel yemiş ya da bütçeyi bitirmiş olabilir.
            if self._engelli_mi() > 0:
                return bayat_ya_da(PanoEngeli(f"{self.ad}: pano engel verdi"))
            if self.butce_kalan() <= 0:
                return bayat_ya_da(ButceDoldu(self._butce_mesaji()))
            self._bekle()
            r = self.s.get(url, timeout=30, allow_redirects=True)
            self._istek_bitti()
            if r.status_code in (403, 429):
                # Panoyu SAATLERCE rahat bırak. Israrla denemek engeli uzatır.
                self._damga_yaz("engel", time.time())
                return bayat_ya_da(PanoEngeli(
                    f"{r.status_code} — {self.ad} bot korumasıyla engel verdi, "
                    f"{ENGEL_SOGUMA_SAAT} saat dokunulmayacak"))
        if r.status_code >= 400:
            raise KaynakHatasi(f"HTTP {r.status_code}: {url}")
        if ORNEK_MOD == "kaydet":
            ornek.parent.mkdir(parents=True, exist_ok=True)
            ornek.write_text(r.text, encoding="utf-8")
        onbellek.yaz(url, r.text)
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
        return self.cek_coklu([sorgu])

    def cek_coklu(self, sorgular: list[str], ilerle=None, ayrilan: int = 0) -> list[Job]:
        """Bütün sorguların liste sayfalarını ÖNCELİK SIRASIYLA çeker: önce her sorgunun
        ilk (ülke geneli) sayfası, sonra ikincileri... Bütçe ya da engel taramayı yarıda
        keserse en değerli sayfalar alınmış olur. Eskiden her sorgu ayrı iş parçacığında
        tüm sayfalarını çekiyordu; bütçe ilk sorgulara gidiyor, sonrakiler hiç sayfa
        alamıyordu. Yarıda kalırsa toplanan ilanlar döner, sebep self.uyari'ya yazılır.

        ayrilan: bütçeden ilan metinlerine (ikinci aşama) bırakılacak istek sayısı. Liste
        sayfaları bunu tüketirse kısa listedeki ilanların hiçbirinin metni alınamaz."""
        kuyruklar = []
        for sorgu in sorgular:
            try:
                kuyruklar.append(self.liste_urlleri(sorgu))
            except (PanoEngeli, ButceDoldu) as e:
                self.uyari = str(e)
                kuyruklar.append([])
        sira: list[str] = []
        for i in range(max((len(k) for k in kuyruklar), default=0)):
            for k in kuyruklar:
                if i < len(k) and k[i] not in sira:
                    sira.append(k[i])
        ilanlar: list[Job] = []
        for u in sira:
            if ayrilan and self.butce_kalan() <= ayrilan and not self._taze_mi(u):
                self.uyari = self.uyari or (
                    f"{self.ad}: istek bütçesinin kalanı ilan metinlerine ayrıldı; "
                    "kalan liste sayfaları sonraki taramada")
                continue                         # önbellekte tazesi olanlar yine okunur
            try:
                kartlar = self.kartlari_ayikla(self._sayfa(u, LISTE_OMRU_SN))
            except (PanoEngeli, ButceDoldu) as e:
                # Ağa çıkılmadı (engel/bütçe kontrolü istekten ÖNCE). Devam edilir:
                # sıradaki sayfaların önbellekte kopyası olabilir.
                self.uyari = str(e)
                continue
            except Exception:
                continue                         # tek sayfa bozuksa diğerine geç
            ilanlar += kartlar
            if ilerle:
                ilerle(len(kartlar))
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
        ard_ag_hatasi = 0
        for j in ilanlar[:ust_sinir]:
            try:
                self.detay_zenginlestir(j)
                n += 1
                ard_ag_hatasi = 0
            except (PanoEngeli, ButceDoldu) as e:
                self.uyari = str(e)              # önbellekte metni olanlar yine okunur
                continue
            except OSError as e:
                # Bağlantı yok (requests hataları OSError'dur). Art arda 3 kez olursa
                # pano ulaşılamıyor demektir; her deneme istek_arasi bekleyip dakikalar
                # yiyordu.
                self.detay_hatalari.append(f"{j.url[:60]}: {type(e).__name__}")
                ard_ag_hatasi += 1
                if ard_ag_hatasi >= 3:
                    self.uyari = self.uyari or f"{self.ad}: bağlantı kurulamadı, ilan metinleri alınamadı"
                    break
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
    # 8 sn: ölçüldü (2026-10-09), 4 sn arayla ~45 istekten (~3 dk) sonra 403 verdi ve
    # pano 6 saat kapandı. Normal bir tarama 60 isteğe çıkabiliyor (6 sorgu x 5 sayfa +
    # 30 detay). Engelin hıza mı sayıya mı bağlı olduğu bilinmiyor; Berke'nin kararıyla
    # önce yavaşlatıldı. Tarama süresi bu panoda ~8 dakikaya çıkabilir.
    istek_arasi = 8.0
    # Saatte en çok 24 istek (önbellekten okunan sayılmaz). ÖLÇÜLDÜ: engel, dakikalar
    # içinde ~30 (8 sn arayla) ve ~45 (4 sn arayla) istekten sonra geldi. Engelin süre mi
    # sayı mı olduğu bilinmiyor; sınır bilinen en düşük eşiğin altında tutuldu. Normal bir
    # tarama (6 sorgu × ülke geneli + sektör sayfası + 8-10 ilan metni) buna sığar;
    # aynı saat içindeki ikinci tarama çoğunlukla önbellekten beslenir.
    saatlik_butce = 24
    # Tek tarama saatlik bütçenin en çok 16'sını kullanır. ÖLÇÜLDÜ (2026-10-12, canlı):
    # ilk CV'nin taraması 24 isteğin tamamını kullandı; 6 dakika sonraki ikinci CV'nin
    # kendine özgü sorguları ("havacılık", "aviyonik mühendisi") hiç çekilemedi ve listesi
    # yalnız birincinin sayfalarından oluştu. Kalan 8 istek, ikinci taramanın önbellekte
    # olmayan sorgularına yeter.
    kosu_butcesi = 16
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
    # 14 gün: tazeleme 10 istek (dizin + 9 alt harita) ve saatlik bütçenin yarısına yakın.
    # Kategori yolları (pozisyon/sektör/il) haftalar içinde pek değişmez.
    HARITA_OMUR_GUN = 14

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
        eski: list[str] = []
        if yol.exists():
            try:
                eski = _json.loads(yol.read_text(encoding="utf-8"))
            except Exception:
                eski = []
            if eski and (_time.time() - yol.stat().st_mtime) < self.HARITA_OMUR_GUN * 86400:
                return eski
        toplam: list[str] = []
        firmalar: list[str] = []
        try:
            idx = self._sayfa(urljoin(self.KOK, "/sitemaps/"), self.HARITA_OMUR_GUN * 86400)
            for alt in re.findall(r"<loc>(.*?)</loc>", idx):
                try:
                    x = self._sayfa(alt, self.HARITA_OMUR_GUN * 86400)
                except (PanoEngeli, ButceDoldu):
                    # Yarım harita eksik kategori demek; eskisi varsa onunla devam.
                    return eski
                except Exception:
                    continue
                toplam += re.findall(
                    rf"<loc>{re.escape(self.KOK)}(/is-ilanlari/[^<]+)</loc>", x)
                # FİRMA PROFİLLERİ de aynı gezintide toplanır — ayrı bir sitemap
                # turu yapmamak için. Bir firmanın profil sayfası o firmanın TÜM
                # açık ilanlarını verir; pozisyon sorgusuyla bulunamayan ilanlara
                # ulaşmanın tek yolu budur (ölçüldü: ASELSAN, TUSAŞ, ROKETSAN gibi
                # kurumların adı kategori yollarında HİÇ geçmiyor).
                firmalar += re.findall(
                    rf"<loc>{re.escape(self.KOK)}(/firma-profil/[^<]+)</loc>", x)
        except Exception:
            # Tazelenemedi (engel, bütçe, ağ). ESKİ kopya varsa o kullanılır: yoksa
            # liste_urlleri uydurma dilime düşer ve site genel listeyi (alakasız) döndürür.
            return eski
        if firmalar:
            veri_dosya("data", self.FIRMA_ONBELLEK).write_text(
                _json.dumps(sorted(set(firmalar))), encoding="utf-8")
        toplam = sorted(set(toplam))
        if toplam:
            yol.write_text(_json.dumps(toplam), encoding="utf-8")
        return toplam or eski

    FIRMA_ONBELLEK = "kariyernet-firmalar.json"

    def _firma_yollari(self) -> list[str]:
        """Sitemap'te ilan edilen firma profili yolları. Boşsa sitemap tazelenir."""
        from ..yollar import veri_dosya
        import json as _json
        import time as _time
        y = veri_dosya("data", self.FIRMA_ONBELLEK)
        if y.exists() and (_time.time() - y.stat().st_mtime) < self.HARITA_OMUR_GUN * 86400:
            try:
                return _json.loads(y.read_text(encoding="utf-8"))
            except Exception:
                pass
        self._kanonik_yollar()          # sitemap gezintisi firma yollarını da yazar
        try:
            return _json.loads(y.read_text(encoding="utf-8"))
        except Exception:
            return []

    def firma_urlleri(self, firma_adi: str, ust_sinir: int = 2) -> list[str]:
        """'ASELSAN' -> firma profil sayfası URL'leri.

        Bir kurumun birden çok tüzel kişiliği olabiliyor (ASELSAN Elektronik,
        ASELSAN Global, ASELSAN Konya...); ilanlar hepsine dağılıyor. Bu yüzden
        adı İÇEREN yolların en kısa `ust_sinir` tanesi alınır — en kısa slug
        genellikle ana şirkettir.
        """
        ad = self._dilim(firma_adi).replace("+", "-")
        if not ad:
            return []
        eslesen = [y for y in self._firma_yollari() if ad in y.rsplit("/", 1)[-1]]
        eslesen.sort(key=len)
        return [urljoin(self.KOK, y) for y in eslesen[:ust_sinir]]

    # Tek başına hiçbir şey ayırt etmeyen sözcükler. Bunlar eşleşme sayılırsa
    # "yapay zeka mühendisi" sorgusu "aerodinamik mühendisi"ne eşleniyor (ölçüldü).
    GENEL_SOZCUK = {"muhendisi", "muhendis", "uzmani", "uzman", "sorumlusu", "elemani",
                    "yetkilisi", "danismani", "personeli", "yoneticisi", "gorevlisi",
                    "teknikeri", "teknisyeni", "asistani", "yardimcisi", "sefi",
                    "mudur", "muduru", "operatoru", "calisani", "adayi",
                    # Rol SON EKLERİ de tek başına ayırt etmez: "frontend geliştirici"
                    # sorgusu yalnız "gelistirici" tutarak "c# geliştirici"ye eşleniyordu.
                    "gelistirici", "gelistiricisi", "gelistirme", "tasarimci",
                    "programcisi", "yazilimcisi", "mimari", "danisman",
                    # SEKTÖR SONEKLERİ de tek başına ayırt etmez. ÖLÇÜLDÜ:
                    # "savunma sanayi" sorgusu yalnız "sanayi" ortaklığıyla
                    # "boru+sanayi" sektör sayfasına eşleniyordu.
                    "sanayi", "sanayii", "ticaret", "hizmetleri", "hizmet",
                    "sektoru", "grubu", "kidemli", "genel"}

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
        # "firma:ASELSAN" biçimi: pozisyon değil ŞİRKET aranıyor. Firma profili o
        # şirketin tüm açık ilanlarını verir; pozisyon sorgusuyla bulunamayan
        # ilanlara ulaşmanın tek yolu budur.
        if sorgu.lower().startswith("firma:"):
            return self.firma_urlleri(sorgu.split(":", 1)[1])
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
            # Eşit skorlu yollar arasında BÜYÜK İL kazansın; yoksa sıralama
            # alfabetik kalıyor ve en küçük iller seçiliyor (bkz. IL_ONCELIGI).
            skor += 0.12 * self._il_agirligi(dilim)
            if sehirli:
                skor += 0.5
            puanli.append((skor, y))
        puanli.sort(key=lambda x: -x[0])
        secilen = self._yol_sec(puanli, sehir_d)

        # SEKTÖR SAYFASINA AYRI KOTA. Sektör yolu ("otomasyon") pozisyon yolundan
        # ("otomasyon+muhendisi") her zaman düşük skor alır — ortak sözcük oranı
        # daha küçük — ve normal sıralamada listeye hiç giremiyor. Oysa kapsamı
        # asıl genişleten o: pozisyon adına bağlı kalmadan tüm sektörü tarıyor.
        sektorler = set(self._sektor_yollari())
        # Seçilenler arasında ZATEN sektör varsa ikincisine gerek yok.
        if not any(y in sektorler for y in secilen):
            en_iyi = puanli[0][0] if puanli else 0.0
            # ALAKA EŞİĞİ: eşiksiz bırakılınca tek ortak sözcükle alakasız sektör
            # geliyordu ("savunma sanayi" -> "boru+sanayi", ortak sözcük: sanayi).
            for skor, y in puanli:
                if y in sektorler and y not in secilen and skor >= en_iyi * 0.42:
                    # İKİNCİ SIRAYA: istek bütçesi sınırlı ve sayfalar sırayla çekiliyor
                    # (bkz. cek_coklu). Sektör sayfası tüm firmaları verdiği için il
                    # sayfalarından değerli; sona eklenince bütçe ona hiç yetmiyordu.
                    secilen.insert(1 if secilen else 0, y)
                    break
        return [urljoin(self.KOK, y) for y in secilen]

    # Sorgu başına çekilecek liste sayfası sayısı. ÖLÇÜLDÜ (14 Eyl 2026): sınır 2
    # iken tüm tarama kariyer.net'ten yalnız 329 ilan getiriyordu ve kısa listenin
    # %98'i bu panodan geliyordu — yani en değerli kaynak en dar olanıydı.
    #
    # NEDEN SAYFALAMA DEĞİL ŞEHİR: kariyer.net kategori sayfaları sayfalanmıyor
    # (sitemap'in 60.441 yolunda tek bir sayfa parametresi yok); her kategori ilk
    # ~50 ilanı gösteriyor. Ama sitemap AYNI pozisyonun İL BAZLI sayfalarını ilan
    # ediyor: "otomasyon mühendisi" için 125, "savunma sanayi" için 74 yol var ve
    # bunlar FARKLI ilanlar taşıyor. Kapsamı artırmanın robots-izinli yolu bu.
    YOL_UST_SINIR = 4
    ISTEK_MALIYETI_NOTU = "her yol 1 istek = ~4 sn; sınır TEMKİNLİ tutuldu — 14 Eyl 2026'da\n    # üst üste gelen testler + tarama panodan 6 saatlik engel yedi."

    # İş hacmine göre il önceliği. NEDEN GEREKLİ: skorlar eşit olduğunda liste
    # ALFABETİK sıralanıyordu ve seçilen iller "adana, adıyaman, afyon, ağrı,
    # aksaray" oluyordu — ilan sayısı en düşük iller. Bu sıra, Türkiye'de sanayi
    # ve teknoloji istihdamının gerçekte yoğunlaştığı illeri öne alır.
    # Kırıkkale ve Eskişehir listede yüksekte: savunma sanayii oralarda (MKE, TUSAŞ).
    IL_ONCELIGI = ["istanbul", "ankara", "izmir", "bursa", "kocaeli", "eskisehir",
                   "kirikkale", "konya", "kayseri", "antalya", "adana", "gaziantep",
                   "manisa", "tekirdag", "sakarya", "denizli", "mersin", "aydin",
                   "balikesir", "hatay", "samsun", "trabzon"]

    def _il_agirligi(self, dilim: str) -> float:
        """Yol dilimindeki ilin öncelik bonusu (0 = listede yok)."""
        for sira, il in enumerate(self.IL_ONCELIGI):
            if dilim.startswith(il):
                return 1.0 - sira / (len(self.IL_ONCELIGI) * 1.5)
        return 0.0

    # Pozisyon adı bu eklerle biter. Sektör sayfaları bitmez ("otomasyon",
    # "savunma+sanayi", "bankacilik"). Bu, elle sektör listesi tutmamak için
    # kullanılan TEK dil kuralıdır — sektörlerin kendisi sitemap'ten türetilir,
    # yani site yeni bir sektör açarsa kod değişmeden gelir.
    POZISYON_EKLERI = ("muhendisi", "muhendis", "uzmani", "uzman", "elemani", "sorumlusu",
                       "muduru", "mudur", "sefi", "sef", "teknisyeni", "teknikeri",
                       "operatoru", "temsilcisi", "danismani", "yoneticisi", "yonetmeni",
                       "asistani", "gorevlisi", "ustasi", "isci", "personeli", "amiri",
                       "lideri", "direktoru", "koordinatoru", "analisti", "yardimcisi",
                       "ogretmeni", "memuru", "yetkilisi", "sorumlu", "programcisi")

    def _sektor_yollari(self) -> list[str]:
        """Sitemap'te ilan edilen SEKTÖR sayfaları — türetilir, elle yazılmaz.

        NEDEN: pozisyon sorgusu ("otomasyon mühendisi") yalnız o unvanı getiriyor.
        Sektör sayfası ("otomasyon", "bankacilik", "savunma+sanayi") o sektördeki
        TÜM firmaların ilanlarını veriyor — bankalar, sigortacılar, fabrikalar
        dahil. Türkiye'de binlerce şirket var; elle şirket ya da sektör listesi
        tutmak ölçeklenmiyor, bu yüzden sitemap'ten çıkarılıyor.

        İKİ KURAL, ikisi de veriden:
          1) şehirsiz + pozisyon eki taşımıyor + en çok 3 sözcük,
          2) ALTINDA pozisyon yolları var. Gerçek bir sektörün altında sitemap'te
             çok sayıda unvan bulunur ("otomasyon" -> "otomasyon+muhendisi",
             "otomasyon+teknikeri", "elektrik+otomasyon+muhendisi"); bir unvanın
             altında bulunmaz. Bu ikinci kural olmadan "makine+enspektoru" gibi
             ek listesine yazılmamış unvanlar sektör sanılıyordu — ve ek listesini
             büyütmek çözüm değil, her yeni unvan için elle bakım demek.
        """
        import functools
        return self._sektor_hesapla(tuple(self._kanonik_yollar()))

    @functools.lru_cache(maxsize=4)
    def _sektor_hesapla(self, yollar: tuple) -> list[str]:
        dilimler = [y.rsplit("/", 1)[-1] for y in yollar]
        adaylar = []
        for y, dilim in zip(yollar, dilimler):
            if "-" in dilim or dilim.endswith(self.POZISYON_EKLERI):
                continue
            if len(dilim.split("+")) > 3:
                continue
            adaylar.append((y, dilim))
        # Her aday için: altında kaç pozisyon yolu var?
        onek = {}
        for d in dilimler:
            kok = d.split("-")[-1]                       # şehir önekini at
            for a in ("+",):
                pass
            onek[kok] = onek.get(kok, 0)
        sayac: dict[str, int] = {}
        for d in dilimler:
            kok = d.split("-")[-1]
            parca = kok.split("+")
            for i in range(1, len(parca)):
                sayac[("+".join(parca[:i]))] = sayac.get("+".join(parca[:i]), 0) + 1
        return [y for y, d in adaylar if sayac.get(d, 0) >= 3]

    def _yol_sec(self, puanli: list[tuple[float, str]], sehir_d: str) -> list[str]:
        """Ülke geneli + farklı illerden en iyi yollar.

        İki kural:
          1) ŞEHİRSİZ (ülke geneli) yol varsa MUTLAKA alınır — en geniş havuz odur.
          2) Aynı ilden ikinci bir yol alınmaz; yoksa liste "istanbul+asya-...",
             "istanbul+asya-pendik-..." gibi aynı şehrin varyantlarıyla dolup
             kapsama hiçbir şey katmıyor (ölçüldü: gömülü yazılım sorgusunda ilk
             4 yolun 3'ü İstanbul Asya'ydı).
        """
        if not puanli:
            return []
        # ÜLKE GENELİ ÖNCE. İl bonusu eklendikten sonra şehir yolları öne geçiyor ve
        # şehirsiz (tüm Türkiye) sayfa 7'lik sınıra hiç giremiyordu — oysa en geniş
        # havuz odur. Sıralamadan bağımsız olarak başa alınır.
        en_iyi = puanli[0][0]
        genel = next((y for sk, y in puanli if "-" not in y.rsplit("/", 1)[-1]), None)
        secilen: list[str] = [genel] if genel else []
        gorulen_il: set[str] = set()
        for skor, yol in puanli:
            if yol == genel:
                continue
            # ALAKA EŞİĞİ: en iyi yolun belirgin altındaki yollar sorgunun konusundan
            # uzaklaşıyor ("gömülü yazılım mühendisi" -> "yazılım mühendisi"). Bunları
            # çekmek hem gereksiz istek hem alakasız ilan demek.
            if skor < en_iyi * 0.72:
                continue
            dilim = yol.rsplit("/", 1)[-1]
            il = dilim.split("-")[0] if "-" in dilim else ""
            if il and il in gorulen_il:
                continue
            if il:
                gorulen_il.add(il)
            secilen.append(yol)
            if len(secilen) >= self.YOL_UST_SINIR:
                break
        return secilen

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
        h = self._sayfa(job.url, DETAY_OMRU_SN)
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
    saatlik_butce = 40               # Cloudflare arkasında; 4 sn arayla, tek liste sayfası
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
        h = self._sayfa(job.url, DETAY_OMRU_SN)
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
