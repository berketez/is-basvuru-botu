"""CV ↔ ilan eşleştirme.

Bu modülde HİÇBİR kişiye özel bilgi yok — her şey profile.yaml'dan gelir.
Kendi CV'nle çalıştırmak için sadece o dosyayı değiştir (veya cv_import ile üret).

Tasarım: kara kutu gömme (embedding) yerine AÇIKLANABİLİR kural + ağırlık.
Sebep: "neden bu ilan?" ve "neyi tutturamıyorum?" sorularının cevabı görünür olmalı.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Job

# ---------- ALAN SAHİPLİĞİ ----------
# Bazı kelimeler bir ilanın hangi alana AİT olduğunu tek başına belirler. Başlıkta
# böyle bir kelime varsa ve adayın CV'sinde o alan YOKSA, ilan o adaya ait değildir —
# başka bir ailenin geniş kalıbına tesadüfen uysa bile.
#
# Ölçüldü: makine mühendisine "Associate SECURITY Research Engineer" ("research
# engineer" kalıbından), platform junior'a "UX DESIGNER - Infrastructure"
# ("infrastructure" kalıbından), blockchain'ciye "Crypto Analyst & TRADER" geliyordu.
ALAN_ISARETI: dict[str, str] = {
    "guvenlik":       r"(?i)\b(security|cyber|infosec|appsec|malware|penetration test|soc analyst)\b",
    "mobil":          r"(?i)\b(ios|android|mobile app|swiftui)\b",
    "oyun":           r"(?i)\b(game|unity|unreal|gameplay)\b",
    "gomulu":         r"(?i)\b(embedded|firmware|rtos|kernel|device driver|bsp)\b",
    "blockchain":     r"(?i)\b(blockchain|web3|solidity|smart contract|defi)\b",
    "makine_tasarim": r"(?i)\b(mechanical|manufacturing|hvac|cnc)\b",
    "urun":           r"(?i)\b(product (manager|owner)|program manager)\b",
    "qa":             r"(?i)\b(qa|sdet|quality assurance)\b",
    "frontend":       r"(?i)\b(frontend|front[- ]end|ux designer|ui designer)\b",
    "platform_sre":   r"(?i)\b(sre|site reliability)\b",
    "veri_muh":       r"(?i)\b(etl|data warehouse)\b",
    # Hiçbir mühendislik CV'sinde bu aileler olmaz; dolayısıyla bu işaretleri taşıyan
    # ilan daima reddedilir. Ölçüldü: pentester'a "Safety & Security COUNSEL" (avukat),
    # ML mühendisine "Manager, PEOPLE ANALYTICS" (İK) geliyordu.
    "hukuk":          r"(?i)\b(counsel|attorney|lawyer|legal|compliance officer|paralegal)\b",
    "insan_kaynaklari": r"(?i)\b(people (analytics|operations|partner|team)|human resources|"
                        r"talent (acquisition|partner)|recruiting|hr business)\b",
    "finans_muhasebe": r"(?i)\b(accountant|accounting|payroll|auditor|tax |treasury)\b",
}
# Hiçbir mühendislik ailesine ait olmayan, ama sık karışan roller
YABANCI_ISARET = r"(?i)\b(trader|trading desk|portfolio manager|actuary|paralegal|nurse|chef)\b"


def _alan_catismasi(baslik: str, aileler: set[str]) -> str | None:
    """Başlık, adayda OLMAYAN bir alanın işaretini taşıyorsa o alanın adını döndürür."""
    import re as _re
    if _re.search(YABANCI_ISARET, baslik):
        return "meslek dışı"
    for aile, kalip in ALAN_ISARETI.items():
        if aile in aileler:
            continue
        if _re.search(kalip, baslik):
            return aile
    return None


# ---------- kıdem ----------
KIDEM_SIRA = {"junior": 0, "mid": 1, "senior": 2, "staff": 3}
KIDEM_KALIP = [
    (re.compile(r"(?i)\b(intern|stajyer|working student)\b"), "junior"),
    (re.compile(r"(?i)\b(junior|entry[- ]level|new ?grad|graduate|associate|jr\.?)\b"), "junior"),
    (re.compile(r"(?i)\b(staff|principal|distinguished|fellow|head of|director|vp|chief)\b"), "staff"),
    (re.compile(r"(?i)\b(senior|sr\.?|lead)\b"), "senior"),
]
# İSTENEN deneyim yılı. Dikkat: "we have 40 years of experience" ŞİRKETİN kendi
# tecrübesidir, adaydan istenen değil (ölçüldü: iki ilan '40 yıl istiyor' diye elendi).
# Bu yüzden (a) şirket-övgüsü bağlamı dışlanır, (b) bir "şart" ipucu aranır,
# (c) 20 yılın üstü zaten şart olamaz kabul edilir.
YIL_KALIP = re.compile(
    r"(?i)\b(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?|yıl)\b"
    r"[^.]{0,40}?(?:experience|deneyim|tecrübe)")
# Şirketin kendini anlattığı kalıplar — bu bağlamda geçen yıl sayısı şart değildir.
OVGU_KALIP = re.compile(r"(?i)(we (have|bring|offer)|our (team|company|firm|founders?)|"
                        r"combined|founded|since \d{4}|over \d+ years|with \d+\+? years of "
                        r"(combined|industry) )")
# Şart ipuçları — bunlardan biri yakında geçmeliyse sayı gerçekten adaydan isteniyor.
SART_IPUCU = re.compile(r"(?i)(minimum|at least|requires?|required|must have|you (have|will have|"
                        r"bring)|looking for|ideally|preferably|proven|en az|aranan|gereklilik|"
                        r"qualification|\d\+\s*(years?|yıl))")

# ---------- konum / çalışma izni ----------
TR_KALIP = re.compile(r"(?i)\b(turkey|türkiye|turkiye|istanbul|i̇stanbul|ankara|izmir|eskişehir|eskisehir)\b")
UZAK_KALIP = re.compile(r"(?i)\b(remote|remoto|remota|uzaktan|work from home|wfh|distributed|anywhere|télétravail|fernarbeit)\b")
GLOBAL_KALIP = re.compile(r"(?i)\b(remote[- ]?(global|worldwide|anywhere|first)|worldwide|globally|anywhere in the world|any (time ?zone|location))\b")
EMEA_KALIP = re.compile(r"(?i)\b(emea|europe|european|eu[- ]based|cet|emea[- ]?remote)\b")
ABD_KILIT = re.compile(r"(?i)(authorized to work in the (us|united states)|must be (based|located) in the (us|united states)|us[- ]based only|require.{0,20}u\.?s\.? (citizen|work authorization)|green card)")
SPONSOR_YOK = re.compile(r"(?i)(unable to (provide|offer) (visa )?sponsor|do(es)? not (provide|offer|sponsor).{0,25}(visa|sponsorship)|no visa sponsorship|without (the need for )?sponsorship)")


@dataclass
class Puan:
    toplam: float = 0.0                     # 0..100
    elendi: bool = False
    eleme_sebebi: str = ""
    rol_ailesi: str = ""
    rol_puan: float = 0.0
    yetenek_puan: float = 0.0
    eslesen_yetenekler: list[str] = field(default_factory=list)
    eksik_yetenekler: list[str] = field(default_factory=list)
    konum_durumu: str = ""
    kidem: str = ""
    istenen_yil: int | None = None
    bilgilendirici_eslesme: int = 0
    alan_disi: bool = False
    bonuslar: list[str] = field(default_factory=list)
    uyarilar: list[str] = field(default_factory=list)


def _kidem_bul(job: Job) -> str:
    for kalip, k in KIDEM_KALIP:
        if kalip.search(job.title):
            return k
    for kalip, k in KIDEM_KALIP:
        if kalip.search(job.description[:1500]):
            return k
    return "mid"


def _istenen_yil(job: Job) -> int | None:
    """İlanın adaydan istediği deneyim yılı. Şirketin kendi tecrübesini anlattığı
    cümleler sayılmaz."""
    for m in YIL_KALIP.finditer(job.description):
        yil = int(m.group(1))
        if yil > 20:                       # 20+ yıl bir işe alım şartı değildir
            continue
        pencere = job.description[max(0, m.start() - 90):m.end() + 40]
        if OVGU_KALIP.search(pencere):      # "we have 40 years of experience"
            continue
        if not SART_IPUCU.search(pencere):  # şart ipucu yoksa güvenmiyoruz
            continue
        return yil
    return None


ABD_EYALET = {
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in","ia","ks","ky","la",
    "me","md","ma","mi","mn","ms","mo","mt","ne","nv","nh","nj","nm","ny","nc","nd","oh","ok",
    "or","pa","ri","sc","sd","tn","tx","ut","vt","va","wa","wv","wi","wy","dc",
    # Tam adlar: "Remote - California" gibi konumlar kısaltma taşımıyor ve ülkeye
    # çözülemeyip eleniyordu. "Georgia" BİLEREK yok — aynı adı taşıyan ülke var.
    "california","texas","florida","new york state","illinois","pennsylvania","ohio",
    "michigan","north carolina","south carolina","new jersey","virginia","west virginia",
    "arizona","massachusetts","tennessee","indiana","missouri","maryland","wisconsin",
    "colorado","minnesota","alabama","louisiana","kentucky","oregon","oklahoma",
    "connecticut","iowa","utah","nevada","arkansas","mississippi","kansas","nebraska",
    "idaho","new mexico","hawaii","new hampshire","maine","montana","rhode island",
    "delaware","south dakota","north dakota","alaska","vermont","wyoming",
    "washington state","district of columbia",
}
# --------------------------------------------------------------------------
# ÜLKE KATALOĞU — TEK KAYNAK
# Arayüzdeki "çalışma iznim var" listesi, ilan konumunun ülkeye çözülmesi ve
# bölge bilgisi hep buradan türer.
#
# NEDEN MERKEZİ: İlk sürümde arayüzde yalnızca ABD / BK / Almanya kutusu vardı,
# oysa motor 40+ ülkeyi tanıyordu. İsviçre'de çalışma izni olan kullanıcı o
# kutuyu hiç göremediği için İsviçre ilanları "switzerland — izin yok" diye
# eleniyordu; kullanıcının elinde düzeltme imkânı yoktu. Liste artık tek yerde
# durur ve arayüz /api/ulkeler ile bunu okur — ülke eklemek için tek dosya.
#
# Alan sırası: (etiket, Türkçe ad, bölge, ilan metninde görülebilen adlar)
ULKELER: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    # --- Avrupa ---
    ("turkey",      "Türkiye",           "avrupa", ("turkey", "türkiye", "turkiye")),
    ("uk",          "Birleşik Krallık",  "avrupa", ("united kingdom", "uk", "u.k.", "england",
                                                   "scotland", "wales", "great britain", "britain",
                                                   "ingiltere", "bk")),
    ("ireland",     "İrlanda",           "avrupa", ("ireland",)),
    ("germany",     "Almanya",           "avrupa", ("germany", "deutschland")),
    ("france",      "Fransa",            "avrupa", ("france",)),
    ("netherlands", "Hollanda",          "avrupa", ("netherlands", "the netherlands", "holland",
                                                   "nederland")),
    ("belgium",     "Belçika",           "avrupa", ("belgium",)),
    ("luxembourg",  "Lüksemburg",        "avrupa", ("luxembourg",)),
    ("switzerland", "İsviçre",           "avrupa", ("switzerland", "schweiz", "suisse")),
    ("austria",     "Avusturya",         "avrupa", ("austria", "österreich")),
    ("spain",       "İspanya",           "avrupa", ("spain", "españa", "espana")),
    ("portugal",    "Portekiz",          "avrupa", ("portugal",)),
    ("italy",       "İtalya",            "avrupa", ("italy", "italia")),
    ("greece",      "Yunanistan",        "avrupa", ("greece",)),
    ("cyprus",      "Kıbrıs",            "avrupa", ("cyprus",)),
    ("malta",       "Malta",             "avrupa", ("malta",)),
    ("poland",      "Polonya",           "avrupa", ("poland", "polska")),
    ("czechia",     "Çekya",             "avrupa", ("czechia", "czech republic")),
    ("slovakia",    "Slovakya",          "avrupa", ("slovakia",)),
    ("hungary",     "Macaristan",        "avrupa", ("hungary",)),
    ("romania",     "Romanya",           "avrupa", ("romania",)),
    ("bulgaria",    "Bulgaristan",       "avrupa", ("bulgaria",)),
    ("croatia",     "Hırvatistan",       "avrupa", ("croatia",)),
    ("slovenia",    "Slovenya",          "avrupa", ("slovenia",)),
    ("serbia",      "Sırbistan",         "avrupa", ("serbia",)),
    ("ukraine",     "Ukrayna",           "avrupa", ("ukraine",)),
    ("estonia",     "Estonya",           "avrupa", ("estonia",)),
    ("latvia",      "Letonya",           "avrupa", ("latvia",)),
    ("lithuania",   "Litvanya",          "avrupa", ("lithuania",)),
    ("sweden",      "İsveç",             "avrupa", ("sweden", "sverige")),
    ("denmark",     "Danimarka",         "avrupa", ("denmark",)),
    ("norway",      "Norveç",            "avrupa", ("norway",)),
    ("finland",     "Finlandiya",        "avrupa", ("finland",)),
    ("iceland",     "İzlanda",           "avrupa", ("iceland",)),
    # --- Orta Doğu ---
    ("israel",      "İsrail",            "orta_dogu", ("israel",)),
    ("uae",         "BAE",               "orta_dogu", ("uae", "united arab emirates", "u.a.e.",
                                                  "bae", "birleşik arap emirlikleri", "dubai")),
    ("saudi",       "Suudi Arabistan",   "orta_dogu", ("saudi arabia", "ksa")),
    ("qatar",       "Katar",             "orta_dogu", ("qatar",)),
    ("jordan",      "Ürdün",             "orta_dogu", ("jordan",)),
    # --- Afrika ---
    ("southafrica", "Güney Afrika",      "afrika", ("south africa",)),
    ("egypt",       "Mısır",             "afrika", ("egypt",)),
    ("morocco",     "Fas",               "afrika", ("morocco",)),
    ("tunisia",     "Tunus",             "afrika", ("tunisia",)),
    ("nigeria",     "Nijerya",           "afrika", ("nigeria",)),
    ("kenya",       "Kenya",             "afrika", ("kenya",)),
    # --- Kuzey Amerika ---
    ("usa",         "ABD",               "kuzey_amerika",
     ("united states", "united states of america", "usa", "us", "u.s.", "u.s.a.",
      "abd", "amerika", "amerika birleşik devletleri")),
    ("canada",      "Kanada",            "kuzey_amerika", ("canada",)),
    # --- Latin Amerika ---
    ("mexico",      "Meksika",           "latin_amerika", ("mexico", "méxico")),
    ("brazil",      "Brezilya",          "latin_amerika", ("brazil", "brasil")),
    ("argentina",   "Arjantin",          "latin_amerika", ("argentina",)),
    ("chile",       "Şili",              "latin_amerika", ("chile",)),
    ("colombia",    "Kolombiya",         "latin_amerika", ("colombia",)),
    ("peru",        "Peru",              "latin_amerika", ("peru",)),
    ("uruguay",     "Uruguay",           "latin_amerika", ("uruguay",)),
    ("costarica",   "Kosta Rika",        "latin_amerika", ("costa rica",)),
    # --- Asya-Pasifik ---
    ("india",       "Hindistan",         "asya_pasifik", ("india",)),
    ("pakistan",    "Pakistan",          "asya_pasifik", ("pakistan",)),
    ("china",       "Çin",               "asya_pasifik", ("china",)),
    ("hongkong",    "Hong Kong",         "asya_pasifik", ("hong kong", "hongkong")),
    ("taiwan",      "Tayvan",            "asya_pasifik", ("taiwan",)),
    ("japan",       "Japonya",           "asya_pasifik", ("japan",)),
    ("korea",       "Güney Kore",        "asya_pasifik", ("korea", "south korea")),
    ("singapore",   "Singapur",          "asya_pasifik", ("singapore",)),
    ("malaysia",    "Malezya",           "asya_pasifik", ("malaysia",)),
    ("indonesia",   "Endonezya",         "asya_pasifik", ("indonesia",)),
    ("thailand",    "Tayland",           "asya_pasifik", ("thailand",)),
    ("vietnam",     "Vietnam",           "asya_pasifik", ("vietnam", "viet nam")),
    ("philippines", "Filipinler",        "asya_pasifik", ("philippines",)),
    ("australia",   "Avustralya",        "asya_pasifik", ("australia",)),
    ("newzealand",  "Yeni Zelanda",      "asya_pasifik", ("new zealand",)),
)

BOLGE_ADI = {"avrupa": "Avrupa", "orta_dogu": "Orta Doğu", "afrika": "Afrika",
             "kuzey_amerika": "Kuzey Amerika", "latin_amerika": "Latin Amerika",
             "asya_pasifik": "Asya-Pasifik"}

ULKE_ADI = {e: ad for e, ad, _, _ in ULKELER}                 # etiket -> "İsviçre"
ULKE_BOLGE = {e: b for e, _, b, _ in ULKELER}                 # etiket -> "avrupa"
ULKE_ETIKET = {t: e for e, _, _, takma in ULKELER for t in takma}   # "schweiz" -> switzerland
# EMEA uzaktan kapsamı: Avrupa + Orta Doğu + Afrika (TR'den başvurulabilir kabul edilir).
EMEA_ULKE = {e for e, _, b, _ in ULKELER if b in ("avrupa", "orta_dogu", "afrika")}

# Şehir -> ülke. NEDEN GEREKLİ: ATS'lerin çoğu konumu yalnız şehirle yazar
# ("Zurich", "Amsterdam"). Şehir ülkeye çözülemeyince ilan "ofis: Zurich" diye
# elenirdi; kullanıcının İsviçre izni işe yaramazdı. Yalnız TEK ANLAMLI şehirler
# listelenir — "Cambridge", "Birmingham", "Paris" (Texas) gibi iki ülkede birden
# bulunan adlar bilerek dışarıda bırakıldı, yanlış ülkeye çivilemek elemekten kötüdür.
SEHIR_ULKE = {
    "berlin": "germany", "munich": "germany", "münchen": "germany", "hamburg": "germany",
    "frankfurt": "germany", "cologne": "germany", "köln": "germany", "stuttgart": "germany",
    "düsseldorf": "germany", "dusseldorf": "germany", "leipzig": "germany",
    "zurich": "switzerland", "zürich": "switzerland", "geneva": "switzerland",
    "lausanne": "switzerland", "basel": "switzerland", "bern": "switzerland",
    "amsterdam": "netherlands", "rotterdam": "netherlands", "utrecht": "netherlands",
    "eindhoven": "netherlands", "the hague": "netherlands",
    "brussels": "belgium", "antwerp": "belgium", "ghent": "belgium",
    "vienna": "austria", "wien": "austria", "graz": "austria",
    "dublin": "ireland", "cork": "ireland",
    "london": "uk", "manchester": "uk", "edinburgh": "uk", "glasgow": "uk", "leeds": "uk",
    "bristol": "uk", "liverpool": "uk", "belfast": "uk", "sheffield": "uk", "cardiff": "uk",
    "madrid": "spain", "barcelona": "spain", "valencia": "spain", "seville": "spain",
    "malaga": "spain", "málaga": "spain", "bilbao": "spain",
    "lisbon": "portugal", "lisboa": "portugal", "porto": "portugal", "braga": "portugal",
    "milan": "italy", "milano": "italy", "rome": "italy", "roma": "italy", "turin": "italy",
    "bologna": "italy", "naples": "italy",
    "lyon": "france", "marseille": "france", "toulouse": "france", "bordeaux": "france",
    "nantes": "france", "lille": "france", "sophia antipolis": "france",
    "stockholm": "sweden", "gothenburg": "sweden", "göteborg": "sweden", "malmö": "sweden",
    "malmo": "sweden", "copenhagen": "denmark", "københavn": "denmark", "aarhus": "denmark",
    "oslo": "norway", "bergen": "norway", "trondheim": "norway",
    "helsinki": "finland", "espoo": "finland", "tampere": "finland",
    "reykjavik": "iceland", "reykjavík": "iceland",
    "warsaw": "poland", "warszawa": "poland", "krakow": "poland", "kraków": "poland",
    "wroclaw": "poland", "wrocław": "poland", "gdansk": "poland", "poznan": "poland",
    "prague": "czechia", "praha": "czechia", "brno": "czechia",
    "bratislava": "slovakia", "budapest": "hungary", "bucharest": "romania",
    "bucuresti": "romania", "cluj": "romania", "cluj-napoca": "romania", "iasi": "romania",
    "sofia": "bulgaria", "zagreb": "croatia", "ljubljana": "slovenia", "belgrade": "serbia",
    "kyiv": "ukraine", "kiev": "ukraine", "lviv": "ukraine",
    "tallinn": "estonia", "riga": "latvia", "vilnius": "lithuania",
    "athens": "greece", "thessaloniki": "greece", "nicosia": "cyprus",
    "tel aviv": "israel", "tel aviv-yafo": "israel", "haifa": "israel", "jerusalem": "israel",
    "dubai": "uae", "abu dhabi": "uae", "doha": "qatar", "riyadh": "saudi", "jeddah": "saudi",
    "amman": "jordan", "cairo": "egypt", "casablanca": "morocco", "rabat": "morocco",
    "tunis": "tunisia", "lagos": "nigeria", "abuja": "nigeria", "nairobi": "kenya",
    "cape town": "southafrica", "johannesburg": "southafrica", "pretoria": "southafrica",
    "new york": "usa", "new york city": "usa", "nyc": "usa", "brooklyn": "usa",
    "san francisco": "usa", "palo alto": "usa", "mountain view": "usa", "sunnyvale": "usa",
    "menlo park": "usa", "santa clara": "usa", "san jose": "usa", "los angeles": "usa",
    "san diego": "usa", "seattle": "usa", "bellevue": "usa", "redmond": "usa",
    "chicago": "usa", "boston": "usa", "cambridge, ma": "usa", "austin": "usa",
    "dallas": "usa", "houston": "usa", "denver": "usa", "atlanta": "usa", "miami": "usa",
    "philadelphia": "usa", "pittsburgh": "usa", "phoenix": "usa", "portland": "usa",
    "salt lake city": "usa", "minneapolis": "usa", "washington": "usa", "washington dc": "usa",
    "toronto": "canada", "vancouver": "canada", "montreal": "canada", "montréal": "canada",
    "ottawa": "canada", "calgary": "canada", "waterloo": "canada",
    "mexico city": "mexico", "guadalajara": "mexico", "monterrey": "mexico",
    "sao paulo": "brazil", "são paulo": "brazil", "rio de janeiro": "brazil",
    "belo horizonte": "brazil", "buenos aires": "argentina", "santiago": "chile",
    "bogota": "colombia", "bogotá": "colombia", "medellin": "colombia", "lima": "peru",
    "montevideo": "uruguay", "san jose, costa rica": "costarica",
    "bangalore": "india", "bengaluru": "india", "hyderabad": "india", "pune": "india",
    "mumbai": "india", "chennai": "india", "gurgaon": "india", "gurugram": "india",
    "noida": "india", "new delhi": "india", "karachi": "pakistan", "lahore": "pakistan",
    "beijing": "china", "shanghai": "china", "shenzhen": "china", "guangzhou": "china",
    "hangzhou": "china", "taipei": "taiwan", "tokyo": "japan", "osaka": "japan",
    "kyoto": "japan", "yokohama": "japan", "seoul": "korea", "busan": "korea",
    "kuala lumpur": "malaysia", "jakarta": "indonesia", "bangkok": "thailand",
    "hanoi": "vietnam", "ho chi minh city": "vietnam", "manila": "philippines",
    "cebu": "philippines", "sydney": "australia", "melbourne": "australia",
    "brisbane": "australia", "perth": "australia", "canberra": "australia",
    "auckland": "newzealand", "wellington": "newzealand",
}
# "Avrupa'nın herhangi bir yerinden" diyen ilanlar — ülkeye çivilenmiş olanın aksine
# bunlara TR'den başvurulabilir.
EMEA_ACIK = re.compile(r"(?i)(anywhere in (europe|emea|the eu\b)|from anywhere in europe|"
                       r"any (country|location) (in|within) (europe|emea)|"
                       r"europe[- ]wide|emea[- ]wide|located anywhere in emea)")
# Ana dil/akıcılık şartı: TR+EN dışında bir dil isteniyorsa eleme sebebi.
DIL_SARTI = re.compile(r"(?i)\b(italian|german|french|spanish|dutch|polish|portuguese|arabic|"
                       r"hebrew|japanese|korean|mandarin|chinese|russian|swedish|danish|"
                       r"norwegian|finnish|czech|romanian|greek)\b[^.]{0,40}"
                       r"\b(speaker|speaking|native|fluen|proficien|required|mandatory)\b")
GENEL_KONUM = re.compile(r"(?i)^\s*(remote|uzaktan|anywhere|global|worldwide|multiple locations|"
                         r"various|flexible|distributed|remote[- ]?first)\s*$")

# YALNIZ KONUM ALANINDA aranır: alan baştan sona "her yerden" diyorsa.
# NEDEN AYRI: GLOBAL_KALIP ilan METNİNDE de aranıyor, oraya gevşek bir "global"
# konulamaz ("a global leader in..." cümlesi her ilanda var). Konum alanı ise
# ilanın kendi beyanıdır, orada "Global" tek başına yeterli kanıttır.
# ÖLÇÜLDÜ: "Remote, Global" / "Distributed, Global" / "Remote - Global" yazan 96 ilan
# ülkeye de çözülemediği için "ofis: Remote, Global" deyip ELENİYORDU — oysa bunlar
# tam da Türkiye'den başvurulabilecek ilanlar.
GLOBAL_KONUM = re.compile(
    r"(?i)^[\s,\-–—/()]*"
    r"(remote|uzaktan|distributed|fully[- ]remote|remote[- ]first|work from anywhere)?"
    r"[\s,\-–—/()]*"
    r"(global|worldwide|anywhere|any ?where in the world|dünya geneli)"
    r"[\s,\-–—/()]*"
    r"(remote|uzaktan|distributed|first)?[\s,\-–—/()]*$")


# Ülke değil BÖLGE yazan konum alanları. Tek ülkeye çözülemedikleri için
# "ofis: North America" deyip eleniyorlardı.
BOLGE_ULKE = {
    "north america": {"usa", "canada"}, "kuzey amerika": {"usa", "canada"},
    "benelux": {"netherlands", "belgium", "luxembourg"},
    "dach": {"germany", "austria", "switzerland"},
    "nordics": {"sweden", "denmark", "norway", "finland", "iceland"},
    "scandinavia": {"sweden", "denmark", "norway"},
    "baltics": {"estonia", "latvia", "lithuania"},
    "iberia": {"spain", "portugal"},
}


def _ulke_etiketleri(konum: str) -> set[str]:
    """'Tokyo, Japan' -> {japan} | 'Washington, DC' -> usa | 'Germany (Remote)' -> germany
    | 'Zurich' -> switzerland | 'Remote' -> None

    İki düzeltme yapıldı:
      * Parantez de ayraç sayılır. Önceden "Germany (Remote)" tek parça olduğu için
        hiçbir ülkeye çözülmüyordu; Almanya çalışma izni olan kullanıcıda bile ilan
        "ofis: Germany (Remote)" diye eleniyordu.
      * Ülke adı yoksa şehre bakılır. ATS'lerin çoğu konumu yalnız şehirle yazar
        ("Zurich", "Amsterdam"); şehir çözülmeyince ülke izni hiç işe yaramıyordu.
    """
    # Toplayıcılar konumu "USA Only", "UK Only", "Germany (Remote)" diye beyan eder;
    # çalışma şekli/nitelik ekleri ülke aramasından önce atılır.
    konum = re.sub(r"(?i)\b(only|based|residents?|timezone[s]?|remote|hybrid|on-?site|"
                   r"onsite|flexible|office|zone \d+|job requisitions?)\b", " ", konum)
    parcalar = [p for x in re.split(r"[,/|()\[\]&+]", konum)
                if (p := x.strip().lower().strip(" -–—.").strip())]

    def _bak(x: str) -> str | None:
        if x in ULKE_ETIKET:
            return ULKE_ETIKET[x]
        if x in ABD_EYALET:
            return "usa"
        return None

    bulunan: set[str] = set()
    for x in reversed(parcalar):
        if x in BOLGE_ULKE:                  # "North America" -> {usa, canada}
            bulunan |= BOLGE_ULKE[x]
        elif (e := _bak(x)):
            bulunan.add(e)
    # TİRE İKİNCİ AŞAMADA bölünür, ilk aşamada değil: "Tel Aviv-Yafo" ve "Cluj-Napoca"
    # bütün olarak da anlamlıdır. ÖLÇÜLDÜ: "Remote - United States", "US - Remote Zone 1"
    # gibi 1.498 ilan tire yüzünden hiçbir ülkeye çözülemiyordu.
    if not bulunan:
        for x in reversed(parcalar):
            for alt in re.split(r"[-–—]", x):
                alt = alt.strip()
                if alt in BOLGE_ULKE:
                    bulunan |= BOLGE_ULKE[alt]
                elif alt and (e := _bak(alt)):
                    bulunan.add(e)
    if not bulunan:                          # ülke yok: şehirden çöz
        for x in parcalar:
            if x in SEHIR_ULKE:
                bulunan.add(SEHIR_ULKE[x])
                continue
            for alt in re.split(r"[-–—]", x):
                if (alt := alt.strip()) in SEHIR_ULKE:
                    bulunan.add(SEHIR_ULKE[alt])
                    break
    return bulunan


def _ulke_etiketi(konum: str) -> str | None:
    """Geriye dönük tek etiketli sürüm (testler ve tek ülke beklenen çağrılar için)."""
    e = _ulke_etiketleri(konum)
    return sorted(e)[0] if e else None


# Türkiye'deki ilanda şehri okunur göstermek için. NEDEN: kullanıcı "Türkiye"yi
# işaretlediğinde listede yalnız "Türkiye" yazıyordu; ilanın İstanbul ofisi mi
# yoksa ülke içinden uzaktan mı olduğu karttan anlaşılmıyordu.
TR_SEHIR_ADI = {"istanbul": "İstanbul", "i̇stanbul": "İstanbul", "ankara": "Ankara",
                "izmir": "İzmir", "i̇zmir": "İzmir", "eskisehir": "Eskişehir",
                "eskişehir": "Eskişehir", "bursa": "Bursa", "antalya": "Antalya",
                "kocaeli": "Kocaeli", "adana": "Adana", "konya": "Konya",
                "gebze": "Gebze", "tekirdag": "Tekirdağ", "tekirdağ": "Tekirdağ"}


def _tr_yer(konumlar: list[str]) -> str:
    """['Istanbul, Turkey'] -> ' · İstanbul' | ['Turkey'] -> '' """
    for k in konumlar:
        if not TR_KALIP.search(k):
            continue
        for parca in re.split(r"[,/|()]", k):
            ad = parca.strip().lower().rstrip(".")
            if ad in TR_SEHIR_ADI:
                return " · " + TR_SEHIR_ADI[ad]
    return ""


def _konum_degerlendir(job: Job, izinler: list[str]) -> tuple[str, bool]:
    """(durum_açıklaması, uygun_mu)

    TASARIM KARARI — BELİRSİZLİKTE KAPIYI KAPAT:
    ATS'lerin 'remote' bayrağı çoğu zaman 'o ülke içinde evden' demektir, 'dünyanın
    her yerinden' demek DEĞİLDİR. Ölçüldü: OpenAI'ın 'Applied AI Engineer - Tokyo'
    ve 'Cyber, Government / Washington DC' ilanları isRemote=true taşıyor. Bu bayrağa
    güvenip 'kapsam belirsiz -> kabul' dendiğinde kısa liste Türkiye'den başvurulamayacak
    ABD ofis ilanlarıyla doluyordu. Bu yüzden:
      - somut şehir/ülke varsa ilan O ÜLKEYE bağlıdır (remote bayrağı bunu değiştirmez),
      - kapsam doğrulanamıyorsa ilan UYGUN SAYILMAZ.
    """
    konumlar = [k for k in job.locations if k]
    metin = job.description[:6000]
    baslik_alan = " ".join(konumlar) + " " + job.title

    # 1) Türkiye açıkça geçiyorsa
    if TR_KALIP.search(baslik_alan):
        return "Türkiye" + _tr_yer(konumlar), "turkey" in izinler

    # 2) Konum alanı açıkça global/worldwide diyorsa
    # GLOBAL_KONUM yalnız konum alanına bakar ("Remote, Global"); GLOBAL_KALIP
    # başlık dahil bileşik ifadeleri yakalar ("Remote Worldwide").
    if any(GLOBAL_KONUM.match(k) for k in konumlar) or GLOBAL_KALIP.search(baslik_alan):
        return "uzaktan (global)", "remote_global" in izinler

    # 3) Konum alanı EMEA/Avrupa diyorsa
    if EMEA_KALIP.search(baslik_alan):
        return "uzaktan (EMEA)", "remote_emea" in izinler

    # 4) Somut ülke tespit edilebiliyorsa ilan o ülkeye bağlıdır
    etiketler = {e for k in konumlar for e in _ulke_etiketleri(k)}
    if etiketler:
        uzak_mi = bool(job.remote_flag) or bool(UZAK_KALIP.search(baslik_alan))
        ek = "uzaktan, " if uzak_mi else ""
        # Türkçe ad: kartta "switzerland" değil "İsviçre" yazsın.
        ad = "/".join(sorted(ULKE_ADI.get(e, e) for e in etiketler))
        if etiketler & set(izinler):
            return f"{ek}{ad}", True
        # DİKKAT: Ülkeye ÇİVİLENMİŞ "remote" ilanı EMEA-açık SAYILMAZ.
        # "Forward Deployed Engineer - Germany (remote)" Alman çalışma izni ister;
        # Türkiye AB/BK'da olmadığı için başvurulamaz. İlk sürümde bu ilanlar
        # "uzaktan EMEA" diye kabul ediliyordu ve kısa listenin ~%70'i çöptü.
        # Tek istisna: ilan metni açıkça "anywhere in Europe/EMEA" diyorsa.
        if "remote_emea" in izinler and uzak_mi and EMEA_ACIK.search(metin[:4000]):
            return f"uzaktan EMEA-açık ({ad})", True
        return f"{ek}{ad} — izin yok", False

    # 5) Somut ülke yok: yalnızca konum alanı 'Remote/Anywhere' gibi genel ise
    #    ve metin global/EMEA doğruluyorsa kabul
    genel = any(GENEL_KONUM.match(k) for k in konumlar) or not konumlar
    uzak_mi = bool(job.remote_flag) or bool(UZAK_KALIP.search(baslik_alan))
    if genel and uzak_mi:
        if ABD_KILIT.search(metin):
            return "uzaktan ama ABD çalışma izni şartı", False
        if GLOBAL_KALIP.search(metin[:3000]):
            return "uzaktan (global, metinden)", "remote_global" in izinler
        if EMEA_KALIP.search(metin[:3000]):
            return "uzaktan (EMEA, metinden)", "remote_emea" in izinler
        return "uzaktan ama kapsam doğrulanamadı", False        # FAIL CLOSED
    if konumlar:
        return f"ofis: {', '.join(konumlar[:2])}", False
    return "konum belirtilmemiş", False


# Adı aynı zamanda sıradan bir İngilizce kelime olan teknolojiler.
# BÜYÜK-KÜÇÜK HARF DUYARLI aranır; yoksa "candidates who excel at..." cümlesi Excel
# yeteneği sayılır (ölçüldü: 1500 ilanın %62'sinde sahte eşleşme).
BELIRSIZ = {"Excel", "Go", "R", "C", "Rust", "Swift", "Julia", "Spark", "Scala",
            "Flask", "Django", "Access", "Word", "Shell", "Pascal", "Solid"}


def _yetenek_ara(metin: str, ad: str) -> bool:
    """Kelime sınırıyla arar: 'C' dili 'CI/CD' içinde eşleşmesin, 'Go' 'Google'da eşleşmesin."""
    bayrak = 0 if ad in BELIRSIZ else re.IGNORECASE
    if re.fullmatch(r"[A-Za-z+#]{1,3}", ad):        # C, Go, R, C++, C#
        return re.search(rf"(?<![\w+#]){re.escape(ad)}(?![\w+#])", metin, bayrak) is not None
    return re.search(rf"(?<!\w){re.escape(ad)}(?!\w)", metin, bayrak) is not None


def puanla(job: Job, profil: dict, idf: dict[str, float] | None = None) -> Puan:
    """idf: yetenek -> ayırt edicilik ağırlığı (havuzdan hesaplanır, bkz. pipeline.idf_hesapla).
    Verilmezse tüm yetenekler eşit sayılır (ilk koşum / tek ilan senaryosu)."""
    p = Puan()
    metin = job.text
    sert = profil.get("sert_filtreler", {})

    # ---------- 1) SERT FİLTRELER ----------
    for kalip in sert.get("yasakli_baslik_kaliplari", []):
        if (m := re.search(kalip, job.title)):
            # Kalıbın kendisi değil EŞLEŞEN SÖZCÜK yazılır. Eskiden kalıp ters bölü ile
            # bölünüyordu ve sonuç her zaman "(?i)" çıkıyordu — hiçbir bilgi taşımıyordu.
            p.elendi, p.eleme_sebebi = True, f"başlık yasaklı kalıba uyuyor ({m.group(0)[:40]})"
            return p

    p.kidem = _kidem_bul(job)
    max_k = sert.get("max_kidem", "mid")
    if KIDEM_SIRA.get(p.kidem, 1) > KIDEM_SIRA.get(max_k, 1):
        p.elendi, p.eleme_sebebi = True, f"kıdem fazla ({p.kidem} > {max_k})"
        return p

    p.istenen_yil = _istenen_yil(job)
    max_yil = sert.get("max_istenen_deneyim_yil")
    if p.istenen_yil and max_yil and p.istenen_yil > max_yil:
        p.elendi, p.eleme_sebebi = True, f"{p.istenen_yil} yıl deneyim istiyor (sınır {max_yil})"
        return p

    p.konum_durumu, konum_ok = _konum_degerlendir(job, sert.get("zorunlu_konum_kosulu", []))
    if not konum_ok:
        p.elendi, p.eleme_sebebi = True, f"konum/çalışma izni uymuyor → {p.konum_durumu}"
        return p

    if sert.get("sponsorluk_gerektiren_ele") and SPONSOR_YOK.search(job.description):
        p.elendi, p.eleme_sebebi = True, "ilan açıkça vize sponsorluğu vermiyor"
        return p

    # Yabancı dil şartı (TR/EN dışı). Tespit ediliyordu ama elenmiyordu:
    # "Solutions Architect - Italian Speaker" kısa listeye giriyordu.
    diller = [d.lower() for d in sert.get("bildigim_diller", ["english", "turkish"])]
    m_dil = DIL_SARTI.search(job.title + " " + job.description[:4000])
    if m_dil and m_dil.group(1).lower() not in diller:
        p.elendi, p.eleme_sebebi = True, f"ana dil şartı: {m_dil.group(1)}"
        return p

    # ---------- 2) ROL AİLESİ (ağırlık 40 puan) ----------
    en_iyi, en_iyi_ad = 0.0, ""
    for ad, tanim in (profil.get("rol_aileleri") or {}).items():
        for kalip in tanim.get("basliklar", []):
            if re.search(kalip, job.title):
                if tanim.get("agirlik", 0) > en_iyi:
                    en_iyi, en_iyi_ad = tanim["agirlik"], ad
                break
        else:  # başlıkta yoksa departman/metinde ara (yarı puan)
            for kalip in tanim.get("basliklar", []):
                if re.search(kalip, job.department + " " + job.description[:900]):
                    if tanim.get("agirlik", 0) * 0.5 > en_iyi:
                        en_iyi, en_iyi_ad = tanim["agirlik"] * 0.5, ad + " (dolaylı)"
                    break
    p.rol_ailesi, p.rol_puan = en_iyi_ad or "eşleşmedi", en_iyi * 40

    # ---------- 3) YETENEK ÖRTÜŞMESİ (ağırlık 45 puan) ----------
    yet = profil.get("yetenekler", {})
    guclu, zayif = yet.get("guclu", {}) or {}, yet.get("zayif", {}) or {}
    toplanan = 0.0
    bilgilendirici = 0          # havuzda seyrek geçen, yani gerçekten ayırt edici eşleşme
    for ad, w in guclu.items():
        if _yetenek_ara(metin, ad):
            a = idf.get(ad, 1.0) if idf else 1.0
            toplanan += w * a
            if a >= 1.5:
                bilgilendirici += 1
            p.eslesen_yetenekler.append(ad)
    for ad, w in zayif.items():
        if not _yetenek_ara(metin, ad):
            continue
        toplanan += w * (idf.get(ad, 1.0) if idf else 1.0)
        p.eslesen_yetenekler.append(f"{ad}(zayıf)")
        # İlan bunu VURGULU yerde istiyorsa (başlık ya da metnin ilk bölümü) kullanıcı
        # bilsin: ilan bu yeteneği öne çıkarıyor ama CV'de zayıf.
        # ESKİDEN: bu kontrol `elif` idi, yani yalnız metinde HİÇ geçmeyen yetenekler
        # için bakılıyordu — mantıken imkânsız bir dal, kutu hep boştu.
        if _yetenek_ara(job.title + " " + job.description[:1200], ad):
            p.eksik_yetenekler.append(ad)
    p.bilgilendirici_eslesme = bilgilendirici
    # normalize: ~8 birim ağırlıklı örtüşme tam puan sayılır
    p.yetenek_puan = min(toplanan / 8.0, 1.0) * 45

    # ---------- 4) TERCİH BONUSLARI (15 puan) ----------
    terc = profil.get("tercihler", {})
    bonus = 0.0
    if "uzaktan" in p.konum_durumu:
        b = terc.get("uzaktan_oncelik", 0.0)
        bonus += b
        p.bonuslar.append(f"uzaktan (+{b:.2f})")
    for kalip, b in (terc.get("sektor_bonus") or {}).items():
        if re.search(kalip, metin[:4000]):
            bonus += b
            p.bonuslar.append(f"sektör (+{b:.2f})")
            break
    p.toplam = round(p.rol_puan + p.yetenek_puan + min(bonus, 1.0) * 15, 1)

    # ALAKA KAPISI — bu olmadan puanlama her şeyi geçiriyordu (ölçüldü: profil başına
    # ~400 "aday"). İki koşuldan biri sağlanmalı:
    #   (a) başlık gerçekten rol ailesine uyuyor (dolaylı/metin eşleşmesi saymaz), veya
    #   (b) en az 2 ayırt edici (havuzda seyrek) yetenek örtüşüyor.
    baslik_eslesti = bool(en_iyi_ad) and "dolaylı" not in en_iyi_ad

    # ALAN SAHİPLİĞİ: başlık, adayda olmayan bir alanın işaretini taşıyorsa ilan
    # o adaya ait değildir — geniş bir kalıba tesadüfen uymuş demektir.
    catisma = _alan_catismasi(job.title, set(profil.get("rol_aileleri") or {}))
    if catisma and not profil.get("alan_disi_goster"):
        p.elendi = True
        p.eleme_sebebi = f"başka alanın ilanı ({catisma})"
        return p

    # ALAN DIŞI EŞLEŞME: ilan başlığı adayın rol ailelerinden hiçbirine uymuyor ama
    # yetenekler örtüşüyor. Bunlar tamamen atılmaz (komşu alan gerçekten ilgi çekici
    # olabilir) ama ALAN İÇİ eşleşmelerin ALTINA sıralanır ve açıkça etiketlenir.
    # Ölçüldü: havuzda iOS ilanı yokken bir iOS geliştiricisine 1. sırada
    # "Ubuntu Linux Kernel Test Engineer" gösteriliyordu, uyarı olmadan.
    if not baslik_eslesti:
        p.toplam = round(p.toplam * 0.55, 1)
        p.alan_disi = True
        p.uyarilar.append("alan dışı: ilan başlığı aradığın rol ailelerine uymuyor, "
                          "yalnızca yetenek örtüşmesiyle geldi")
        # VARSAYILAN: alan dışı ilan GÖSTERİLMEZ. Kesinlik, kapsamdan önce gelir —
        # 10 ilan çıkıp hepsi uygun olması, 40 ilan çıkıp yarısı alakasız olmasından
        # iyidir. (Ölçüldü: ceza uygulansa bile alan içi sonuç azken alan dışı ilanlar
        # ilk 10'a sızıyordu; 15 CV'de toplam 66 sızıntı.)
        # Profilde `alan_disi_goster: true` denirse gösterilir.
        if not profil.get("alan_disi_goster"):
            p.elendi = True
            p.eleme_sebebi = "alan dışı (başlık rol ailelerine uymuyor)"
            return p

    if not baslik_eslesti and p.bilgilendirici_eslesme < 2:
        p.elendi = True
        p.eleme_sebebi = ("rol başlıkta eşleşmedi ve ayırt edici yetenek örtüşmesi yetersiz "
                          f"({p.bilgilendirici_eslesme} ayırt edici eşleşme)")
        return p

    # ---------- 5) UYARILAR (elemez, bilgilendirir) ----------
    if p.eksik_yetenekler:
        p.uyarilar.append("ilanın istediği ama CV'de zayıf: " + ", ".join(p.eksik_yetenekler[:5]))
    if re.search(r"(?i)\b(fluent|native|c1|c2)\b[^.]{0,30}\b(english|ingilizce)\b", job.description):
        p.uyarilar.append("ileri seviye İngilizce şartı geçiyor")
    if not p.eslesen_yetenekler:
        p.uyarilar.append("CV'den hiçbir teknik yetenek eşleşmedi — büyük ihtimalle alakasız")
    return p
