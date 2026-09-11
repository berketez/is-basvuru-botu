#!/usr/bin/env python3
"""Regresyon testleri — bugün düzeltilen her hata için bir test.

Amaç: bu hatalar bir daha sessizce geri gelmesin. Her testin başlığında hatanın
ne olduğu ve neye yol açtığı yazıyor. Ağ erişimi YOK, saniyeler içinde koşar.

    python tests/test_regresyon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from isbot.experience import metin_normalize, tahmin
from isbot.ghost import degerlendir
from isbot.models import Job
from isbot.pipeline import _varyant_anahtari, tekilleştir
from isbot.scoring import _istenen_yil, _konum_degerlendir, _yetenek_ara

GECTI = BASARISIZ = 0
HATALAR: list[str] = []


def sina(ad: str, beklenen, cikan) -> None:
    global GECTI, BASARISIZ
    if beklenen == cikan:
        GECTI += 1
    else:
        BASARISIZ += 1
        HATALAR.append(f"  {ad}\n     beklenen: {beklenen!r}\n     çıkan   : {cikan!r}")


def ilan(**kw) -> Job:
    varsayilan = dict(source="test", company="ACME", board_token="acme", native_id="1",
                      title="Software Engineer", url="u", locations=[], description="")
    varsayilan.update(kw)
    return Job(**varsayilan)


# ---------------------------------------------------------------- 1
# HATA: CV'deki en eski yıl kariyer başlangıcı sayılıyordu; lise başlangıç yılını
# yakalayıp yeni mezunu 10 yıllık gösteriyordu.
def t1_lise_yili_kariyer_sanilmasin():
    cv = """Experience
AI Intern, BigCo                                  Summer 2025
Education
B.Sc. Computer Engineering, Üniversite            2020 -- 2026
High School Diploma                               2016 -- 2020"""
    d = tahmin(cv)
    sina("1. lise yılı kariyer başlangıcı sayılmamalı (<1 yıl beklenir)",
         True, d.profesyonel_yil < 1.0)


# ---------------------------------------------------------------- 2
# HATA: Kariyerine liseden sonra başlayan, üniversite okumamış kişide mezuniyet
# yılına dayanan kural çöküyordu.
def t2_universitesiz_kariyer():
    cv = """Experience
Senior Backend Developer, Acme Corp    Jan 2021 -- Present
Backend Developer, StartupX            Jun 2017 -- Dec 2020
Junior Developer, WebShop Ltd          Sep 2015 -- May 2017
Education
High School Diploma                    2011 -- 2015"""
    d = tahmin(cv)
    sina("2. üniversitesiz, liseden başlayan kariyer (>9 yıl beklenir)",
         True, d.profesyonel_yil > 9.0)


# ---------------------------------------------------------------- 3
# HATA: Gerçek işteki "Team Lead" unvanı gönüllü/kulüp sanılıp deneyimden düşülüyordu.
def t3_gercek_takim_lideri_dusulmesin():
    cv = """Experience
Engineering Team Lead, RealCo    Jan 2019 -- Present
Education
BSc CS 2014 -- 2018"""
    sina("3. gerçek işteki 'Team Lead' düşülmemeli (>6 yıl)",
         True, tahmin(cv).profesyonel_yil > 6.0)


# ---------------------------------------------------------------- 4
# HATA: PDF metin çıkarımı satırı sayının ortasında kesiyordu ("May 202\n0");
# 4 haneli yıl bulunamadığı için o iş hiç sayılmıyordu (12,8 yıl -> 6,2 yıl).
def t4_pdf_bolunmus_yil():
    bozuk = "Junior Security Analyst        Aug 2016 -- May 202\n0\nSOC Defenders"
    sina("4. bölünmüş yıl onarılmalı", True, "May 2020" in metin_normalize(bozuk))
    cv = """Experience
Analyst, X    Aug 2016 -- May 202
0
Education
High School  2011 -- 2013"""
    # Bu CV'de tek iş var: Ağu 2016 - May 2020 = ~3,75 yıl. Onarım OLMAZSA aralık hiç
    # bulunmaz ve 0 çıkar; onarım olursa ~3,7 bulunur. Test bunu ayırt eder.
    sina("4b. onarım sonrası aralık sayılmalı (~3,7 yıl)",
         True, 3.0 < tahmin(cv).profesyonel_yil < 4.5)


# ---------------------------------------------------------------- 5
# HATA: "we have 40 years of experience" (şirketin kendi övgüsü) adaydan istenen
# deneyim sanılıyor, ilan haksız yere eleniyordu.
def t5_sirket_ovgusu_sart_sanilmasin():
    sina("5. şirket övgüsü şart sayılmamalı",
         None, _istenen_yil(ilan(description="Founded in 1985, we have 40 years of experience.")))
    sina("5b. gerçek şart okunmalı",
         5, _istenen_yil(ilan(description="Requirements: 5+ years of experience with Python.")))
    sina("5c. 'at least N yıl' okunmalı",
         3, _istenen_yil(ilan(description="You will have at least 3 years of experience in ML.")))


# ---------------------------------------------------------------- 6
# HATA: ATS'in isRemote bayrağı "dünyanın her yerinden" sanılıyordu; oysa
# "Tokyo, Japan" ve "Washington, DC" ilanlarında da açık. Kısa liste Türkiye'den
# başvurulamayacak ABD/Japonya ilanlarıyla doluyordu.
def t6_ulkeye_civilenmis_remote():
    izin = ["turkey", "remote_global", "remote_emea"]
    _, uygun = _konum_degerlendir(ilan(locations=["Washington, DC"], remote_flag=True), izin)
    sina("6. remote bayraklı ABD ilanı uygun SAYILMAMALI", False, uygun)
    _, uygun = _konum_degerlendir(ilan(locations=["Tokyo, Japan"], remote_flag=True), izin)
    sina("6b. remote bayraklı Japonya ilanı uygun SAYILMAMALI", False, uygun)
    _, uygun = _konum_degerlendir(ilan(locations=["Germany (Remote)"], remote_flag=True), izin)
    sina("6c. Almanya'ya çivilenmiş remote uygun SAYILMAMALI", False, uygun)
    _, uygun = _konum_degerlendir(ilan(locations=["Worldwide"], remote_flag=True), izin)
    sina("6d. 'Worldwide' uygun sayılmalı", True, uygun)
    _, uygun = _konum_degerlendir(ilan(locations=["Istanbul, Turkey"]), izin)
    sina("6e. Türkiye uygun sayılmalı", True, uygun)
    _, uygun = _konum_degerlendir(ilan(locations=["EMEA"], remote_flag=True), izin)
    sina("6f. EMEA uygun sayılmalı", True, uygun)


# ---------------------------------------------------------------- 7
# HATA: Belirsizlikte kapı açıktı; kapsamı doğrulanamayan "remote" ilan kabul
# ediliyordu. Artık fail-closed.
def t7_belirsiz_kapsam_reddedilir():
    _, uygun = _konum_degerlendir(
        ilan(locations=["Remote"], remote_flag=True, description="Join our team."),
        ["turkey", "remote_global", "remote_emea"])
    sina("7. kapsamı doğrulanamayan remote reddedilmeli", False, uygun)


# ---------------------------------------------------------------- 8
# HATA: "Excel" fiili ("candidates who excel at...") yetenek sayılıyordu;
# 1500 ilanın %62'sinde sahte eşleşme üretiyordu.
def t8_belirsiz_kelime_buyuk_kucuk_duyarli():
    sina("8. 'excel' fiili Excel yeteneği sayılmamalı",
         False, _yetenek_ara("Candidates who excel at communication", "Excel"))
    sina("8b. gerçek 'Excel' sayılmalı",
         True, _yetenek_ara("Advanced Microsoft Excel required", "Excel"))
    sina("8c. 'go to the office' Go dili sayılmamalı",
         False, _yetenek_ara("you will go to the office twice a week", "Go"))


# ---------------------------------------------------------------- 9
# HATA: Ülke eki başlığın ORTASINDA olabiliyordu ("X | Germany | Remote") ve
# ayraç sınıfında "|" yoktu; Grafana'nın tek ilanı 5 satır görünüyordu.
def t9_ulke_varyanti_tekillestirme():
    j = [ilan(native_id=str(i), title=f"Senior Backend Engineer - Databases | {u} | Remote")
         for i, u in enumerate(["Germany", "Ireland", "Spain", "Sweden", "UK"])]
    sina("9. ülke varyantları tek ilana inmeli", 1, len(tekilleştir(j)))
    sina("9b. sonda ülke eki de temizlenmeli",
         _varyant_anahtari(ilan(title="Deployment Strategist - Italy")),
         _varyant_anahtari(ilan(title="Deployment Strategist")))


# ---------------------------------------------------------------- 10
# HATA: Tekilleştirme anahtarı board_token içeriyordu; aynı ilan farklı arama
# sorgusuyla gelince (remotive:qa vs remotive:game) 3 kez listeye giriyordu.
def t10_farkli_token_ayni_ilan():
    a = ilan(board_token="remotive:qa", native_id="1", company="Lemon.io", title="Senior QA Engineer")
    b = ilan(board_token="remotive:game", native_id="2", company="Lemon.io", title="Senior QA Engineer")
    sina("10. aynı şirket+başlık farklı token ile tek sayılmalı", 1, len(tekilleştir([a, b])))


# ---------------------------------------------------------------- 11
# HATA: Tekilleştirmede "en taze" kopya tutuluyordu; kısa/kesik metinli kopya
# seçilince yetenekler görünmüyor ve en iyi eşleşme "alakasız" damgası yiyordu.
def t11_zengin_metin_kazanir():
    kisa = ilan(native_id="1", title="AI Engineer", description="Kısa özet.")
    uzun = ilan(native_id="2", title="AI Engineer", description="Python, LLM, RAG " * 60)
    tutulan = tekilleştir([kisa, uzun])[0]
    sina("11. zengin metinli kopya tutulmalı", True, len(tutulan.description) > 500)
    tutulan2 = tekilleştir([uzun, kisa])[0]          # sıra fark etmemeli
    sina("11b. giriş sırası sonucu değiştirmemeli", True, len(tutulan2.description) > 500)


# ---------------------------------------------------------------- 12
# HATA: Yaş cezası düzdü; 5 yıllık kalıcı vitrin ilanı yalnızca "şüpheli" sayılıyordu.
def t12_yas_kademeleri():
    from datetime import datetime, timedelta, timezone
    def yasli(gun):
        return ilan(posted_at=datetime.now(timezone.utc) - timedelta(days=gun))
    sina("12. 5 gün -> taze", "taze", degerlendir(yasli(5)).bant)
    sina("12b. 1900 gün -> hayalet", "hayalet", degerlendir(yasli(1900)).bant)
    sina("12c. 800 gün -> hayalet", "hayalet", degerlendir(yasli(800)).bant)
    sina("12d. havuz ilanı başlıktan yakalanmalı", "hayalet",
         degerlendir(ilan(title="[Expression of Interest] Research Engineer",
                          posted_at=datetime.now(timezone.utc) - timedelta(days=500))).bant)


# ---------------------------------------------------------------- 13
# HATA: Ayrıştırıcıyı canlı siteye karşı test etmek. Onlarca ayrı test süreci
# koşunca süreç-içi hız sınırı sayacı her seferinde sıfırlandı, gerçek istek hızı
# yükseldi ve kariyer.net 403 verdi (11 Eyl 2026). Artık ayrıştırıcı testleri
# KAYDEDİLMİŞ SAYFALARLA çalışıyor; canlı siteye hiç dokunmuyor.
def t13_tr_ayristirici_ornekten():
    import os
    import socket
    if not (Path(__file__).parent / "ornekler").exists():
        return                                    # örnek yoksa test atlanır
    os.environ["ISBOT_ORNEK"] = "oku"
    import importlib
    import isbot.sources.tr_panolar as tp
    importlib.reload(tp)

    gercek = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("ağa çıkıldı"))
    try:
        e = tp.ElemanNet()
        js = e.cek()
        sina("13. örnekten ilan okunmalı (ağ kapalı)", True, len(js) > 10)
        n = e.detaylari_cek(js, ust_sinir=3)
        sina("13b. örnekten detay okunmalı", 3, n)
        dolu = [j for j in js if j.raw.get("detay_cekildi")]
        sina("13c. detayda şirket adı çıkmalı", True,
             all(j.company and j.company != "?" for j in dolu))
        sina("13d. detayda tarih çıkmalı", True, all(j.posted_at for j in dolu))
        sina("13e. yaş negatif olmamalı (saat dilimi)", True,
             all((j.age_days or 0) >= 0 for j in dolu))
    finally:
        socket.socket.connect = gercek
        os.environ.pop("ISBOT_ORNEK", None)
        importlib.reload(tp)


# ---------------------------------------------------------------- 14
# HATA: Uygulama Finder'dan çift tıklanınca Dock simgesi sonsuza kadar zıplıyor,
# panel hiç açılmıyordu. Sebeplerden biri: webbrowser.open() macOS'ta osascript'e
# Apple Event yollar; masaüstünden açılan imzasız .app'in bu izni yoktur, istek
# sessizce düşer. Terminalden çalışınca izin Terminal'e ait olduğu için sorun
# görünmüyordu. Çözüm /usr/bin/open (LaunchServices, izin istemez).
def t14_tarayici_apple_event_ile_acilmasin():
    import isbot.server as sunucu

    sina("14a. webbrowser modül düzeyinde içe aktarılmamalı",
         False, "webbrowser" in vars(sunucu))

    cagrilan: list = []

    class SahteSurec:
        def __init__(self, komut, **kw):
            cagrilan.append(komut)

    gercek = sunucu.subprocess.Popen
    sunucu.subprocess.Popen = SahteSurec
    try:
        sonuc = sunucu.tarayicida_ac("http://127.0.0.1:8733/")
    finally:
        sunucu.subprocess.Popen = gercek

    if sys.platform == "darwin":
        sina("14b. macOS'ta /usr/bin/open kullanılmalı",
             ["/usr/bin/open", "http://127.0.0.1:8733/"], cagrilan[0] if cagrilan else None)
        sina("14c. açma başarılı raporlanmalı", True, sonuc)


# ---------------------------------------------------------------- 15
# HATA: İkinci çift tıklama ikinci bir sunucu başlatıyordu (8733 dolu -> 8734).
# İki ayrı panel, iki ayrı tarama durumu demekti. Tekil sürüm denetimi portta
# koşanın BİZ olduğumuzu /api/saglik künyesinden anlar; künye silinirse denetim
# sessizce bozulur ve hata geri gelir.
def t15_saglik_kunyesi_durmali():
    from isbot.server import app as web

    with web.test_client() as istemci:
        veri = istemci.get("/api/saglik").get_json()
    sina("15a. /api/saglik künye taşımalı", "isbasvurubotu", veri.get("uygulama"))
    sina("15b. sağlık alanı durmalı", True, "saglikli" in veri)


# ---------------------------------------------------------------- 16
# HATA: Salt Flask koşan süreç LaunchServices'e kaydolmuyordu (lsappinfo bomboş),
# Dock da "açıldım" sinyalini bekleyip sonsuza kadar zıplıyordu. Çözüm ana
# thread'de NSApplication çalıştırmak. ctypes köprüsü bozulursa uygulama yine
# çalışır ama zıplama geri gelir -- bu yüzden köprü ayrıca sınanıyor.
def t16_cocoa_koprusu_ayakta():
    import uygulama as giris

    if sys.platform != "darwin":
        return
    objc, gonder = giris._objc_kur()
    sina("16a. libobjc + AppKit bağlanmalı", True, objc is not None)
    if objc is None:
        return
    sinif = objc.objc_getClass(b"NSApplication")
    sina("16b. NSApplication sınıfı bulunmalı", True, bool(sinif))
    # sharedApplication ÇAĞRILMIYOR: test sürecini Dock uygulamasına çevirirdi.
    sina("16c. selector kaydı çalışmalı", True,
         bool(objc.sel_registerName(b"finishLaunching")))


# ---------------------------------------------------------------- 17
# HATA: Arayüzde ABD / BK / Almanya diye ÜÇ sabit kutu vardı; motor ise onlarca
# ülkeyi tanıyordu. İsviçre'de (ya da Hollanda, Kanada…) çalışma izni olan
# kullanıcı bunu hiçbir yere yazamadığı için o ilanlar "izin yok" diye eleniyor,
# elinde düzeltme imkânı olmuyordu. İki yan hata daha çıktı:
#   * "Germany (Remote)" parantez ayraç sayılmadığı için HİÇBİR ülkeye çözülmüyordu
#     (Almanya izni olan kullanıcıda bile "ofis: Germany (Remote)" diye eleniyordu),
#   * yalnız şehirle yazılmış ilan ("Zurich") ülkeye bağlanamıyordu.
def t17_dinamik_ulke_izni():
    _, uygun = _konum_degerlendir(ilan(locations=["Zurich"]), ["switzerland"])
    sina("17. İsviçre izni varken Zürih ilanı geçmeli", True, uygun)
    _, uygun = _konum_degerlendir(ilan(locations=["Zurich"]), ["turkey"])
    sina("17b. İsviçre izni yokken geçmemeli", False, uygun)
    _, uygun = _konum_degerlendir(ilan(locations=["Germany (Remote)"], remote_flag=True),
                                  ["germany"])
    sina("17c. 'Germany (Remote)' Almanya iznine çözülmeli", True, uygun)
    _, uygun = _konum_degerlendir(ilan(locations=["Amsterdam"]), ["netherlands"])
    sina("17d. şehirle yazılmış Hollanda ilanı geçmeli", True, uygun)
    durum, _ = _konum_degerlendir(ilan(locations=["Amsterdam"]), ["netherlands"])
    sina("17e. ülke adı Türkçe yazılmalı", True, "Hollanda" in durum)


# ---------------------------------------------------------------- 18
# HATA (aynı kök): arayüzün ülke listesi elle yazıldığı için motordan kopuktu.
# Artık /api/ulkeler motorun kataloğunu döndürür; tek yerde ülke eklenir.
def t18_ulke_ucu():
    from isbot.scoring import ULKE_ADI
    from isbot.server import app as web

    with web.test_client() as istemci:
        liste = istemci.get("/api/ulkeler").get_json()
    etiket = {u["etiket"] for u in liste}
    sina("18. uç motorun kataloğunu döndürmeli", True, len(liste) >= 50)
    sina("18b. İsviçre listede olmalı", True, "switzerland" in etiket)
    sina("18c. Türkiye listede OLMAMALI (kendi kutusu var)", False, "turkey" in etiket)
    sina("18d. her kayıt Türkçe ad + bölge taşımalı", True,
         all(u["ad"] and u["bolge"] for u in liste))
    sina("18e. uç ile katalog aynı olmalı", set(ULKE_ADI) - {"turkey"}, etiket)


# ---------------------------------------------------------------- 19
# HATA: Türkiye işaretlenince listede yalnızca "Türkiye" yazıyordu; ilanın
# İstanbul ofisi mi yoksa ülke içinden uzaktan mı olduğu karttan anlaşılmıyordu.
def t19_turkiye_ilaninda_sehir():
    durum, _ = _konum_degerlendir(ilan(locations=["Istanbul, Turkey"]), ["turkey"])
    sina("19. TR ilanında şehir görünmeli", "Türkiye · İstanbul", durum)
    durum, _ = _konum_degerlendir(ilan(locations=["Turkey"]), ["turkey"])
    sina("19b. şehir yoksa yalnız ülke yazmalı", "Türkiye", durum)


# ---------------------------------------------------------------- 20
# HATA: Konum alanı "Remote, Global" / "Distributed, Global" / "Remote - Global"
# yazan ilanlar ülkeye de çözülemediği için "ofis: Remote, Global" deyip ELENİYORDU.
# Ölçüldü: 10.928 ilanlık havuzda 96 ilan bu yüzden kayboluyordu — hepsi de tam olarak
# Türkiye'den başvurulabilecek ilanlar.
def t20_global_konum_beyani():
    izin = ["turkey", "remote_global", "remote_emea"]
    for alan in ("Remote, Global", "Distributed, Global", "Remote - Global", "Global",
                 "Anywhere", "Remote (Global)", "Worldwide"):
        durum, uygun = _konum_degerlendir(ilan(locations=[alan], remote_flag=True), izin)
        sina(f"20. '{alan}' global sayılmalı", True, uygun)
    # Başlıkta geçen "Global" konum beyanı SAYILMAZ (yanlış pozitif koruması)
    _, uygun = _konum_degerlendir(
        ilan(locations=["New York"], title="Global Head of Sales"), izin)
    sina("20b. başlıktaki 'Global' konum beyanı sayılmamalı", False, uygun)


# ---------------------------------------------------------------- 21
# HATA: Tire ayraç sayılmadığı için "Remote - United States", "US - Remote Zone 1",
# "Remote - California" gibi 1.498 ilan HİÇBİR ülkeye çözülmüyordu. Sonuç aynıydı
# (eleniyorlardı) ama sebep yanlıştı: ABD çalışma izni eklenince de gelmiyorlardı.
def t21_tireli_ve_coklu_ulke():
    _, uygun = _konum_degerlendir(ilan(locations=["Remote - United States"]), ["usa"])
    sina("21. 'Remote - United States' ABD iznine çözülmeli", True, uygun)
    _, uygun = _konum_degerlendir(
        ilan(locations=["US - Remote Zone 1 (Job Requisitions Only)"]), ["usa"])
    sina("21b. 'US - Remote Zone 1' ABD sayılmalı", True, uygun)
    _, uygun = _konum_degerlendir(ilan(locations=["Remote - California"]), ["usa"])
    sina("21c. eyalet tam adı ABD sayılmalı", True, uygun)
    # Tek konum satırı BİRDEN ÇOK ülke taşıyabilir; biri yeterli.
    for izin in (["usa"], ["canada"]):
        _, uygun = _konum_degerlendir(ilan(locations=["United States & Canada"]), izin)
        sina(f"21d. 'United States & Canada' {izin[0]} iznine uymalı", True, uygun)
    _, uygun = _konum_degerlendir(ilan(locations=["North America"]), ["canada"])
    sina("21e. 'North America' bölgesi çözülmeli", True, uygun)
    # Tire ŞEHİR ADININ İÇİNDE olabilir; bölme onu bozmamalı.
    _, uygun = _konum_degerlendir(ilan(locations=["Tel Aviv-Yafo"]), ["israel"])
    sina("21f. 'Tel Aviv-Yafo' İsrail sayılmalı", True, uygun)


# ---------------------------------------------------------------- 22
# HATA: "ilanın istediği ama CV'de zayıf" kutusu HİÇ dolmuyordu. Kontrol `elif` idi:
# önce ilanın TAMAMINDA aranıyor, bulunamazsa aynı metnin ALT KÜMESİNDE aranıyordu —
# mantıken imkânsız. Ölçüldü: 24 adayın 24'ünde kutu boştu.
def t22_eksik_yetenek_dolar():
    from isbot.scoring import puanla

    profil = {
        "sert_filtreler": {"zorunlu_konum_kosulu": ["remote_global"], "max_kidem": "senior"},
        "rol_aileleri": {"ml": {"basliklar": [r"(?i)\bml engineer\b"], "agirlik": 1.0}},
        "yetenekler": {"guclu": {"Python": 1.0}, "zayif": {"Kubernetes": 0.4}},
    }
    j = ilan(title="ML Engineer", locations=["Worldwide"], remote_flag=True,
             description="You will use Python daily. Kubernetes experience is required.")
    p = puanla(j, profil)
    sina("22. zayıf yetenek ilanda geçiyorsa 'eksik' listelenmeli",
         True, "Kubernetes" in p.eksik_yetenekler)
    sina("22b. zayıf yetenek eşleşen listesine de girmeli",
         True, any("Kubernetes" in x for x in p.eslesen_yetenekler))


# ---------------------------------------------------------------- 23
# HATA: Eleme gerekçesi kalıbı ters bölü ile bölüyordu; sonuç HER ZAMAN "(?i)" idi,
# yani hangi sözcüğün elediği hiç yazmıyordu.
def t23_eleme_gerekcesi_sozcuk_yazar():
    from isbot.scoring import puanla

    profil = {"sert_filtreler": {"yasakli_baslik_kaliplari": [r"(?i)\b(recruiter|sales)\b"]}}
    p = puanla(ilan(title="Technical Recruiter"), profil)
    sina("23. eleme gerekçesi eşleşen sözcüğü yazmalı", True, "Recruiter" in p.eleme_sebebi)
    sina("23b. gerekçede ham kalıp olmamalı", False, "(?i)" in p.eleme_sebebi)


# ---------------------------------------------------------------- 24
# HATA: Kapanan ilan sorgusuna board_token yerine ŞİRKET ADI gidiyordu
# ("Databricks" ↔ "databricks"), hiçbir satır eşleşmiyordu: "kapandı" işareti ve
# ona dayanan yeniden-yayım sinyali sessizce ölüydü.
def t24_kapanan_ilan_isaretlenir():
    import tempfile

    from isbot.store import Depo

    with tempfile.TemporaryDirectory() as gecici:
        depo = Depo(Path(gecici) / "t.db")
        eski = ilan(native_id="1", title="Data Engineer", board_token="databricks")
        r1 = depo.kosu_baslat("t1")
        depo.kaydet(eski, r1)
        depo.commit()
        r2 = depo.kosu_baslat("t2")          # ikinci koşuda ilan artık yok
        n = depo.kapananlari_isaretle(r2, ["databricks"])
        sina("24. artık görünmeyen ilan kapandı sayılmalı", 1, n)
        sina("24b. şirket ADIYLA çağrılırsa hiçbir şey kapanmamalı",
             0, depo.kapananlari_isaretle(r2, ["Databricks"]))
        depo.close()


# ---------------------------------------------------------------- 25
# HATA: cv_import.py'de SABIT_ELEME_LISTESI / motor_surumu / _kidem_ustu_kaliplar
# İKİŞER KEZ tanımlıydı (48 satırlık kopya blok). İkinci tanım birinciyi gölgeliyor,
# yani ilk bloktaki düzeltmeler sessizce hiç çalışmıyordu.
def t25_kopya_tanim_yok():
    import ast
    import collections

    kok = Path(__file__).resolve().parent.parent
    for dosya in sorted(kok.glob("isbot/**/*.py")):
        agac = ast.parse(dosya.read_text(encoding="utf-8"))
        sayac: collections.Counter = collections.Counter()
        for d in agac.body:
            if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                sayac[d.name] += 1
            elif isinstance(d, ast.Assign):
                for h in d.targets:
                    if isinstance(h, ast.Name):
                        sayac[h.id] += 1
        tekrar = [k for k, v in sayac.items() if v > 1]
        sina(f"25. {dosya.name}: tekrar eden üst düzey tanım olmamalı", [], tekrar)


# ---------------------------------------------------------------- 26
# HATA: İlan metnindeki "hybrid" sözcüğü konum alanındaki "Remote" beyanını eziyordu.
# "This is a hybrid technical and commercial role" cümlesi çalışma şekli değil ROL
# tarifi; buna rağmen 301 ilan HİBRİT etiketlenip "uzaktan" filtresinde kayboluyordu.
def t26_hybrid_sozcugu_remote_beyanini_ezmez():
    from isbot.siniflandir import calisma_sekli

    sina("26. metindeki 'hybrid ... role' uzaktanlığı bozmamalı", "uzaktan",
         calisma_sekli(ilan(locations=["Remote - California"],
                            description="This is a hybrid technical and commercial role.")))
    sina("26b. gerçek hibrit düzen hibrit sayılmalı", "hibrit",
         calisma_sekli(ilan(locations=["Istanbul"],
                            description="Hybrid work model: 3 days a week in the office.")))
    sina("26c. konum alanındaki 'Hybrid' beyanı geçerli", "hibrit",
         calisma_sekli(ilan(locations=["Berlin (Hybrid)"], description="Great team.")))
    sina("26d. 'fully remote' metni uzaktan sayılmalı", "uzaktan",
         calisma_sekli(ilan(locations=["Istanbul"],
                            description="We are a fully remote company.")))


def main() -> int:
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("t") and callable(v)
               and k[1].isdigit()]:
        fn()
    print(f"\n{GECTI} geçti, {BASARISIZ} başarısız")
    if HATALAR:
        print("\nBAŞARISIZ:")
        for h in HATALAR:
            print(h)
    return 1 if BASARISIZ else 0


if __name__ == "__main__":
    sys.exit(main())
