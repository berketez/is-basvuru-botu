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


# ---------------------------------------------------------------- 27
# Türkçe PDF'lerde pdftotext harfleri AYRIŞTIRILMIŞ (NFD) veriyor: "Ç" tek karakter
# değil, "C" + birleştirici çengel. Normalize edilmezse regex tabanı tek başına
# duran bir harf sanıyor. ÖLÇÜLDÜ: bir kontrol mühendisi CV'sinde "Gömülü/Görü/
# Gökkubbe" -> Go dili, "Çift/çalışma/Güç" -> C dili GÜÇLÜ yetenek çıktı; aday
# C/Go sistem programcısı sanıldı ve kısa listeye Ubuntu çekirdek ilanları geldi.
def t27_nfd_turkce_sahte_yetenek_uretmez():
    import unicodedata
    from isbot.cv_import import yetenek_tespit
    ham = ("Gömülü sistemler için C++ · Görüntü işleme · Gökkubbe Teknoloji\n"
           "Çift Anadal · çalışmalarım · Güç elektroniği · sensör füzyonu\n" * 3)
    nfd = unicodedata.normalize("NFD", ham)
    guclu, zayif = yetenek_tespit(nfd)
    bulunan = set(guclu) | set(zayif)
    sina("NFD metinde sahte 'Go' yok", False, "Go" in bulunan)
    sina("NFD metinde sahte 'C' yok", False, "C" in bulunan)
    sina("NFD metinde sahte 'R' yok", False, "R" in bulunan)
    sina("NFD metinde gerçek C++ bulunur", True, "C++" in bulunan)


# ---------------------------------------------------------------- 28
# Kelime sınırı (\b) Türkçe ekini ve İngilizce çoğulunu KESİYORDU. Sözlüğe terim
# eklenmiş görünüyor ama gerçek metinde hiç tutmuyordu — sessiz kayıp.
def t28_ek_ve_cogul_toleransi():
    from isbot.cv_import import _gecis_sayisi
    sina("'gömülü sistem' <- 'Gömülü sistemler'", 1,
         _gecis_sayisi("Gömülü sistemler için C++", "gömülü sistem"))
    sina("'kontrol sistemleri' <- 'sistemlerinde'", 1,
         _gecis_sayisi("Kontrol sistemlerinde deneyim", "kontrol sistemleri"))
    sina("'control system' <- 'control systems'", 1,
         _gecis_sayisi("control systems experience", "control system"))
    # Kısa terimler GENİŞLETİLMEZ: yoksa java->javascript, react->reactive olur.
    sina("'java' 'JavaScript'e yayılmaz", 0, _gecis_sayisi("JavaScript ile yazdım", "java"))
    sina("ilan tarafı: 'Java' 'JavaScript'e yayılmaz", False,
         _yetenek_ara("JavaScript developer", "Java"))
    sina("ilan tarafı: 'React' 'reactive'e yayılmaz", False,
         _yetenek_ara("reactive programming", "React"))


# ---------------------------------------------------------------- 29
# Türkiye tespiti YALNIZ 6 şehir tanıyordu (İstanbul/Ankara/İzmir/Eskişehir + ülke
# adı). ÖLÇÜLDÜ: savunma sanayii havuzunda Konya, Bursa, Gaziantep ve Kırıkkale
# ilanları "Türkiye değil" sayılıp konum filtresinde elendi — oysa Türkiye'de
# savunma sanayii tam olarak o şehirlerde.
def t29_turkiye_81_il():
    from isbot.scoring import TR_KALIP, _tr_yer
    for sehir in ["Konya", "Bursa", "Gaziantep", "Kırıkkale", "Kayseri", "Sanliurfa"]:
        sina(f"'{sehir}' Türkiye sayılır", True, bool(TR_KALIP.search(sehir)))
    sina("ASCII yazım da tanınır", " · Kırıkkale", _tr_yer(["Kirikkale, Turkey"]))
    sina("yabancı şehir Türkiye sayılmaz", False, bool(TR_KALIP.search("Berlin")))


# ---------------------------------------------------------------- 30
# Türkçede "kontrol" hem control-systems hem quality-control demek. ÖLÇÜLDÜ:
# kariyer.net "kontrol mühendisi" sorgusunun 51 sonucunun TAMAMI kalite kontrol /
# kontrol odası ilanıydı. Rol kalıbı bunları kontrol mühendisliği sanıyordu.
def t30_kalite_kontrol_ayrimi():
    import re
    import yaml as _y
    from isbot.yollar import kaynak_dosya
    from isbot.scoring import _alan_catismasi
    roller = _y.safe_load(kaynak_dosya("isbot", "data", "roller.yaml").read_text(encoding="utf-8"))
    ko = roller["kontrol_otomasyon"]["basliklar"][0]
    sina("'Kalite Kontrol Mühendisi' kontrol ailesine GİRMEZ", False,
         bool(re.search(ko, "Kalite Kontrol Mühendisi")))
    sina("'Kontrol Sistemleri Mühendisi' GİRER", True,
         bool(re.search(ko, "Kontrol Sistemleri Mühendisi")))
    sina("kalite kontrol ilanı alan çatışması sayılır", "kalite_kontrol",
         _alan_catismasi("Kalite Kontrol Mühendisi", {"kontrol_otomasyon", "havacilik_savunma"}))
    # "People Ops" KISALTMASI yakalanmıyordu; bir kontrol mühendisinin kısa
    # listesinde "People Ops Onboarding Specialist" 23,8 puanla duruyordu.
    sina("'People Ops' İK sayılır", "insan_kaynaklari",
         _alan_catismasi("People Ops Onboarding Specialist, EMEA", {"kontrol_otomasyon"}))


# ---------------------------------------------------------------- 31
# Uyum hakemi (gelişmiş arama) OPSİYONELDİR. Model yoksa ya da onnxruntime kurulu
# değilse motor eskisi gibi çalışmalı — import bile çökmemeli.
def t31_uyum_modulu_opsiyonel():
    from isbot import uyum
    hazir, sebep = uyum.kullanilabilir()
    sina("kullanilabilir() (bool, str) döner", True,
         isinstance(hazir, bool) and isinstance(sebep, str))
    # Profil cümlesi model olmasa da kurulabilmeli (saf metin işi).
    cumle = uyum.profil_cumlesi({"kimlik": {"deneyim_yil": 2.0},
                                 "yetenekler": {"guclu": {"control systems": 1.0}},
                                 "rol_aileleri": {"kontrol_otomasyon": {}}})
    sina("profil cümlesi Türkçe karşılığı da içerir", True, "kontrol sistemleri" in cumle)
    sina("profil cümlesi boş değil", True, len(cumle) > 40)


# ---------------------------------------------------------------- 32
# Sözlüğe 20 yazılım-dışı meslek alanı eklendi; rol ailesi olmadan yarım kalıyordu
# (yetenek tanınıyor, hedef rol yine genel_yazilim çıkıyordu).
def t32_yazilim_disi_meslekler():
    import re
    import yaml as _y
    from isbot.yollar import kaynak_dosya
    roller = _y.safe_load(kaynak_dosya("isbot", "data", "roller.yaml").read_text(encoding="utf-8"))

    def aile(baslik):
        return [ad for ad, t in roller.items() if any(re.search(k, baslik) for k in t["basliklar"])]

    for baslik, beklenen in [("Yoğun Bakım Hemşiresi", "saglik"),
                             ("Şantiye Şefi", "insaat"),
                             ("Ön Muhasebe Elemanı", "muhasebe"),
                             ("Lojistik Uzmanı", "lojistik"),
                             ("Avukat", "hukuk"),
                             ("Okul Öncesi Öğretmeni", "egitim")]:
        sina(f"'{baslik}' -> {beklenen}", True, beklenen in aile(baslik))
    # Yazılım tarafı bozulmamalı.
    sina("'Aviyonik Mühendisi' havacılık ailesinde", True,
         "havacilik_savunma" in aile("Aviyonik Mühendisi"))


# ---------------------------------------------------------------- 33
# Workable v3 `department`'ı LİSTE döndürmeye başladı (["T-Tech"]). Liste SQLite'a
# yazılamadı ve tek ilan bütün taramayı düşürdü: "Error binding parameter 10:
# type 'list' is not supported". Ayrıca tarih `published` anahtarına taşınmıştı,
# Workable ilanlarının yaşı hiç okunmuyordu.
def t33_workable_liste_alanlar():
    import tempfile
    from isbot.sources.workable import Workable
    from isbot.store import Depo

    # 2026-10-08'de apply.workable.com/api/v3/accounts/ttech/jobs yanıtından.
    yanit = {"total": 1, "results": [{
        "shortcode": "75BD306A09", "title": "Microsoft Cloud Project Engineer",
        "department": ["T-Tech Infrastructure and Projects"], "type": "full",
        "remote": False, "workplace": "hybrid", "published": "2026-09-29T00:00:00.000Z",
        "location": {"city": "London", "country": "United Kingdom", "region": "England"},
        "locations": [{"city": "London", "country": "United Kingdom", "region": "England",
                       "hidden": False},
                      {"city": "Cork", "country": "Ireland", "region": None, "hidden": True}],
    }]}
    k = Workable()
    k._post = lambda *a, **kw: yanit
    j = k.cek("ttech", "Turkcell Teknoloji")[0]
    sina("Workable department metne indirgenir", "T-Tech Infrastructure and Projects",
         j.department)
    sina("Workable tarihi 'published'dan okunur", "2026-09-29",
         j.posted_at.date().isoformat() if j.posted_at else None)
    sina("gizli konum alınmaz", ["London, England, United Kingdom"], j.locations)

    # Güvenlik ağı: bağlayıcı unutsa da model listeyi metne çevirir, depo çökmez.
    ham = ilan(department=["A", "B"], employment_type=["Tam zamanlı"], title=None)
    sina("model liste department'ı birleştirir", "A, B", ham.department)
    sina("model None başlığı boş metne çevirir", "", ham.title)
    with tempfile.TemporaryDirectory() as d:
        depo = Depo(Path(d) / "t.db")
        try:
            run = depo.kosu_baslat()
            depo.kaydet(j, run)
            depo.kaydet(ham, run)
            depo.kaydet(ham, run)            # UPDATE yolu da sınanır
            sina("liste alanlı ilan SQLite'a yazılır", True, True)
        except Exception as e:
            sina("liste alanlı ilan SQLite'a yazılır", True, f"{type(e).__name__}: {e}")
        finally:
            depo.close()


# ---------------------------------------------------------------- 34
# Sabit başlık eleme listesi yazılımcı varsayımıyla HERKESE uygulanıyordu: İK adayının
# "Recruiter", satışçının "Account Executive", pazarlamacının "Content Strategist"
# ilanları puanlamaya girmeden eleniyordu. Kendi ailesinin kalıbı adaya uygulanmaz;
# yazılımcı/mühendis için liste değişmemeli.
def t34_eleme_meslek_muafiyeti():
    import re
    from isbot.cv_import import eleme_kaliplari

    # "senior": kıdem kalıbı yalnız distinguished/fellow + yönetim unvanlarını eler, yani
    # burada ölçülen SABİT listenin muafiyetidir. (mid kıdemde "manager" sözcüğü kıdem
    # kalıbıyla zaten eleniyor — o ayrı, açık bir konu.)
    def elenir(baslik, aileler):
        return any(re.search(k, baslik) for k in eleme_kaliplari(dict.fromkeys(aileler), "senior"))

    muhendis_elenmeli = ["Account Executive, EMEA", "Senior Recruiter", "Customer Success Manager",
                         "Technical Program Manager", "Developer Advocate", "Support Engineer",
                         "Solutions Architect", "Business Development Rep", "Content Strategist"]
    for b in muhendis_elenmeli:
        sina(f"yazılımcıya '{b}' elenir", True, elenir(b, ["backend", "ml_ai"]))
    sina("İK adayına 'Senior Recruiter' açık", False, elenir("Senior Recruiter", ["ik"]))
    sina("İK adayına satış yine elenir", True, elenir("Account Executive", ["ik"]))
    sina("satışçıya 'Account Executive' açık", False, elenir("Account Executive, EMEA", ["satis"]))
    sina("satışçıya 'Recruiter' yine elenir", True, elenir("Senior Recruiter", ["satis"]))
    sina("ürün adayına 'Program Manager' BİLEREK elenir (benchmark)", True,
         elenir("Technical Program Manager", ["urun"]))
    sina("ürün adayına 'Product Manager' açık", False, elenir("Senior Product Manager", ["urun"]))
    sina("pazarlamacıya 'Content Strategist' açık", False,
         elenir("Content Strategist", ["pazarlama"]))
    sina("pazarlamacıya destek rolü yine elenir", True, elenir("Support Engineer", ["pazarlama"]))


# ---------------------------------------------------------------- 35
# roller.yaml'da çift tırnaklı kalıplarda tek "\b" yazılmıştı; YAML onu BACKSPACE'e
# çeviriyor. İK kalıbı "HR Business Partner"ı, İSG kalıbı "HSE Engineer"ı hiç tanımıyordu.
def t35_rol_kaliplarinda_backspace_yok():
    import re
    import yaml as _y
    from isbot.yollar import kaynak_dosya
    roller = _y.safe_load(kaynak_dosya("isbot", "data", "roller.yaml").read_text(encoding="utf-8"))
    bozuk = [ad for ad, t in roller.items() for k in (t.get("basliklar") or []) if "\x08" in k]
    sina("rol kalıplarında backspace yok", [], bozuk)
    sina("İK 'HR Business Partner'ı tanır", True,
         any(re.search(k, "HR Business Partner") for k in roller["ik"]["basliklar"]))
    sina("İSG 'HSE Engineer'ı tanır", True,
         any(re.search(k, "HSE Engineer") for k in roller["isg"]["basliklar"]))


# ---------------------------------------------------------------- 36
# mid/junior kıdem kalıbı "manager" sözcüğünü tümden eliyordu. Ürün, pazarlama, satış
# ve İK'da "Product/Marketing/Account/HR Manager" yönetici değil, bireysel unvandır.
# Adayın ailesine ait bileşikler açılır; "Engineering Manager" herkese kapalı kalır.
def t36_bireysel_manager_unvanlari():
    import re
    from isbot.cv_import import eleme_kaliplari

    def elenir(baslik, aileler, kidem="mid"):
        return any(re.search(k, baslik) for k in eleme_kaliplari(dict.fromkeys(aileler), kidem))

    sina("mid ürün adayına 'Product Manager' açık", False, elenir("Product Manager", ["urun"]))
    sina("junior ürün adayına 'Associate Product Manager' açık", False,
         elenir("Associate Product Manager", ["urun"], "junior"))
    sina("mid pazarlamacıya 'Brand Manager' açık", False, elenir("Brand Manager", ["pazarlama"]))
    sina("mid satışçıya 'Account Manager' açık", False, elenir("Account Manager", ["satis"]))
    sina("mid İK adayına 'HR Manager' açık", False, elenir("HR Manager", ["ik"]))
    sina("ürün+backend adayına 'Engineering Manager' yine elenir", True,
         elenir("Engineering Manager", ["urun", "backend"]))
    sina("'Manager, Product' (ekip yöneticisi) elenir", True, elenir("Manager, Product", ["urun"]))
    sina("mid yazılımcıya 'Product Manager' eskisi gibi elenir", True,
         elenir("Product Manager", ["backend"]))
    sina("mid yazılımcıya 'Engineering Manager' elenir", True,
         elenir("Engineering Manager", ["backend"]))


# ---------------------------------------------------------------- 37
# Uyum hakemi herkese aynı "uyumsuz meslekler" cümlesini ve "deneyimli mühendis"
# profil cümlesini veriyordu: teknisyen, kalite kontrolcü, İK uzmanı kendi mesleğinin
# ilanlarında ceza alıyordu. Mühendis için iki cümle de BİREBİR aynı kalmalı.
def t37_uyum_meslekten_bagimsiz():
    from isbot import uyum
    from isbot.cv_import import teknisyen_mi

    eski = ("Quality control and inspection, production line operator, CNC machine operator, "
            "assembly technician, maintenance and repair technician, warehouse and logistics, "
            "sales and marketing, human resources and payroll, cleaning and administrative "
            "support. Kalite kontrol ve muayene, üretim bandı operatörlüğü, CNC tezgah "
            "operatörlüğü, montaj teknisyenliği, bakım onarım teknisyenliği, depo ve sevkiyat, "
            "satış ve pazarlama, insan kaynakları ve özlük işleri, temizlik ve idari işler.")
    muh = {"kimlik": {"deneyim_yil": 3.0}, "rol_aileleri": {"kontrol_otomasyon": {}},
           "yetenekler": {"guclu": {"control systems": 1.0}}}
    sina("mühendisin uyumsuz cümlesi birebir aynı", eski, uyum.uyumsuz_cumlesi(muh))
    sina("mühendisin profil cümlesi 'mühendis' der", True,
         uyum.profil_cumlesi(muh).startswith("3.0 yıl deneyimli mühendis."))

    tek = {"kimlik": {"deneyim_yil": 8.0, "teknisyen": True},
           "rol_aileleri": {"kontrol_otomasyon": {}}}
    sina("teknisyene bakım onarım cezası yok", False,
         "bakım onarım" in uyum.uyumsuz_cumlesi(tek))
    sina("teknisyenin profil cümlesi 'teknisyen' der", True,
         "deneyimli teknisyen" in uyum.profil_cumlesi(tek))
    sina("İK adayına İK cezası yok", False,
         "insan kaynakları" in uyum.uyumsuz_cumlesi({"rol_aileleri": {"ik": {}}}))
    sina("kalite kontrolcüye kalite cezası yok", False,
         "Kalite kontrol" in uyum.uyumsuz_cumlesi({"rol_aileleri": {"uretim_kalite": {}}}))
    sina("hemşireye 'mühendis' denmez", False,
         "mühendis" in uyum.profil_cumlesi({"rol_aileleri": {"saglik": {}}}))

    sina("başlığı 'Bakım Teknisyeni' olan CV teknisyen", True,
         teknisyen_mi("Aday — Bakım Teknisyeni\nBursa\nEğitim ..."))
    sina("başlığı 'Research Engineer' olan CV teknisyen DEĞİL", False,
         teknisyen_mi("Dr. Ali Vural AI Research Engineer\n... operator theory ... technician"))


# ---------------------------------------------------------------- 38
# Tek geçişli (zayıf) beceri bütün bir meslek ailesini açıyordu. Gerçek bir Türkçe
# CV'de "ağ, depolama ve kullanıcı yönetimi" -> lojistik, "Platt kalibrasyonu" +
# "otomatik kalite kontrolü" -> üretim/kalite, "kompozitler" -> kimya çıktı.
# Zayıf kanıtlı aile ancak deneyimde o ailenin UNVANI geçiyorsa kalır.
def t38_zayif_beceri_aile_acamaz():
    from isbot.cv_import import rol_aileleri_turet, unvan_aileleri

    yet = {"PyTorch", "LLM", "reinforcement learning", "Quality Control",
           "Metrology and Calibration", "Composite Materials"}
    guclu = {"PyTorch", "LLM", "reinforcement learning"}
    aileler = rol_aileleri_turet(yet, guclu, set())
    sina("güçlü kanıtlı aile kalır", True, "ml_ai" in aileler)
    sina("zayıf kanıtlı üretim/kalite düşer", False, "uretim_kalite" in aileler)
    sina("zayıf kanıtlı kimya düşer", False, "kimya" in aileler)
    sina("deneyimde unvanı geçen zayıf aile kalır", True,
         "uretim_kalite" in rol_aileleri_turet(yet, guclu, {"uretim_kalite"}))
    sina("güçlü kanıt hiç yoksa eski davranış (genel yazılıma düşmez)", True,
         "uretim_kalite" in rol_aileleri_turet({"Quality Control", "Metrology and Calibration"},
                                               set(), set()))
    sina("'Üretim Mühendisi' unvanı üretim/kalite kanıtıdır", True,
         "uretim_kalite" in unvan_aileleri("Deneyim\nÜretim Mühendisi   2024 – 2025\nABC A.Ş."))

    from isbot.cv_import import yetenek_tespit
    g, z = yetenek_tespit("Linux sunucusu kurdum; ağ, depolama ve kullanıcı yönetimi dâhil. " * 3)
    sina("'depolama' depo yönetimi sayılmaz", False, "Warehouse Management" in {**g, **z})


# ---------------------------------------------------------------- 39
# "Yaz 2025" gibi ay yazılmamış dönem 3 ay sayılıyordu ve mevsim yok sayılıp hep
# Haziran–Eylül'e konuyordu: iki yaz stajlı CV 5 aylık deneyimi 0,7 yıl gösteriyordu.
def t39_mevsim_suresi():
    from isbot.experience import _araliklari_topla
    for satir in ("Stajyer   Yaz 2025", "Intern   Summer 2025"):
        (bas, son), = _araliklari_topla(satir)[0]
        sina(f"'{satir.split()[-2]}' 2 ay sayılır", 2, round((son - bas) * 12))
    (bas, _), = _araliklari_topla("Intern   Winter 2024")[0]
    sina("'Winter' kışa yerleşir (Ocak)", 1, round((bas - 2024) * 12) + 1)


# ---------------------------------------------------------------- 40
# Paneldeki rol adı sözlüğünde 20 yazılım dışı aile yoktu; kullanıcı "uretim kalite",
# "lojistik" gibi ham anahtarlar görüyordu. Her aile panelde okunur ada sahip olmalı.
def t40_panelde_her_ailenin_adi_var():
    import re
    import yaml as _y
    from isbot.yollar import kaynak_dosya
    roller = _y.safe_load(kaynak_dosya("isbot", "data", "roller.yaml").read_text(encoding="utf-8"))
    html = kaynak_dosya("isbot", "web", "index.html").read_text(encoding="utf-8")
    blok = html[html.index("const ROL_AD"):html.index("const rolAdi")]
    sina("panelde adı eksik aile yok", [], sorted(set(roller) - set(re.findall(r"(\w+):\s*\"", blok))))


# ---------------------------------------------------------------- 41
# kariyer.net'in en yaygın pozisyonlarının çoğu hiçbir aileye girmiyordu: "Mağaza Satış
# Elemanı" (193 il), "Depo Elemanı" (184), "Kalite Mühendisi", "Teknik Ofis Mühendisi"...
# Aile vardı, Türkçe unvanı yoktu. Olumsuzlar, genişletilen kalıpların komşu mesleği
# yutmadığını kilitler.
def t41_turkce_unvan_kapsami():
    import re
    import yaml as _y
    from isbot.yollar import kaynak_dosya
    roller = _y.safe_load(kaynak_dosya("isbot", "data", "roller.yaml").read_text(encoding="utf-8"))

    def aile(baslik):
        return [ad for ad, t in roller.items() if any(re.search(k, baslik) for k in t["basliklar"])]

    for baslik, beklenen in [("MAĞAZA SATIŞ ELEMANI", "satis"), ("Tıbbi Mümessil", "satis"),
                             ("Depo Elemanı", "lojistik"), ("Dış Ticaret Uzmanı", "lojistik"),
                             ("Kalite Mühendisi", "uretim_kalite"),
                             ("Üretim Planlama Mühendisi", "uretim_kalite"),
                             ("Teknik Ofis Mühendisi", "insaat"), ("Grafik Tasarımcı", "pazarlama"),
                             ("Bilgi İşlem Uzmanı", "platform_sre"), ("Hasta Bakıcı", "saglik"),
                             ("Kabin Memuru", "turizm"), ("Gişe Yetkilisi", "bankacilik"),
                             ("Okul Müdür Yardımcısı", "egitim"), ("Proje Müdürü", "urun")]:
        sina(f"'{baslik}' -> {beklenen}", True, beklenen in aile(baslik))
    sina("'Güvenlik Vardiya Amiri' üretime girmez", False,
         "uretim_kalite" in aile("Güvenlik Vardiya Amiri"))
    sina("'Müşteri İletişim Uzmanı' pazarlamaya girmez", False,
         "pazarlama" in aile("Müşteri İletişim Uzmanı"))
    sina("'Güvenlik Görevlisi' siber güvenliğe girmez", False,
         "guvenlik" in aile("Güvenlik Görevlisi"))


# ---------------------------------------------------------------- 42
# Teknisyen CV'si kontrol/otomasyon ve üretim/kalite ailelerine düşüyordu; 6 Türkçe
# sorgusunun 6'sı mühendis/müdür pozisyonuydu ("otomasyon mühendisi", "üretim müdürü"),
# "Elektrik Bakım Teknisyeni" başlığı hiçbir aileye girmiyordu. bakim_teknik ailesi
# YALNIZ teknisyende açılır ve açıldığında sorgular ondan dolar.
def t42_teknisyen_ailesi():
    import re
    import yaml as _y
    from isbot.cv_import import _en_sorgular, _tr_sorgular, profil_tazele, rol_aileleri_turet
    from isbot.yollar import kaynak_dosya
    roller = _y.safe_load(kaynak_dosya("isbot", "data", "roller.yaml").read_text(encoding="utf-8"))

    def aile(baslik):
        return [ad for ad, t in roller.items() if any(re.search(k, baslik) for k in t["basliklar"])]

    yet = {"preventive maintenance", "hydraulics and pneumatics", "electrical panel", "PLC",
           "Lean Manufacturing", "Kaizen"}
    sina("bakım becerili mühendise teknisyen ailesi açılmaz", False,
         "bakim_teknik" in rol_aileleri_turet(yet, yet, set(), teknisyen=False))
    teknik = rol_aileleri_turet(yet, yet, set(), teknisyen=True)
    sina("teknisyene açılır", True, "bakim_teknik" in teknik)

    # Sıra bilerek ters: üretim/kalite önde olsa da sorgular teknisyen ailesinden dolar.
    sira = {"uretim_kalite": teknik["uretim_kalite"], "bakim_teknik": teknik["bakim_teknik"]}
    sina("Türkçe sorguların hepsi teknisyen pozisyonu", roller["bakim_teknik"]["tr_pozisyonlar"][:6],
         _tr_sorgular(sira))
    sina("İngilizce sorgularda mühendis pozisyonu yok", roller["bakim_teknik"]["en_pozisyonlar"],
         _en_sorgular(sira))
    sina("teknisyen olmayanın sorgusu değişmez", "üretim müdürü",
         _tr_sorgular({"uretim_kalite": teknik["uretim_kalite"]})[0])

    # CV'siz tazeleme de aynı kararı vermeli (kimlik.teknisyen profilde saklı).
    profil = {"_motor_surumu": "eski", "kimlik": {"teknisyen": True},
              "yetenekler": {"guclu": {k: 0.8 for k in yet}, "zayif": {}},
              "rol_aileleri": {"kontrol_otomasyon": {}}, "sert_filtreler": {"max_kidem": "mid"}}
    sina("tazelemede teknisyen ailesi korunur", True,
         "bakim_teknik" in profil_tazele(profil)[0]["rol_aileleri"])

    for baslik, beklenen in [("Elektrik Bakım Teknisyeni", True), ("Saha Teknisyeni", True),
                             ("Fiberoptik Teknisyeni", True), ("Teknik Servis Elemanı", True),
                             ("Maintenance Technician", True), ("Servis Elemanı", False),
                             ("Kalite Kontrol Teknisyeni", False), ("Anestezi Teknikeri", False),
                             ("Bakım Mühendisi", False)]:
        sina(f"'{baslik}' teknisyen ailesi: {beklenen}", beklenen, "bakim_teknik" in aile(baslik))
    sina("'Teknik Servis Elemanı' garson sayılmaz", False, "turizm" in aile("Teknik Servis Elemanı"))


# ---------------------------------------------------------------- 43
# Üretim elemanı/operatörü, CNC, kaynak, paketleme kariyer.net'in en yaygın mavi yaka
# pozisyonlarıydı ve hiçbir aileye girmiyordu. "Üretim Elemanı" başlıklı CV teknisyen
# tespitine de takılmıyordu; "CNC Machinist" başlıklı CV ise iki satır aşağıdaki
# "Precision Engineering Ltd" yüzünden mühendis sayılıyordu.
def t43_uretim_operatoru():
    import re
    import yaml as _y
    from isbot import uyum
    from isbot.cv_import import teknisyen_mi
    from isbot.yollar import kaynak_dosya
    roller = _y.safe_load(kaynak_dosya("isbot", "data", "roller.yaml").read_text(encoding="utf-8"))

    def aile(baslik):
        return [ad for ad, t in roller.items() if any(re.search(k, baslik) for k in t["basliklar"])]

    for baslik in ("Üretim Elemanı", "Ambalaj Makinesi Operatörü", "CNC Operatörü", "Kaynakçı",
                   "Paketleme Elemanı", "Montaj Elemanı", "CNC Machinist"):
        sina(f"'{baslik}' -> uretim_operator", True, "uretim_operator" in aile(baslik))
    for baslik in ("Forklift Operatörü", "Kalite Kontrol Operatörü", "Üretim Mühendisi"):
        sina(f"'{baslik}' operatör ailesine girmez", False, "uretim_operator" in aile(baslik))
    sina("'İlaçlama Operatörü' ilaç ailesine girmez", False,
         "ilac_biyotek" in aile("İlaçlama Operatörü"))

    sina("'Üretim Elemanı' başlıklı CV uygulayıcı", True,
         teknisyen_mi("Aday — Üretim Elemanı\nKocaeli\nEğitim"))
    sina("işyeri adındaki 'Engineering' mühendis yapmaz", True,
         teknisyen_mi("Ali Kaya - CNC Machinist\nLeeds\n\nEducation\nCollege\n\n"
                      "Experience\nPrecision Engineering Ltd"))
    sina("'Muhasebe Elemanı' uygulayıcı değil", False,
         teknisyen_mi("Ayşe Yılmaz\nMuhasebe Elemanı\nAnkara"))

    op = {"kimlik": {"deneyim_yil": 5.0, "teknisyen": True},
          "rol_aileleri": {"uretim_operator": {}, "bakim_teknik": {}}}
    sina("operatörün profil cümlesi üretim işini anlatır", True,
         "Üretim hattı, tezgah" in uyum.profil_cumlesi(op))
    sina("operatöre CNC operatörlüğü cezası yok", False,
         "CNC" in uyum.uyumsuz_cumlesi({"rol_aileleri": {"uretim_operator": {}}}))


# ---------------------------------------------------------------- 44
# Müşteri hizmetleri temsilcisi/yetkilisi ve çağrı merkezi elemanı hiçbir aileye
# girmiyordu; çağrı merkezi CV'si satis'e düşüp "satış müdürü" diye aranıyordu.
# İngilizce "Customer Support Specialist" başlığı sabit eleme listesinde HERKESE yasaktı.
def t44_musteri_hizmetleri():
    import re
    import yaml as _y
    from isbot.cv_import import eleme_kaliplari, rol_aileleri_turet
    from isbot.yollar import kaynak_dosya
    roller = _y.safe_load(kaynak_dosya("isbot", "data", "roller.yaml").read_text(encoding="utf-8"))

    def aile(baslik):
        return [ad for ad, t in roller.items() if any(re.search(k, baslik) for k in t["basliklar"])]

    for baslik in ("Müşteri Hizmetleri Temsilcisi", "Çağrı Merkezi Elemanı",
                   "Customer Support Specialist", "Canlı Destek Temsilcisi"):
        sina(f"'{baslik}' -> musteri_hizmetleri", True, "musteri_hizmetleri" in aile(baslik))
    sina("'Servis Danışmanı' satış sonrası (satis)", True, "satis" in aile("Servis Danışmanı"))

    def yasak(aileler, baslik):
        return any(re.search(k, baslik) for k in eleme_kaliplari(aileler, "mid"))
    sina("müşteri hizmetleri adayına 'Customer Support Specialist' yasak değil", False,
         yasak({"musteri_hizmetleri": {}}, "Customer Support Specialist"))
    sina("mühendise 'Customer Support Specialist' hâlâ yasak", True,
         yasak({"backend": {}}, "Customer Support Specialist"))

    tek = {"Customer Service", "CRM"}
    sina("'Customer Service' + 'CRM' tek başına aileyi açmaz (bankacı, otelci)", False,
         "musteri_hizmetleri" in rol_aileleri_turet(tek, tek, set()))
    sina("çağrı merkezi becerisi açar", True,
         "musteri_hizmetleri" in rol_aileleri_turet(tek | {"Call Centre"}, tek | {"Call Centre"}, set()))


# ---------------------------------------------------------------- 45
# CV kişinin İSTEMEDİĞİNİ söylemez: FastAPI/Flask kanıtı olan aday backend ailesini %62
# ağırlıkla alıyordu ama backend işi aramıyordu. Panelde aile kapatılır; karar profilde
# saklanır, CV yeniden yüklenince ve motor güncellenince de korunur.
def t45_rol_ailesi_kapatma():
    import tempfile
    import isbot.server as sunucu
    from isbot.cv_import import profil_tazele, profil_uret, yaz

    cv = Path(__file__).resolve().parent.parent / "test-cvs" / "14_blockchain_solidity.txt"
    p = profil_uret(cv)
    sina("örnek CV'de backend açık (sınamanın ön koşulu)", True, "backend" in p["rol_aileleri"])
    p["_haric_aileler"] = ["backend"]
    p, _ = profil_tazele(p, zorla=True)
    sina("kapatılan aile türetilmez", False, "backend" in p["rol_aileleri"])
    sina("kapatılan ailenin İngilizce sorgusu düşer", False, "backend engineer" in p["arama_sorgulari"])
    sina("CV yeniden üretilince karar korunur", False,
         "backend" in profil_uret(cv, haric={"backend"})["rol_aileleri"])

    eski_yol = sunucu.VARSAYILAN_PROFIL
    with tempfile.TemporaryDirectory() as d:
        sunucu.VARSAYILAN_PROFIL = Path(d) / "profile.local.yaml"
        try:
            yaz(profil_uret(cv), sunucu.VARSAYILAN_PROFIL)
            with sunucu.app.test_client() as ist:
                r = ist.post("/api/profil/aile", json={"ad": "backend", "haric": True}).get_json()
                sina("uç aileyi kapatır", (False, ["backend"]),
                     ("backend" in [x["ad"] for x in r["rol_aileleri"]], r["haric_aileler"]))
                with open(cv, "rb") as f:
                    r = ist.post("/api/cv", data={"cv": (f, "cv.txt")},
                                 content_type="multipart/form-data").get_json()
                sina("yeni CV yüklemesi kapatılan aileyi taşır", (False, ["backend"]),
                     ("backend" in [x["ad"] for x in r["rol_aileleri"]], r["haric_aileler"]))
                r = ist.post("/api/profil/aile", json={"ad": "blockchain", "haric": True})
                sina("son açık aile kapatılamaz", 400, r.status_code)
                r = ist.post("/api/profil/aile", json={"ad": "backend", "haric": False}).get_json()
                sina("geri açılır", (True, []),
                     ("backend" in [x["ad"] for x in r["rol_aileleri"]], r["haric_aileler"]))
                sina("tanınmayan aile reddedilir", 400,
                     ist.post("/api/profil/aile", json={"ad": "yok_boyle"}).status_code)
        finally:
            sunucu.VARSAYILAN_PROFIL = eski_yol


# ---------------------------------------------------------------- 46
# Bankacı CV'sinin "kredi risk değerlendirmesi" İSG ailesini açıyordu: eşanlamlı çıplak
# "risk değerlendirmesi" tanımlayıcı tetikti, İSG unvan kalıbı da onu unvan sayıyordu.
def t46_risk_degerlendirmesi_isg_acmaz():
    import re
    import yaml as _y
    from isbot.cv_import import rol_aileleri_turet
    from isbot.yollar import kaynak_dosya
    roller = _y.safe_load(kaynak_dosya("isbot", "data", "roller.yaml").read_text(encoding="utf-8"))
    sina("tek başına risk değerlendirmesi İSG açmaz", False,
         "isg" in rol_aileleri_turet({"Occupational Risk Assessment", "Credit Analysis"},
                                     {"Occupational Risk Assessment", "Credit Analysis"}, set()))
    sina("İSG uzmanında açılır", True,
         "isg" in rol_aileleri_turet({"Occupational Health and Safety", "Occupational Risk Assessment"},
                                     {"Occupational Health and Safety"}, set()))
    sina("'Kredi Risk Değerlendirme Uzmanı' İSG unvanı değil", False,
         any(re.search(k, "Kredi Risk Değerlendirme Uzmanı") for k in roller["isg"]["basliklar"]))


# ---------------------------------------------------------------- 47
# Türk panosu ilanlarının metni en fazla tr_detay_siniri tane çekiliyor ve liste BAŞINDAN
# alınıyordu; liste havuz sırasındaydı. Başlığı en iyi uyan ilan sona düşerse metni hiç
# çekilmiyor, beceri puanı 0'da kalıyordu.
def t47_tr_detay_en_iyisi_once():
    from types import SimpleNamespace as N
    from isbot.pipeline import tr_detay_adaylari
    def s_(kaynak, puan, cekildi=False):
        return N(job=N(source=kaynak, raw={"detay_cekildi": cekildi}, title=str(puan)), nihai=puan)
    liste = [s_("kariyernet", 10), s_("greenhouse", 90), s_("kariyernet", 40),
             s_("elemannet", 25), s_("kariyernet", 80, cekildi=True)]
    sina("TR adayları puan sırasıyla, ATS ve metni çekilmiş olan hariç", [40, 25, 10],
         [x.nihai for x in tr_detay_adaylari(liste)])


# ---------------------------------------------------------------- 48
# "Site Reliability Engineer (Intermediate to Senior Staff)" en yüksek sözcükten staff
# okunuyor, kıdemli adaya da kapanıyordu. Aralıkta kıdem ALT SINIRDAN okunur.
def t48_kidem_araligi():
    from isbot.scoring import _kidem_bul
    def k(baslik):
        return _kidem_bul(Job(source="x", company="x", board_token="x", native_id="1",
                              title=baslik, url=""))
    sina("'Intermediate to Senior Staff' -> mid", "mid",
         k("Site Reliability Engineer (Intermediate to Senior Staff)"))
    sina("'Mid/Senior' -> mid", "mid", k("Mid/Senior Backend Engineer"))
    sina("'Senior Staff Engineer' aralık değil -> staff", "staff", k("Senior Staff Engineer"))
    sina("'Senior - Platform Team' aralık değil -> senior", "senior", k("Senior - Platform Team"))


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
