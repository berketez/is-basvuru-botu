"""CV → profil taslağı üretici.

AMAÇ: Bu araç sadece tek bir kişiye göre çalışmasın. Kim olursa olsun kendi
CV'sini verir, motor ona göre puanlar.

    python -m isbot cv-import ~/cv.pdf -o config/profile.local.yaml

Üretilen dosya bir TASLAKTIR — kıdem, konum ve çalışma izni gibi alanlar
CV'den güvenilir biçimde çıkarılamaz, kullanıcı elle düzeltir. Bunu gizlemiyoruz:
üretilen YAML'ın başına 'GÖZDEN GEÇİR' notu düşüyoruz.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from .experience import metin_normalize
from .experience import tahmin as deneyim_tahmin

from .yollar import kaynak_dosya

SOZLUK = kaynak_dosya("isbot", "data", "skills.yaml")

BASLIK_YIL = re.compile(r"(19|20)\d{2}")
# Türkçe başlıklar çekim eki alır: "Beceri" değil "Teknik Beceriler", "Yetkinlikler",
# "Teknolojiler". `\b...\b` ile yazılınca ekli hâl eşleşmez ve bölüm hiç bulunmaz.
# Bunun bedeli sessizdir: bölüm bulunamayınca hiçbir yetenek "Skills'te ilan edilmiş"
# bonusunu (+0,35) alamaz, hepsi eşiğin altında kalır ve GÜÇLÜ yetenek listesi BOŞ çıkar.
# ÖLÇÜLDÜ (Türkçe kontrol mühendisi CV'si): "Teknik Beceriler" başlığı altında 8 kalem
# yazılı olduğu hâlde güçlü yetenek sayısı 0'dı.
YETENEK_BOLUM = re.compile(
    r"(?is)\b(technical skills|core competenc\w*|competenc\w*|technolog\w*|skills?|"
    r"teknik beceri\w*|teknik yetkinlik\w*|beceri\w*|yetenek\w*|yetkinlik\w*|"
    r"teknoloji\w*|uzmanlık alan\w*|bilgisayar bilgi\w*)\b(.{0,1500})")


# ---------------- metin çıkarma ----------------
def metin_cikar(yol: str | Path) -> str:
    p = Path(yol).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"CV bulunamadı: {p}")
    son = p.suffix.lower()

    if son == ".pdf":
        try:
            r = subprocess.run(["pdftotext", "-layout", str(p), "-"],
                               capture_output=True, timeout=60)
            if r.returncode == 0 and r.stdout.strip():
                return metin_normalize(r.stdout.decode("utf-8", "ignore"))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        try:
            import pypdf
            return metin_normalize("\n".join((s.extract_text() or "") for s in pypdf.PdfReader(str(p)).pages))
        except Exception as e:
            raise RuntimeError(f"PDF okunamadı: {e}") from e

    if son == ".docx":
        import docx
        # metin_normalize'dan GEÇMELİ: NFC birleştirmesi orada yapılıyor (bkz. experience.py).
        return metin_normalize("\n".join(par.text for par in docx.Document(str(p)).paragraphs))

    ham = p.read_text(encoding="utf-8", errors="ignore")
    if son == ".tex":
        ham = re.sub(r"(?m)^\s*%.*$", "", ham)
        if r"\begin{document}" in ham:
            ham = ham.split(r"\begin{document}")[-1]
        ham = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", ham)
        ham = re.sub(r"\\[a-zA-Z]+\*?", " ", ham)
        ham = re.sub(r"[{}$&~^\\]", " ", ham)
    return metin_normalize(re.sub(r"[ \t]+", " ", ham))


# ---------------- yetenek tespiti ----------------
# --- terim eşleştirme: ek ve çoğul toleransı -------------------------------------
# SORUN: kelime sınırı (\b) hem Türkçe ekini hem İngilizce çoğulunu KESİYOR.
#   "gömülü sistem"      ← "Gömülü sistemler için C++"   -> 0 eşleşme
#   "kontrol sistemleri" ← "Kontrol sistemlerinde"        -> 0 eşleşme
#   "control system"     ← "control systems experience"   -> 0 eşleşme
# Bu sessiz bir kayıptı: sözlüğe terim eklenmiş görünüyor, gerçek metinde hiç
# tutmuyordu. Türkçe eklemeli bir dil olduğu için bedeli Türkçe tarafta çok ağır.
#
# ÇÖZÜM: terimin SONUNA ek toleransı (\w*), ama yalnız yanlış eşleşme riski
# düşük terimlerde:
#   - çok kelimeli terim ("kontrol sistemleri")  -> zaten spesifik, güvenli
#   - 7+ karakterli tek kelime ("aviyonik", "simulink") -> güvenli
#   - kısa tek kelime ("java", "rust", "react", "go", "C") -> DOKUNULMAZ.
#     Yoksa "java" -> "javascript", "react" -> "reactive" sahte eşleşmesi olur.
def _ek_toleransli(terim: str) -> bool:
    return " " in terim.strip() or len(terim) >= 7


def _gecis_sayisi(metin: str, terim: str) -> int:
    if re.fullmatch(r"[A-Za-z+#.]{1,4}", terim):
        kalip = rf"(?<![\w+#.]){re.escape(terim)}(?![\w+#.])"
    elif _ek_toleransli(terim):
        kalip = rf"(?<!\w){re.escape(terim)}\w*"
    else:
        kalip = rf"(?<!\w){re.escape(terim)}(?!\w)"
    return len(re.findall(kalip, metin, re.IGNORECASE))


def yetenek_tespit(metin: str) -> tuple[dict[str, float], dict[str, float]]:
    """CV metnini sözlükle tarar → (güçlü, zayıf) yetenek haritaları.

    Ağırlık, kanıt yoğunluğundan gelir: kaç kez geçiyor + 'Skills' bölümünde mi.
    Tek kez geçen bir teknoloji 'zayıf', birden çok yerde geçen 'güçlü' sayılır.

    Girdi burada TEKRAR normalize edilir. Şu an tek çağıran metin_cikar'dan geçiyor,
    yani zaten NFC; ama bu fonksiyon ham metinle çağrılırsa Türkçe CV'de sahte
    yetenek üretir (Gömülü->Go, Çift->C, sensör->R) ve hata SESSİZDİR — çıktı
    makul görünür, yalnızca yanlıştır. NFC idempotenttir, ikinci çağrının bedeli yok.
    """
    metin = metin_normalize(metin)
    sozluk = yaml.safe_load(SOZLUK.read_text(encoding="utf-8"))
    bolum_m = YETENEK_BOLUM.search(metin)
    yetenek_bolumu = bolum_m.group(2) if bolum_m else ""

    skor: Counter[str] = Counter()
    for _kat, kalemler in sozluk.items():
        for kanonik, esanlamlilar in kalemler.items():
            terimler = [kanonik] + list(esanlamlilar or [])
            n = sum(_gecis_sayisi(metin, t) for t in terimler)
            if n == 0:
                continue
            s = min(n, 6) / 6.0                       # 6+ geçiş = doygunluk
            if any(_gecis_sayisi(yetenek_bolumu, t) for t in terimler):
                s += 0.35                             # Skills bölümünde ilan edilmiş
            skor[kanonik] = round(min(s, 1.0), 2)

    guclu = {k: v for k, v in skor.items() if v >= 0.45}
    zayif = {k: round(v * 0.5, 2) for k, v in skor.items() if v < 0.45}
    return dict(sorted(guclu.items(), key=lambda x: -x[1])), dict(sorted(zayif.items(), key=lambda x: -x[1]))


# ---------------- profil üretimi ----------------
ROLLER = kaynak_dosya("isbot", "data", "roller.yaml")

# Tercihler her profilde aynı kalabilir; rol aileleri ise CV'den TÜRETİLİR.
SABLON_KUYRUK = {
    "tercihler": {
        "uzaktan_oncelik": 0.25,
        "sektor_bonus": {r"(?i)\b(fintech|crypto|trading|quant)\b": 0.10},
    },
}


def rol_aileleri_turet(yetenekler: set[str]) -> dict:
    """CV'de tespit edilen yeteneklerden rol ailelerini çıkarır.

    NEDEN: Eskiden bu liste SABİTTİ (llm/ml/yazılım/veri). Sonuç: iOS geliştiricisi,
    gömülü mühendis, QA, oyun geliştiricisi — hepsi "ML/backend işi arıyor" gibi
    puanlanıyordu. 15 CV'lik benchmark'ta 11 profile aynı ilan çıkıyordu
    ("Senior Software Engineer - Core Databases"). Artık aileler CV'ye göre seçiliyor.

    Ağırlık, tetiklenen yetenek sayısıyla hafifçe ölçeklenir: 5 mobil yeteneği olan
    biri, 1 tanesi olandan daha güçlü bir mobil adayıdır.
    """
    tanimlar = yaml.safe_load(ROLLER.read_text(encoding="utf-8"))
    secilen = {}
    for ad, t in tanimlar.items():
        # TANIMLAYICI tetik: biri bile varsa aile açılır.
        guclu = [x for x in (t.get("tetik_guclu") or []) if x in yetenekler]
        # DESTEKLEYİCİ tetik: tek başına yetmez (bkz. roller.yaml'daki Swift örneği).
        destek = [x for x in (t.get("tetik") or []) if x in yetenekler]
        tetikler = guclu + destek
        if not guclu and len(destek) < t.get("tetik_min", 2):
            continue
        secilen[ad] = {
            "_ham_agirlik": t.get("agirlik", 1.0),
            "_guclu_var": bool(guclu),
            "_tetik_sayisi": len(tetikler),
            "basliklar": t["basliklar"],
            "_tetikleyen": tetikler[:6],
        }
    # AĞIRLIK = alanın CV'deki MERKEZİLİĞİ.
    # Eşit ağırlık vermek yanlıştı: 7 tetikle açılan ml_ai ile 2 tetikle açılan
    # platform_sre aynı ağırlığı alıyordu ve bir Staff ML mühendisinin ilk
    # sonuçları SRE ilanları oluyordu. Artık en çok tetiklenen aile baskın.
    en_cok = max((d["_tetik_sayisi"] for d in secilen.values()), default=1) or 1
    for ad, d in secilen.items():
        taban = 0.55 if d["_guclu_var"] else 0.40
        merkezilik = d["_tetik_sayisi"] / en_cok
        d["agirlik"] = round(d["_ham_agirlik"] * min(1.0, taban + 0.45 * merkezilik), 2)
        for k in ("_ham_agirlik", "_guclu_var", "_tetik_sayisi"):
            d.pop(k)

    if not secilen:            # hiçbir aile tutmadıysa geniş bir yazılım ailesi ver
        secilen["genel_yazilim"] = {
            "agirlik": 0.5,
            "basliklar": [r"(?i)\b(engineer|developer|analyst|specialist)\b"],
            "_tetikleyen": [],
        }
    return dict(sorted(secilen.items(), key=lambda x: -x[1]["agirlik"]))


SABIT_ELEME_LISTESI = [
    r"(?i)\b(sales|recruiter|account executive|customer success)\b",
    r"(?i)\b(solutions? (architect|engineer|consultant)|deployment strategist|"
    r"consulting (architect|engineer)|professional services)\b",
    r"(?i)\b(technical account|escalations engineer|pre[- ]?sales|business development)\b",
    r"(?i)\b(partner manager|customer engineer|field engineer|implementation consultant)\b",
    r"(?i)\b(support (engineer|associate|specialist|analyst|agent|representative|"
    r"consultant|advisor|coordinator)|technical support|"
    r"l[123] support|help ?desk|community manager|developer (advocate|relations)|devrel|"
    r"(product|customer|saas|client) support)\b",
    r"(?i)\b(strategist|evangelist|program manager)\b",
]
SABIT_ELEME = "|".join(SABIT_ELEME_LISTESI)


def motor_surumu() -> str:
    """Üretilen filtrelerin sürüm damgası.

    NEDEN: Profil CV yüklenince BİR KEZ üretiliyor. Motor sonradan iyileştirilince
    (yeni eleme kalıbı, yeni rol ailesi) mevcut kullanıcının profili eski kalıyor ve
    düzeltme ona hiç ulaşmıyor — ölçüldü: "Developer Relations" ve "Support Agent"
    ilanları, kalıpları eklendikten SONRA bile kısa listede kalmıştı.
    Damga değişince profil otomatik tazelenir.
    """
    import hashlib
    govde = (ROLLER.read_text(encoding="utf-8")
             + "|".join(_kidem_ustu_kaliplar("junior") + _kidem_ustu_kaliplar("senior"))
             + SABIT_ELEME)
    return hashlib.sha256(govde.encode("utf-8")).hexdigest()[:12]


def _kidem_ustu_kaliplar(kidem: str) -> list[str]:
    """Adayın kıdeminin ÜSTÜNDEKİ unvanları eleyen kalıplar.

    Başlık bazlı eleme, ilan metnindeki "X yıl deneyim" şartından daha güvenilirdir
    (çoğu ilan yıl yazmaz). Denetimde panelden üretilen profilde bu eksikti ve
    0,6 yıllık bir CV'ye "Engineering Manager, SRE" ilanı öneriliyordu.
    """
    # c[teofi]o = cto/ceo/coo/cfo/cio. Kopyası silinen blokta bu genişliğiyle duruyordu
    # ama Python ikinci tanımı kullandığı için COO/CIO başlıkları hiç elenmiyordu.
    yonetim = r"(?i)\b(head of|director|vp of|vice president|chief|c[teofi]o)\b"
    if kidem == "junior":
        return [r"(?i)\b(staff|principal|distinguished|fellow|lead|manager)\b", yonetim]
    if kidem == "mid":
        return [r"(?i)\b(staff|principal|distinguished|fellow|manager)\b", yonetim]
    if kidem == "senior":
        return [r"(?i)\b(distinguished|fellow)\b", yonetim]
    return [yonetim]


# Rol ailesine göre önerilen HEDEF ŞİRKETLER. Bu kurumların adı kariyer.net'in
# kategori yollarında HİÇ geçmiyor ve bir kısmının kendi kariyer sitesi bot
# korumasının arkasında (ASELSAN'da robots.txt bile alınamıyor). Firma profili
# sayfası onlara ulaşan tek robots-izinli kanal.
#
# Bu bir BAŞLANGIÇ listesidir, kullanıcı profile.yaml'da kendi listesini yazar.
# Yalnız ilgili aile açıldığında eklenir — bir muhasebeciye savunma sanayii
# şirketleri önerilmez.
HEDEF_SIRKETLER = {
    "havacilik_savunma": ["ASELSAN", "TUSAŞ", "ROKETSAN", "HAVELSAN", "STM",
                          "BAYKAR", "MKE", "TEI", "FNSS", "OTOKAR"],
    "kontrol_otomasyon": ["ASELSAN", "ROKETSAN", "Arçelik", "Vestel", "Ford Otosan",
                          "TOFAŞ", "Siemens", "Schneider Electric"],
    "makine_tasarim": ["Arçelik", "Ford Otosan", "TOFAŞ", "TEMSA", "BMC", "Otokar"],
    "gomulu": ["ASELSAN", "Vestel", "Arçelik", "BAYKAR", "HAVELSAN"],
    "enerji_cevre": ["Enerjisa", "Aksa Enerji", "Zorlu Enerji", "TEİAŞ"],
    "insaat": ["Limak", "Rönesans", "Nurol", "TAV", "Enka"],
    "bankacilik": ["Garanti BBVA", "İş Bankası", "Akbank", "Yapı Kredi", "QNB"],
    "saglik": ["Acıbadem", "Medical Park", "Memorial", "Medicana"],
}


def _hedef_sirketler(roller: dict, ust_sinir: int = 8) -> list[str]:
    """Etkin rol ailelerinden önerilen hedef şirketler.

    SIRAYLA (round-robin) alınır: tek ailenin listesi kotayı doldurursa ikinci
    aile hiç temsil edilmiyor. ÖLÇÜLDÜ: kontrol+havacılık profilinde kontrol
    ailesinin 8 şirketi kotayı bitiriyor ve TUSAŞ, HAVELSAN, BAYKAR listeye hiç
    girmiyordu — oysa aday tam olarak o kurumların adayı.
    (Aynı sorun tr_arama_sorgulari'nda da yaşanmıştı, çözüm aynı.)
    """
    listeler = [list(HEDEF_SIRKETLER.get(ad, [])) for ad in roller]
    cikti: list[str] = []
    for i in range(max((len(x) for x in listeler), default=0)):
        for lst in listeler:
            if i < len(lst) and lst[i] not in cikti:
                cikti.append(lst[i])
                if len(cikti) >= ust_sinir:
                    return cikti
    return cikti


def _en_sorgular(roller: dict, ust_sinir: int = 3) -> list[str]:
    """Etkin rol ailelerinden İngilizce pozisyon adları (ağırlığa göre sıralı).

    Uluslararası kaynaklar (Remotive vb.) İngilizce sorgu alır. Aday hangi alandaysa
    sorgu da o alandan gelmeli; sabit bir "software engineer" herkese aynı havuzu
    getiriyordu.
    """
    tanimlar = yaml.safe_load(ROLLER.read_text(encoding="utf-8"))
    cikti: list[str] = []
    for ad in roller:                                   # roller zaten ağırlığa göre sıralı
        for poz in (tanimlar.get(ad, {}) or {}).get("en_pozisyonlar", []):
            if poz not in cikti:
                cikti.append(poz)
                if len(cikti) >= ust_sinir:
                    return cikti
    return cikti or ["engineer"]


def _tr_sorgular(roller: dict, ust_sinir: int = 6) -> list[str]:
    """Etkin rol ailelerinden Türkçe pozisyon adları toplar (ağırlığa göre sıralı)."""
    tanimlar = yaml.safe_load(ROLLER.read_text(encoding="utf-8"))
    # SIRAYLA al (round-robin): tek ailenin tüm pozisyonlarını alıp kotayı doldurmak,
    # ikinci ailenin hiç temsil edilmemesine yol açıyordu — CV'si hem gömülü hem
    # yapay zeka olan birinde "yapay zeka mühendisi" listeye hiç girmiyordu.
    listeler = [list((tanimlar.get(ad, {}) or {}).get("tr_pozisyonlar", [])) for ad in roller]
    cikti: list[str] = []
    for i in range(max((len(x) for x in listeler), default=0)):
        for lst in listeler:
            if i < len(lst) and lst[i] not in cikti:
                cikti.append(lst[i])
                if len(cikti) >= ust_sinir:
                    return cikti
    return cikti[:ust_sinir]


def profil_uret(cv_yolu: str | Path) -> dict:
    metin = metin_cikar(cv_yolu)
    if len(metin) < 200:
        raise RuntimeError("CV'den anlamlı metin çıkmadı (taranmış PDF olabilir — OCR gerekir)")
    guclu, zayif = yetenek_tespit(metin)
    dnm = deneyim_tahmin(metin)
    yil, kidem = dnm.profesyonel_yil, dnm.kidem
    tr = bool(re.search(r"(?i)\b(turkey|türkiye|istanbul|ankara|izmir)\b", metin))

    return {
        "_NOT": "cv-import ile ÜRETİLDİ — TASLAKTIR. Aşağıdaki alanları elle gözden geçir: "
                "calisma_izni, zorunlu_konum_kosulu, max_kidem, max_istenen_deneyim_yil.",
        "_kaynak_cv": str(Path(cv_yolu).expanduser()),
        "_uretim_tarihi": date.today().isoformat(),
        "_motor_surumu": motor_surumu(),
        "kimlik": {
            "konum": "Türkiye" if tr else "GÖZDEN GEÇİR",
            "calisma_izni": ["turkey"] if tr else ["GÖZDEN GEÇİR"],
            "deneyim_yil": yil,
            "_deneyim_toplam_gonullu_dahil": dnm.toplam_yil,
            "_deneyim_kaynagi": dnm.kaynak,
        },
        "sert_filtreler": {
            # Junior bir kademe yukarı bakabilir; üst seviyeler kendi seviyesinde kalır.
            "max_kidem": {"junior": "mid", "mid": "mid", "senior": "senior", "staff": "staff"}[kidem],
            "max_istenen_deneyim_yil": int(max(round(yil) + 3, 4)),
            "yasakli_baslik_kaliplari": SABIT_ELEME_LISTESI + _kidem_ustu_kaliplar(kidem),
            "zorunlu_konum_kosulu": ["remote_global", "remote_emea"] + (["turkey"] if tr else []),
            "sponsorluk_gerektiren_ele": True,
        },
        "rol_aileleri": (_roller := rol_aileleri_turet(set(guclu) | set(zayif))),
        # Şirketler-arası kaynaklar için İngilizce arama sorguları: en güçlü
        # yetenekler + ROL AİLESİNDEN gelen pozisyon adları.
        # NEDEN: eskiden listeye sabit olarak "software engineer" ekleniyordu. Bir
        # kontrol/havacılık mühendisi adayında bu, havuzu yazılım ilanlarıyla
        # dolduran tek en büyük kalemdi — aday yazılımcı olmadığı hâlde.
        "arama_sorgulari": list(dict.fromkeys(
            [a.lower() for a in list(guclu)[:5]] + _en_sorgular(_roller)))[:8],
        # Türk panoları İngilizce sorguyla çalışmaz; pozisyon adları Türkçe olmalı.
        # Rol ailelerinden türetilir (roller.yaml -> tr_pozisyonlar).
        "tr_arama_sorgulari": _tr_sorgular(_roller),
        # Firma profili taranacak kurumlar. Kendi listeni buraya yazabilirsin;
        # boş bırakılırsa firma taraması yapılmaz.
        # BOŞ BIRAKILIR — elle şirket listesi ölçeklenmiyor (Türkiye'de binlerce
        # banka, sigorta, otomotiv ve fabrika var). Onun yerine tr_arama_sorgulari
        # içine kariyer.net'in SEKTÖR sayfaları konuldu; onlar o sektördeki tüm
        # firmaların ilanlarını veriyor. Belirli bir kuruma odaklanmak isteyen
        # kullanıcı bu listeye kendi şirketlerini yazar (firma profili taranır).
        "tr_hedef_sirketler": [],
        **SABLON_KUYRUK,
        "yetenekler": {"guclu": guclu, "zayif": zayif},
    }


def profil_tazele(profil: dict) -> tuple[dict, list[str]]:
    """Motor güncellendiyse profilin ÜRETİLEN kısımlarını yeniler.

    CV'ye gerek yok: yetenekler ve kıdem zaten profilde saklı. Kullanıcının ELLE
    verdiği kararlar (çalışma izni, konum koşulu, şehirler, arama sorguları)
    KORUNUR — yalnız motordan gelen türetmeler tazelenir.

    Dönüş: (profil, değişenlerin listesi)
    """
    guncel = motor_surumu()
    if profil.get("_motor_surumu") == guncel:
        return profil, []

    degisen: list[str] = []
    yet = profil.get("yetenekler") or {}
    tum = set(yet.get("guclu") or {}) | set(yet.get("zayif") or {})
    sf = profil.setdefault("sert_filtreler", {})

    # kıdem tavanından, kullanıcının tespit edilmiş seviyesini geri çıkar
    tavan = sf.get("max_kidem", "mid")
    kidem = {"mid": "junior", "senior": "mid", "staff": "senior"}.get(tavan, tavan)

    yeni_kaliplar = SABIT_ELEME_LISTESI + _kidem_ustu_kaliplar(kidem)
    if yeni_kaliplar != sf.get("yasakli_baslik_kaliplari"):
        sf["yasakli_baslik_kaliplari"] = yeni_kaliplar
        degisen.append("eleme kalıpları")

    if tum:
        yeni_roller = rol_aileleri_turet(tum)
        if set(yeni_roller) != set(profil.get("rol_aileleri") or {}):
            profil["rol_aileleri"] = yeni_roller
            degisen.append("rol aileleri")
        # Türkçe sorguları kullanıcı elle değiştirdiyse dokunma
        if not profil.get("_tr_sorgu_elle"):
            yeni_tr = _tr_sorgular(profil["rol_aileleri"])
            if yeni_tr != profil.get("tr_arama_sorgulari"):
                profil["tr_arama_sorgulari"] = yeni_tr
                degisen.append("Türkçe sorgular")

    profil["_motor_surumu"] = guncel
    return profil, degisen


def yaz(profil: dict, hedef: str | Path) -> Path:
    h = Path(hedef).expanduser()
    h.parent.mkdir(parents=True, exist_ok=True)
    h.write_text(
        "# is-basvuru-bot profili — cv-import çıktısı\n"
        "# BU BİR TASLAKTIR: _NOT alanındaki maddeleri gözden geçirmeden güvenme.\n\n"
        + yaml.safe_dump(profil, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    return h
