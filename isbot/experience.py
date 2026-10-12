"""Deneyim süresi tahmini — CV biçiminden bağımsız, genel.

NEDEN AYRI MODÜL: Bu, CV ayrıştırmanın en kolay yanlış yapılan yeri. İki naif
yaklaşım da kırılır:
  - "en eski yıl" → liseden başlayanı 10 yıllık gösterir (lise başlangıç yılını yakalar)
  - "mezuniyet yılı" → üniversite okumamış / liseden sonra çalışmaya başlamış
    kişide tamamen çöker (mezuniyet yok)

Doğru yaklaşım: DENEYİM BÖLÜMÜNDEKİ tarih aralıklarının sürelerini topla.
Böylece kariyerine 17 yaşında başlayan da, 26'da başlayan da doğru ölçülür.
Örtüşen dönemler (aynı anda iki iş) tek sayılır — aralık birleşimi alınır.

Kulüp/gönüllü/öğrenci takımı satırları profesyonel deneyimden düşülür, ama
'toplam_yil' içinde raporlanır; karar kullanıcıya bırakılır.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

AY = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
AY.update({m: i for i, m in enumerate(
    "oca şub mar nis may haz tem ağu eyl eki kas ara".split(), 1)})
AY.update({"sept": 9, "june": 6, "july": 7, "summer": 6, "yaz": 6,
           "winter": 1, "spring": 3, "fall": 9, "autumn": 9})

SIMDI_KALIP = r"(?:present|current|now|günümüz|halen|devam)"
_AYAD = r"[A-Za-zÇĞİÖŞÜçğıöşü]{3,9}\.?"

# "Aug. 2020 -- June 2026" / "2022 - 2023" / "Summer 2025" / "Aug 2026 – Present"
ARALIK = re.compile(
    rf"(?i)(?:({_AYAD})\s*\.?\s*)?((?:19|20)\d{{2}})"
    rf"\s*(?:-{{1,2}}|–|—|to|ile)\s*"
    rf"(?:(?:({_AYAD})\s*\.?\s*)?((?:19|20)\d{{2}})|({SIMDI_KALIP}))"
)
# "Haziran – Temmuz 2024" / "June – July 2024": YIL YALNIZ SONDA yazılmış, aynı yıl
# içindeki kısa dönem. Yukarıdaki kalıp ilk tarafta yıl beklediği için bunu hiç
# görmüyordu. ÖLÇÜLDÜ: bir stajyer CV'sinde iki staj (2+2 ay) tamamen kayboldu —
# kısa dönemler iş deneyimi geçmişinin tamamı olabilir, kaybı doğrudan kıdemi düşürür.
AY_AY_YIL = re.compile(
    rf"(?i)(?<![\w/])({_AYAD})\s*(?:-{{1,2}}|–|—|to|ile)\s*({_AYAD})\s+((?:19|20)\d{{2}})(?![\w/])"
)
TEK_DONEM = re.compile(rf"(?i)\b(summer|yaz|winter|spring|fall|autumn)\s+((?:19|20)\d{{2}})\b")

# TÜRKÇE EKLER: başlık sözcüğü çekim eki alır ("Beceri" değil "Beceriler",
# "Sertifika" değil "Sertifikalar ve Eğitimler"). Kalıp `\b...\b` ile yazılınca
# ekli hâl eşleşmez ve bölüm hiç bulunmaz. ÖLÇÜLDÜ: Türkçe bir CV'de deneyim bölümü
# bulunamayınca süre CV GENELİNDEN toplanıyor, Projeler/Eğitim tarihleri de deneyime
# karışıyordu. Bu yüzden gövdeye `\w*` eklenir ve başlık satırının sonunda kısa bir
# kuyruğa ("… ve Eğitimler", ": ") izin verilir.
# Kuyruk SERBEST METİN OLAMAZ. İlk hâli `[^\n]{0,32}$` idi ve bölüm başlığı sanılan
# şey aslında bir UNVAN satırı oluyordu: "Proje Mimarı" -> `proje\w*` dalına,
# "Project Manager" -> `projects?` dalına takıldı ve DENEYİM BÖLÜMÜ orada kesildi.
# ÖLÇÜLDÜ: bir mimar CV'sinde bölüm 44 karakterde bitti, 7,1 yıllık deneyim 3,3
# göründü. Artık yalnız gerçek başlıkların aldığı kuyruğa izin verilir:
# bağlaçla bağlanmış ikinci bir başlık sözcüğü ("Sertifikalar ve Eğitimler"),
# iki nokta, ya da hiçbir şey.
_BAS_KUYRUK = r"(?:\s*(?:ve|and|&|/|,|-|–)\s*[\wçğıöşüÇĞİÖŞÜ]+){0,3}\s*:?\s*$"
# Başlık "experience"tan ÖNCE niteleyici alabilir: "WORK & PROJECT EXPERIENCE",
# "Work and Internship Experience", "İş ve Staj Deneyimi". ÖLÇÜLDÜ (2026-10-12, gerçek
# bir yeni mezun CV'si): başlık "WORK & PROJECT EXPERIENCE" idi, kalıp yalnız tek
# niteleyiciye ("work experience") izin verdiği için bölüm bulunamadı; süre CV
# GENELİNDEN toplandı, lisans tarihleri (2020 – 2026) deneyim sayıldı ve stajyer
# "6 yıl, senior" profili aldı. Niteleyiciler SÖZLÜKTEN gelir, serbest sözcük değil:
# "Customer Experience" bir unvan satırıdır, başlık sayılmamalı.
_NITELEYICI = (r"(?:work|professional|relevant|industry|research|internship|project|teaching|"
               r"clinical|field|military|iş|profesyonel|mesleki|staj|proje|akademik|saha)")
BOLUM_BAS = re.compile(
    rf"(?im)^[\s•·\-]*((?:{_NITELEYICI}\s*(?:&|and|ve|/|,)?\s*){{0,3}}experience|"
    r"employment(?: history)?|internships?|"
    rf"(?:{_NITELEYICI}\s*(?:&|and|ve|/|,)?\s*){{0,3}}deneyim\w*|(?:iş )?tecrübe\w*|"
    r"çalışma geçmişi|career|stajlar\w*)"
    + _BAS_KUYRUK)
BOLUM_SON = re.compile(
    r"(?im)^[\s•·\-]*(education|projects|skills|technical skills|publications|awards|"
    r"certifications?|references|languages|"
    r"eğitim\w*|projeler\w*|yetenek\w*|beceri\w*|yetkinlik\w*|sertifika\w*|yayın\w*|"
    r"başarı\w*|ödül\w*|referans\w*|yabancı dil\w*|diller)"
    + _BAS_KUYRUK)

# Profesyonel deneyimden düşülecek oluşumlar. Dikkat: çıplak "team" ELENMEZ —
# gerçek işte "Team Lead" olur. Sadece üniversite/öğrenci bağlamı niteleyicileriyle
# gelen "team" ve açık kulüp/gönüllü işaretleri sayılmaz.
GONULLU = re.compile(
    r"(?i)("
    r"\bclub\b|\bsociety\b|\bcommittee\b|\bvolunteer\b|\bvoluntary\b|"
    r"\bstudent\s+(team|chapter|branch|society)\b|\bteam\s+member\b|"
    r"\b(project|rocket|racing|robotics|formula|solar|student|university|ieee|acm)\s+team\b|"
    r"\bkul[üu]b|\btopluluk|\bg[öo]n[üu]ll[üu]|\b[öo][ğg]renci\s+(tak[ıi]m|kul[üu]b)|"
    r"\b(proje|roket|robotik)\s+tak[ıi]m|"
    # Yarışma takımı adı araya sözcük alabiliyor: "UZAYTEK Rocket Technologies Team".
    # ÖLÇÜLDÜ (2026-10-12): bu satır 2022–2025 profesyonel deneyim sayıldı, yeni mezun
    # 3 yıllık "mid" oldu. Alan sözcüğü + en çok bir ara sözcük + team, ya da yarışma izi.
    r"\b(rocket|roket|uav|[iİ]ha|robotics?|robotik|formula|solar|racing|drone)\s+\w+\s+(team|tak[ıi]m)\b|"
    r"\bteknofest\b|\b(competition|yarışma)\w*\s+(team|tak[ıi]m)\b"
    r")")


# HARF ARALIKLI BAŞLIK: tasarım şablonları başlığı harf aralığıyla dizer ("EDUCATION"
# yerine "E D U C AT I O N"); pdftotext bunu harf öbeklerine böler. ÖLÇÜLDÜ (2026-10-12,
# gerçek bir CV): "P RO F E S S I O NA L S U M M A RY", "E D U C AT I O N",
# "L A N G UAG E S" — hiçbiri başlık olarak tanınmıyordu. Satır yalnız 1-3 harflik BÜYÜK
# harf öbeklerinden oluşuyorsa birleştirilir; iki ve daha fazla boşluk sözcük arası sayılır.
# Küçük harfli öbekler ("ve ile de") ve noktalama taşıyan satırlar ("C, C++, R") dokunulmaz.
_ARALIKLI_OBEK = re.compile(r"[A-ZÇĞİÖŞÜ]{1,3}")


def _aralikli_birlestir(satir: str) -> str:
    obekler = satir.split()
    if len(obekler) < 4 or not all(_ARALIKLI_OBEK.fullmatch(o) for o in obekler):
        return satir
    girinti = satir[:len(satir) - len(satir.lstrip())]
    sozcukler = [s.replace(" ", "") for s in re.split(r"\s{2,}", satir.strip())]
    return girinti + " ".join(sozcukler)


def metin_normalize(metin: str) -> str:
    """PDF metin çıkarımının bozduğu token'ları onarır.

    PDF'ten metin çıkarırken satır, kelimenin/sayının ORTASINDA kesilebilir —
    özellikle sabit genişlikli çıktı ve iki kolonlu CV'lerde:

        Junior Security Analyst          Aug 2016 -- May 202
        0                                  <- "2020" ikiye bölünmüş

    Onarılmazsa o tarih aralığı hiç görülmez ve deneyim eksik hesaplanır
    (ölçülen: 12,8 yıl -> 6,2 yıl). Satır yapısı korunur, yalnız bölünmüş
    token'lar birleştirilir.

    AYRICA Unicode'u NFC'ye birleştirir. Bu, Türkçe CV'lerde HAYATİ:
    pdftotext (ve bazı LaTeX üretimi PDF'ler) harfleri AYRIŞTIRILMIŞ verir —
    "Ç" tek karakter değil, "C" + birleştirici çengel (U+0327) olarak gelir.
    Birleştirilmezse regex, aksanı harf saymadığı için tabanı TEK BAŞINA duran
    bir harf sanır ve sahte yetenek üretir. ÖLÇÜLDÜ (Türkçe kontrol mühendisi
    CV'si): "Gömülü/Görü/Gökkubbe" -> Go dili (güçlü, 1.0), "Çift/çalışma/Güç"
    -> C dili (güçlü, 1.0), "sensör" -> R. Aday C/Go sistem programcısı sanıldı,
    kısa listeye Ubuntu çekirdek ilanları geldi. Aynı bozulma "İş Deneyimi"
    başlığını da tanınmaz yaptığı için deneyim 2,2 yıl yerine 1,2 çıkıyordu.
    """
    metin = unicodedata.normalize("NFC", metin)
    metin = "\n".join(_aralikli_birlestir(s) for s in metin.split("\n"))
    # Yıl ikiye bölünmüş: parçaların toplamı tam 4 hane ise birleştir.
    def _yil(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        return a + b if len(a) + len(b) == 4 else m.group(0)

    metin = re.sub(r"\b((?:19|20)\d{0,2})[ \t]*\n[ \t]*(\d{1,3})\b", _yil, metin)
    # Tire ile bölünmüş kelime: "experi-\nence" -> "experience"
    metin = re.sub(r"(\w)-[ \t]*\n[ \t]*(\w)", r"\1\2", metin)
    # Aralık işareti satır sonunda kalmış: "2016 --\n  May 2020"
    metin = re.sub(r"((?:19|20)\d{2})[ \t]*(-{1,2}|–|—)[ \t]*\n[ \t]*", r"\1 \2 ", metin)
    return metin


@dataclass
class Deneyim:
    profesyonel_yil: float      # kulüp/gönüllü hariç
    toplam_yil: float           # dahil
    kidem: str
    kaynak: str                 # tahminin nereden geldiği (şeffaflık)
    araliklar: list[tuple[float, float]]


def _ay(s: str | None) -> int:
    if not s:
        return 7                                   # ay yoksa yıl ortası varsay
    return AY.get(s.strip(". ").lower()[:4], AY.get(s.strip(". ").lower()[:3], 7))


def _ondalik(yil: int, ay: int) -> float:
    return yil + (ay - 1) / 12.0


def _birlestir(araliklar: list[tuple[float, float]]) -> float:
    """Örtüşen dönemleri tek sayar (aynı anda iki iş = çift deneyim değil)."""
    if not araliklar:
        return 0.0
    araliklar = sorted(araliklar)
    toplam, bas, son = 0.0, *araliklar[0]
    for b, s in araliklar[1:]:
        if b <= son:
            son = max(son, s)
        else:
            toplam += son - bas
            bas, son = b, s
    return toplam + (son - bas)


def _deneyim_bolumu(metin: str) -> str:
    m = BOLUM_BAS.search(metin)
    if not m:
        return ""
    kalan = metin[m.end():]
    son = BOLUM_SON.search(kalan)
    return kalan[:son.start()] if son else kalan


# Eğitim satırı: deneyim bölümü bulunamayıp süre CV GENELİNDEN toplanırken lisans/lise
# tarihleri deneyim sayılmasın. ÖLÇÜLDÜ (2026-10-12): bölümü bulunamayan yeni mezun CV'sinde
# "Istanbul Technical University ... 2020 – 2026" satırı 6 yıl deneyim yazdırdı.
EGITIM_SATIRI = re.compile(
    r"(?i)(universit|üniversite|college|lisans|bachelor|b\.?sc|m\.?sc|master|yüksek lisans|"
    r"doktora|ph\.?d|\blise\b|high school|gpa|not ortalama|erasmus|exchange program|"
    r"mezuniyet|fakülte|faculty|okulu\b)")


def _araliklari_topla(blok: str, egitimi_atla: bool = False) -> tuple[list, list]:
    """(profesyonel, gönüllü) aralık listeleri."""
    simdi = _ondalik(date.today().year, date.today().month)
    prof, gon = [], []
    satirlar = blok.splitlines()
    for i, satir in enumerate(satirlar):
        # Tarih çoğu zaman kurum satırında, derece komşu satırda durur
        # ("Istanbul Technical University   2020 – 2026" / "B.Sc. in ..."); pencereye bakılır.
        if egitimi_atla and EGITIM_SATIRI.search(" ".join(satirlar[max(0, i - 1):i + 2])):
            continue
        # CV'lerde tarih bir satırda, kurum adı komşu satırda olur:
        #   "Embedded Systems Electronics            2020 -- 2022"
        #   "IEEE RAS Committee AUV Project Team, ITU"
        # Bu yüzden gönüllü/kulüp taraması satır PENCERESİ üzerinde yapılır.
        pencere = " ".join(satirlar[max(0, i - 1):i + 3])
        hedef = gon if GONULLU.search(pencere) else prof
        bulundu = False
        for m in ARALIK.finditer(satir):
            ay1, y1, ay2, y2, simdi_mi = m.groups()
            bas = _ondalik(int(y1), _ay(ay1))
            son = simdi if simdi_mi else _ondalik(int(y2), _ay(ay2))
            if son > bas and son - bas < 50:
                hedef.append((bas, son)); bulundu = True
        if not bulundu:
            for m in AY_AY_YIL.finditer(satir):     # "Haziran – Temmuz 2024"
                ay1, ay2, y = m.group(1), m.group(2), int(m.group(3))
                a1, a2 = _ay(ay1), _ay(ay2)
                # Ay adı sözlükte yoksa _ay() 7 döndürür; iki taraf da tanınmadıysa
                # bu bir tarih değil, iki sıradan sözcüktür ("Kontrol – Otomasyon 2024").
                if ay1.strip(". ").lower()[:3] not in AY and ay2.strip(". ").lower()[:3] not in AY:
                    continue
                if a2 >= a1:
                    hedef.append((_ondalik(y, a1), _ondalik(y, a2 + 1)))
                    bulundu = True
        if not bulundu:
            # "Summer 2025" / "Yaz 2025": ay yazılmamış, süre bilinmiyor. Eskiden 3 ay
            # sayılıyordu ve mevsim yok sayılıp hep Haziran–Eylül'e konuyordu. Türkiye'de
            # staj 20-40 iş günü (~1-1,5 ay), yurt dışında 10-12 hafta; ikisinin ortası
            # olan 2 ay sayılır. Ölçüldü (2026-10-08): iki "Yaz" stajlı bir CV 5 aylık
            # deneyimi 8 ay (0,7 yıl) gösteriyordu.
            for m in TEK_DONEM.finditer(satir):
                # _ay() ilk 3-4 harfe bakar; "winter"/"spring" orada tutmuyor, tam adla aranır.
                y, bas_ay = int(m.group(2)), AY.get(m.group(1).lower(), 6)
                hedef.append((_ondalik(y, bas_ay), _ondalik(y, bas_ay + 2)))
    return prof, gon


def tahmin(metin: str) -> Deneyim:
    metin = metin_normalize(metin)
    # (1) CV açıkça söylüyorsa en güvenilir kaynak odur
    m = re.search(r"(?i)\b(\d{1,2})\s*\+?\s*(?:years?|yrs?|yıl)\b[^.]{0,32}"
                  r"(?:of\s+)?(?:professional\s+|industry\s+|relevant\s+)?"
                  r"(?:experience|deneyim|tecrübe)", metin)
    if m:
        y = float(m.group(1))
        return Deneyim(y, y, _kidem(y, metin), "CV'de açıkça yazıyor", [])

    # (2) Deneyim bölümündeki sürelerin toplamı (asıl yöntem)
    blok = _deneyim_bolumu(metin)
    kaynak = "deneyim bölümündeki sürelerin toplamı"
    genel = not blok.strip()
    if genel:
        blok, kaynak = metin, "CV geneli (deneyim bölümü bulunamadı, eğitim satırları hariç)"
    prof, gon = _araliklari_topla(blok, egitimi_atla=genel)
    p_yil = round(_birlestir(prof), 1)
    t_yil = round(_birlestir(prof + gon), 1)
    if not prof and not gon:
        return Deneyim(0.0, 0.0, "junior", "tarih aralığı bulunamadı — ELLE GİR", [])
    return Deneyim(p_yil, t_yil, _kidem(p_yil, metin), kaynak, prof)


_UST_YONETICI = re.compile(r"(?i)\b(director|head of|vp of|vice president|cto|chief)\b")
# "Executive Assistant to the Managing Director": yönetici ADAYIN değil, yanında çalıştığı
# kişinin unvanı. ÖLÇÜLDÜ (2026-10-12): yönetici asistanı CV'si "staff" kıdem alıyordu ve
# kendi seviyesindeki asistan ilanları "kıdem fazla" sayılmasa da kıdem üstü kalıpları
# hiç almıyordu.
_YANINDA = re.compile(r"(?i)\b(assistant|secretary|reporting|support(ing)?|pa)\s+(directly\s+)?to"
                      r"(\s+the)?(\s+\w+){0,2}\s*$")


def _ust_yonetici_unvani(metin: str) -> bool:
    return any(not _YANINDA.search(metin[max(0, m.start() - 45):m.start()])
               for m in _UST_YONETICI.finditer(metin))


def _kidem(yil: float, metin: str) -> str:
    # "staff engineer" birebir aranınca "Staff Machine Learning Engineer" kaçıyordu.
    # Bu yüzden staff/principal sözcüğünü ünvan bağlamında (yakınında engineer/scientist/
    # developer/architect geçen) arıyoruz.
    if re.search(r"(?i)\b(staff|principal|distinguished|fellow)\b[^.\n]{0,40}"
                 r"\b(engineer|scientist|developer|architect|researcher)\b", metin[:900]) or \
       _ust_yonetici_unvani(metin[:900]):
        return "staff"
    if yil >= 6 or re.search(r"(?i)\bsenior\b", metin[:600]):
        return "senior"
    if yil >= 2.5:
        return "mid"
    return "junior"


# ---------------- güncellik ----------------
# NEDEN: Yetenek tespiti CV'deki her geçişi EŞİT sayıyordu; dört yıl önce öğrenci
# kulübünde yapılan gömülü sistem işi, bugünkü yapay zekâ işiyle aynı ağırlığı alıyordu.
# ÖLÇÜLDÜ (2026-10-12): yapay zekâ mühendisi olarak çalışan bir adayın kısa listesi
# gömülü yazılım ilanlarıyla doluydu. Kusur kişiye özel değil, mesleğe de bağlı değil:
# gömülüden ML'e geçmiş sentetik CV'de ilk 10'un 6'sı, muhasebeden İK'ya geçmiş CV'de
# 7'si ESKİ meslekten geliyordu; öğretmenlikten satışa geçmiş CV'nin 6 Türkçe sorgusunun
# 3'ü öğretmenlikti.
# Her satır, ait olduğu CV girdisinin BİTİŞ tarihini taşır; eski girdideki geçiş daha az
# sayılır. Tarihsiz satırlar (ad/unvan, özet, beceriler) 1,0 kalır — eski davranış.
# Yani eski tarihli girdisi olmayan CV'nin hiçbir değeri değişmez.
GUNCEL_YIL = 1.5      # bitişinin üstünden bu kadar yıl geçmemiş girdi tam sayılır
YARI_OMUR = 2.0       # sonrasında her YARI_OMUR yılda ağırlık yarıya iner
AGIRLIK_TABANI = 0.25  # ne kadar eski olursa olsun bir geçiş bu kadar sayılır

OZET_BAS = re.compile(
    r"(?im)^[\s•·\-]*((?:professional\s*|career\s*|executive\s*)?(?:summary|profile|objective)|"
    r"about me|özet\w*|profil\w*|hakkımda|kariyer hedef\w*)" + _BAS_KUYRUK)
_SON_YIL = re.compile(rf"(?i)(?:({_AYAD})\s*\.?\s*)?((?:19|20)\d{{2}})\s*$")
# "2015 Eylül – 2019 Haziran": YIL ÖNCE, ay sonra. Türkçe CV'lerin eğitim satırlarında
# yaygın; ARALIK ay-önce bekler ve bu satırı hiç tarihli saymıyordu. Eğitim satırı tarihsiz
# kalınca "güncel" sayılıyordu: hemşirelikten veri analistliğine geçmiş CV'de 2012'de biten
# "Hemşirelik Lisans" satırı hemşireliği bugünkü alan gibi gösterdi (ölçüldü, 2026-10-12).
YIL_AY_ARALIK = re.compile(
    rf"(?i)((?:19|20)\d{{2}})\s*(?:{_AYAD})?\s*(?:-{{1,2}}|–|—|to|ile)\s*"
    rf"(?:((?:19|20)\d{{2}})\s*({_AYAD})?|({SIMDI_KALIP}))")


def yas_agirligi(yas: float) -> float:
    """Bitişinin üstünden `yas` yıl geçmiş bir girdideki geçişin ağırlığı."""
    if yas <= GUNCEL_YIL:
        return 1.0
    return max(AGIRLIK_TABANI, 0.5 ** ((yas - GUNCEL_YIL) / YARI_OMUR))


def _satir_bitisi(satir: str, simdi: float) -> float | None:
    """Satır bir CV girdisini başlatıyorsa (tarih taşıyorsa) o girdinin bitiş zamanı."""
    son = None
    for m in ARALIK.finditer(satir):
        _, _, ay2, y2, simdi_mi = m.groups()
        e = simdi if simdi_mi else _ondalik(int(y2), _ay(ay2))
        son = e if son is None else max(son, e)
    if son is not None:
        return son
    for m in YIL_AY_ARALIK.finditer(satir):
        y2, ay2, simdi_mi = m.group(2), m.group(3), m.group(4)
        e = simdi if simdi_mi else _ondalik(int(y2), _ay(ay2) if ay2 else 7)
        son = e if son is None else max(son, e)
    if son is not None:
        return son
    m = AY_AY_YIL.search(satir)
    if m and (m.group(1).strip(". ").lower()[:3] in AY or m.group(2).strip(". ").lower()[:3] in AY):
        return _ondalik(int(m.group(3)), _ay(m.group(2)) + 1)
    m = TEK_DONEM.search(satir)
    if m:
        return _ondalik(int(m.group(2)), AY.get(m.group(1).lower(), 6) + 2)
    # Sağa yaslanmış tek yıl: "ROKETSAN — Stajyer        2025", "Kitapçevir …   2026".
    m = _SON_YIL.search(satir.rstrip())
    if m and len(satir.rstrip()) > 4:
        ay = m.group(1)
        if ay and ay.strip(". ").lower()[:3] in AY:
            return _ondalik(int(m.group(2)), _ay(ay))
        return int(m.group(2)) + 0.5
    return None


# Beceri bölümü başlığı. Altındaki satırlar tarihsizdir ama "güncel kullanım" kanıtı da
# sayılmaz: insanlar bir zamanlar yaptıkları her şeyi buraya yazar.
BECERI_BAS = re.compile(
    r"(?im)^[\s•·\-]*((?:technical |core |key )?(?:skills?|competenc\w*)|technolog\w*|"
    r"tools(?: and technologies)?|teknik beceri\w*|beceri\w*|yetenek\w*|yetkinlik\w*|"
    r"teknoloji\w*|uzmanlık alan\w*|bilgisayar bilgi\w*)" + _BAS_KUYRUK)


def satir_agirliklari(metin: str, simdi: float | None = None) -> list[tuple[float, str]]:
    """Her satır için (güncellik ağırlığı, tür). Tür: "tarihli" (bir CV girdisine ait),
    "beceri" (beceri bölümü), "tarihsiz" (ad/unvan, özet, tarihsiz bölüm) ya da "baslik"
    (bölüm başlığının kendisi; ağırlığı 0 — "Eğitim" başlığı bir beceri kanıtı değildir).

    Tarih taşıyan satır yeni bir girdi başlatır; sonraki satırlar (kurum, madde işaretleri,
    teknoloji satırı) o girdinin tarihini devralır. Bölüm başlığı bağlamı sıfırlar. Girdi
    `metin_normalize`'dan geçmiş olmalı (satır sayısı yetenek taramasıyla birebir aynı
    kalsın diye burada yeniden normalize edilmez).
    """
    if simdi is None:
        simdi = _ondalik(date.today().year, date.today().month)
    cikti: list[tuple[float, str]] = []
    bitis: float | None = None
    beceri = False
    for satir in metin.split("\n"):
        if BECERI_BAS.search(satir):
            bitis, beceri = None, True
            cikti.append((0.0, "baslik"))
            continue
        if BOLUM_BAS.search(satir) or BOLUM_SON.search(satir) or OZET_BAS.search(satir):
            bitis, beceri = None, False
            cikti.append((0.0, "baslik"))
            continue
        if beceri:
            cikti.append((1.0, "beceri"))
            continue
        e = _satir_bitisi(satir, simdi)
        if e is not None:
            bitis = e
        if bitis is None:
            cikti.append((1.0, "tarihsiz"))
        else:
            cikti.append((yas_agirligi(max(0.0, simdi - bitis)), "tarihli"))
    return cikti
