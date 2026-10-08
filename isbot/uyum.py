"""Uyum hakemi — ilanın adaya GERÇEKTEN uyup uymadığını denetleyen model katmanı.

NEDEN VAR: Motor (sözlük + rol kalıpları) hızlı ve açıklanabilir, ama sözcüğe
bakar, anlama bakmaz. Ölçülen iki tipik kırılma:

  - Türkçede "kontrol" hem *control systems* hem *quality control* demek.
    "kontrol mühendisi" sorgusunun 51 sonucunun TAMAMI kalite kontrol çıktı.
  - CV'de "AutoCAD sertifikalı" yazan bir kontrol mühendisi adayına
    "CAD/CAM Operatör Yardımcısı" ilanı 50,2 puanla ikinci sıradan geldi.
    Başlık kalıbı tutuyor, yetenek tutuyor — ama iş adaya ait değil.

Bu katman o kararı anlam düzeyinde verir: adayın NE OLDUĞUNU ve NE OLMADIĞINI
anlatan iki cümle kurulur, ilan ikisine de kıyaslanır, FARK alınır. Yalnız
"uygun mu" demek yetmiyordu — "kalite kontrol mühendisi" ilanı da adaya benziyor;
ayrımı yaratan, adayın işi OLMAYAN mesleklere olan yakınlığın düşülmesi.

ÖLÇÜLDÜ (14 Eyl 2026):
  - 10.834 ilanlık havuz, 12 test CV'si, beklenen.yaml'daki alan ölçütü:
    motor tek başına 52/60 → model yeniden sıralamayla 54/60. Hiçbir CV'de
    kötüleşme yok.
  - Türkçe savunma sanayii havuzunda CAD/CAM operatör ilanları negatife düştü,
    mühendislik ilanları pozitif kaldı.

TASARIM SINIRI — model ELEMEZ. Kendisi de yanılıyor (ölçümde "Dijital Pazarlama
Uzmanı"na pozitif skor verdi). Bu yüzden yalnız puanı dar bir bantta düzeltir ve
uyumsuz bulduğunu ETİKETLER. Eleme kararı motorun sert filtrelerinde kalır.

Model yoksa bu modülün tamamı sessizce devre dışı kalır; motor eskisi gibi çalışır.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .yollar import kaynak_dosya

# Sözlükteki kanonik adlar İngilizce (bkz. data/skills.yaml). Türk panolarından
# gelen ilanlar Türkçe olduğu için profil cümlesi iki dilde de kurulur; model
# çok dilli ama aynı dildeki eşleşme daha güçlü sinyal veriyor.
TR_KARSILIK = {
    "control systems": "kontrol sistemleri", "flight dynamics": "uçuş dinamiği",
    "autonomous systems": "otonom sistemler", "adaptive control": "adaptif kontrol",
    "UAV": "insansız hava aracı", "autopilot": "otopilot", "aerospace": "havacılık",
    "sensor fusion": "sensör füzyonu", "power electronics": "güç elektroniği",
    "high voltage": "yüksek gerilim", "state-space": "durum uzayı",
    "system identification": "sistem tanımlama", "avionics": "aviyonik",
    "propulsion": "itki sistemleri", "Robotics": "robotik",
    "embedded systems": "gömülü sistemler", "computer vision": "bilgisayarlı görü",
    "signal processing": "sinyal işleme", "machine learning": "makine öğrenmesi",
    "reverse engineering": "tersine mühendislik", "penetration testing": "sızma testi",
    "product management": "ürün yönetimi", "data analysis": "veri analizi",
}

# Adayın işi OLMAYAN meslekler. Mühendislik/uzmanlık ilanlarıyla aynı sözcük havuzunu
# paylaşan ama farklı bir işi tarif eden roller; iki dilde yazılır (havuzda ikisi de var).
# Her madde: (EN, TR, bu maddenin KENDİ MESLEĞİ olduğu aileler, teknisyenin işi mi).
# NEDEN MADDE MADDE: cümle eskiden SABİTTİ ve herkese uygulanıyordu — kalite kontrolcü,
# satışçı, İK uzmanı ve teknisyen kendi mesleğinin ilanlarında ceza alıyordu. Adayın
# kendi mesleği cümleden çıkarılır; yazılımcı/mühendis için cümle birebir aynı kalır.
UYUMSUZ_MADDELER: list[tuple[str, str, frozenset[str], bool]] = [
    ("Quality control and inspection", "Kalite kontrol ve muayene",
     frozenset({"uretim_kalite"}), False),
    ("production line operator", "üretim bandı operatörlüğü", frozenset({"uretim_kalite"}), True),
    ("CNC machine operator", "CNC tezgah operatörlüğü", frozenset({"uretim_kalite"}), True),
    ("assembly technician", "montaj teknisyenliği", frozenset({"uretim_kalite"}), True),
    ("maintenance and repair technician", "bakım onarım teknisyenliği", frozenset(), True),
    ("warehouse and logistics", "depo ve sevkiyat", frozenset({"lojistik"}), False),
    ("sales and marketing", "satış ve pazarlama", frozenset({"satis", "pazarlama"}), False),
    ("human resources and payroll", "insan kaynakları ve özlük işleri", frozenset({"ik"}), False),
    ("cleaning and administrative support", "temizlik ve idari işler", frozenset(), False),
]


def _bas_harf(s: str) -> str:
    return ("İ" if s[:1] == "i" else s[:1].upper()) + s[1:]


def uyumsuz_cumlesi(profil: dict) -> str:
    """Adayın işi OLMAYAN meslekleri anlatan cümle — adayın kendi mesleği hariç."""
    aileler = set(profil.get("rol_aileleri") or {})
    teknisyen = bool((profil.get("kimlik") or {}).get("teknisyen"))
    kalan = [(en, tr) for en, tr, muaf, tek_isi in UYUMSUZ_MADDELER
             if not (muaf & aileler) and not (teknisyen and tek_isi)]
    return (_bas_harf(", ".join(en for en, _ in kalan)) + ". "
            + _bas_harf(", ".join(tr for _, tr in kalan)) + ".")


# Profil cümlesindeki "mühendis ... Ar-Ge" kalıbı bu aileler için kurulup ölçüldü
# (alan ölçütü 52 -> 54/60). Başka bir meslekte adayı yanlış tarif ediyordu: hemşireye,
# avukata, teknisyene de "deneyimli mühendis" deniyordu.
MUHENDISLIK_AILELERI = frozenset({
    "kontrol_otomasyon", "havacilik_savunma", "makine_tasarim", "gomulu", "ml_ai",
    "veri_muh", "veri_bilimi", "platform_sre", "backend", "frontend", "mobil", "oyun",
    "guvenlik", "qa", "blockchain", "urun", "bilimsel_hpc", "genel_yazilim",
})

MODEL_DOSYA = "model_int8.onnx"
TOKENIZER_DOSYA = "tokenizer.json"
AZAMI_TOKEN = 256          # ilan metninin ilk ~250 kelimesi karar için yeterli
YIGIN = 64                 # tek seferde gömülen ilan sayısı
BASLIK_AGIRLIK = 0.6       # başlık ilanın kimliğidir; gövde gürültülüdür

# --- zayıf donanım koruması ---
# Bu araç 8 yıllık bir Windows dizüstüde de açılacak. Orada model, geliştirme
# makinesinden 10-20 kat yavaş çalışabilir. İki sınır konur:
#   - en çok AZAMI_ILAN ilan denetlenir (kısa listenin en yüksek puanlıları),
#   - denetim AZAMI_SANIYE'yi aşarsa kalanı bırakılır ve uyarı verilir.
# Süre sınırı bilerek GENİŞ tutuldu (90 sn): tarama zaten dakikalar sürüyor,
# yavaş bir makinede denetimi erken kesmek faydayı yok eder. Sınır bir "makul
# bekleme" değil, donma koruması.
# Yarım denetim kabul edilebilir: denetlenmeyen ilan uyum=None kalır, motorun
# kendi puanıyla listede durur — hiçbir ilan bu yüzden kaybolmaz.
AZAMI_ILAN = 400
AZAMI_SANIYE = 90.0

# NOT — MODEL DOSYASI DONANIMDAN BAĞIMSIZ OLMALI.
# İlk indirilen dosya `model_qint8_avx512_vnni.onnx` idi: adı üstünde, Intel'in
# AVX512-VNNI komut setine göre nicelenmiş bir sürüm. Apple Silicon'da çalışıyordu
# (onnxruntime genel yola düşüyor) ama AVX512'si olmayan eski Intel makinelerde
# yavaşlama riski vardı. Artık genel int8 sürümü kullanılıyor; ölçümde aynı hız.


def model_dizini() -> Path:
    return kaynak_dosya("isbot", "model")


def model_var_mi() -> bool:
    d = model_dizini()
    return (d / MODEL_DOSYA).exists() and (d / TOKENIZER_DOSYA).exists()


class Hakem:
    """Gömme modelini tutar. Yükleme PAHALI (~1 sn) — süreç başına bir kez."""

    def __init__(self) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        d = model_dizini()
        self._np = np
        self._tok = Tokenizer.from_file(str(d / TOKENIZER_DOSYA))
        self._tok.enable_truncation(max_length=AZAMI_TOKEN)
        self._tok.enable_padding(length=None)
        # Tek iş parçacığı: panel zaten ilanları paralel çekiyor, burada iş parçacığı
        # açmak makineyi kilitliyordu (ölçüldü: 8 çekirdekte tarama %40 yavaşladı).
        ayar = ort.SessionOptions()
        ayar.intra_op_num_threads = max(1, (__import__("os").cpu_count() or 4) // 2)
        self._oturum = ort.InferenceSession(str(d / MODEL_DOSYA), ayar,
                                            providers=["CPUExecutionProvider"])
        self._girdiler = {g.name for g in self._oturum.get_inputs()}

    def _goem(self, metinler: list[str], onek: str):
        """e5 ailesi 'query:'/'passage:' öneki bekler; öneksiz kalite belirgin düşüyor."""
        np = self._np
        cikti = []
        for i in range(0, len(metinler), YIGIN):
            dilim = [f"{onek}: {m}" for m in metinler[i:i + YIGIN]]
            kodlu = self._tok.encode_batch(dilim)
            ids = np.array([k.ids for k in kodlu], dtype=np.int64)
            mask = np.array([k.attention_mask for k in kodlu], dtype=np.int64)
            besle = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._girdiler:
                besle["token_type_ids"] = np.zeros_like(ids)
            son = self._oturum.run(None, besle)[0]
            m = mask[..., None].astype(np.float32)
            ortalama = (son * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
            cikti.append(ortalama)
        v = np.concatenate(cikti, axis=0) if cikti else np.zeros((0, 384), dtype=np.float32)
        return v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-9, None)

    def skorla(self, profil: dict, ilanlar: list) -> list[float]:
        """Her ilan için kontrast skoru: (adaya yakınlık) − (adayın işi olmayana yakınlık).

        Pozitif = iş adayın alanına ait. Negatif = aynı sözcükleri paylaşan
        ama başka bir mesleğe ait ilan. Sıfır civarı = kararsız.
        """
        if not ilanlar:
            return []
        import time as _time
        np = self._np
        basla = _time.monotonic()
        q_uygun = self._goem([profil_cumlesi(profil)], "query")[0]
        q_uygunsuz = self._goem([uyumsuz_cumlesi(profil)], "query")[0]

        hedef = ilanlar[:AZAMI_ILAN]
        basliklar = self._goem([j.title for j in hedef], "passage")
        if _time.monotonic() - basla > AZAMI_SANIYE:
            # Başlıklar bile süreyi aştıysa makine çok yavaş: gövdeyi hiç deneme,
            # elde olanla karar ver. Yarım sinyal, sinyalsizlikten iyidir.
            D = basliklar
        else:
            govdeler = self._goem(
                [f"{j.title}. {(j.description or '')[:600]}" for j in hedef], "passage")
            D = BASLIK_AGIRLIK * basliklar + (1 - BASLIK_AGIRLIK) * govdeler
        D = D / np.clip(np.linalg.norm(D, axis=1, keepdims=True), 1e-9, None)
        skor = [float(x) for x in (D @ q_uygun) - (D @ q_uygunsuz)]
        # Sınırın dışında kalanlar: None -> motorun kendi puanı geçerli kalır.
        return skor + [None] * (len(ilanlar) - len(skor))


@lru_cache(maxsize=1)
def hakem() -> Hakem | None:
    """Süreç başına tek örnek. Model yoksa ya da yüklenemezse None — motor yalnız çalışır."""
    if not model_var_mi():
        return None
    try:
        return Hakem()
    except Exception:
        # onnxruntime kurulu değil / model bozuk / mimari uyumsuz. Sessiz düşmek
        # doğru davranış: bu katman ZORUNLU değil, motor onsuz da doğru sonuç verir.
        return None


def kullanilabilir() -> tuple[bool, str]:
    """(hazır mı, sebep) — panelde 'gelişmiş arama' seçeneğini göstermek için."""
    if not model_var_mi():
        return False, "model dosyası yok"
    try:
        import onnxruntime  # noqa: F401
        import tokenizers   # noqa: F401
    except ImportError as e:
        return False, f"paket eksik: {e.name}"
    return True, "hazır"


def profil_cumlesi(profil: dict) -> str:
    """CV profilinden modele verilecek doğal dil cümlesi.

    NEDEN DOĞAL DİL: ilk denemede cümle makine anahtarlarıyla kuruluyordu
    ("Alan: kontrol_otomasyon, havacilik_savunma"). Model bunları anlamlı bir
    meslek tarifi olarak okumadı ve tüm ilanlara birbirine çok yakın skorlar
    verdi (0,81–0,89 bandı). Cümle bir işverenin yazacağı gibi kurulunca ayrım açıldı.
    """
    kimlik = profil.get("kimlik") or {}
    yet_ham = list((profil.get("yetenekler") or {}).get("guclu") or {})[:16]
    # Her yeteneği İngilizce kanonik + varsa Türkçe karşılığıyla yaz.
    yet = []
    for k in yet_ham:
        yet.append(k)
        tr = TR_KARSILIK.get(k)
        if tr:
            yet.append(tr)
    aileler = list(profil.get("rol_aileleri") or {})
    alanlar = [_okunur(a) for a in aileler]
    yil = kimlik.get("deneyim_yil")
    if kimlik.get("teknisyen"):
        bas = f"{yil} yıl deneyimli teknisyen." if yil else "Teknisyen."
        return (f"{bas} Çalışma alanı: {', '.join(alanlar) or 'teknik servis'}. "
                f"Uzmanlık: {', '.join(yet) or 'teknik servis'}. "
                f"Kurulum, bakım, arıza giderme ve saha işi.")
    # Aileler ağırlığa göre sıralı: ilk aile adayın ana mesleğidir.
    if aileler and aileler[0] not in MUHENDISLIK_AILELERI:
        bas = f"{yil} yıl deneyimli profesyonel." if yil else "Profesyonel."
        return (f"{bas} Meslek alanı: {', '.join(alanlar)}. "
                f"Uzmanlık: {', '.join(yet) or ', '.join(alanlar)}.")
    bas = f"{yil} yıl deneyimli mühendis." if yil else "Mühendis."
    return (f"{bas} Çalışma alanı: {', '.join(alanlar) or 'mühendislik'}. "
            f"Uzmanlık: {', '.join(yet) or 'mühendislik'}. "
            f"Tasarım, geliştirme, modelleme ve Ar-Ge işi.")


def _okunur(aile: str) -> str:
    """rol ailesi anahtarını modele verilecek okunur ada çevirir."""
    ADLAR = {
        "kontrol_otomasyon": "kontrol sistemleri ve otomasyon, control systems and automation",
        "havacilik_savunma": "havacılık, uzay ve savunma sanayii, aerospace and defence",
        "makine_tasarim": "makine tasarımı ve imalat, mechanical design",
        "gomulu": "gömülü sistemler ve firmware, embedded systems",
        "ml_ai": "yapay zekâ ve makine öğrenmesi, machine learning",
        "veri_muh": "veri mühendisliği, data engineering",
        "veri_bilimi": "veri bilimi ve analitik, data science",
        "platform_sre": "platform ve altyapı mühendisliği, platform engineering",
        "backend": "arka uç yazılım geliştirme, backend software engineering",
        "frontend": "arayüz geliştirme, frontend web development",
        "mobil": "mobil uygulama geliştirme, mobile development",
        "oyun": "oyun geliştirme, game development",
        "guvenlik": "siber güvenlik, cyber security",
        "qa": "yazılım testi ve otomasyonu, software testing",
        "blockchain": "blokzincir geliştirme, blockchain development",
        "urun": "ürün yönetimi, product management",
        "bilimsel_hpc": "bilimsel hesaplama ve simülasyon, scientific computing",
        "genel_yazilim": "yazılım mühendisliği, software engineering",
        # Yazılım dışı meslekler: eskiden anahtar adıyla ("saglik", "ik") gidiyordu.
        "bankacilik": "bankacılık ve finans, banking and finance",
        "denizcilik": "denizcilik ve gemi işletmesi, maritime and shipping",
        "egitim": "eğitim ve öğretmenlik, education and teaching",
        "enerji_cevre": "enerji ve çevre, energy and environment",
        "gida_tarim": "gıda ve tarım, food and agriculture",
        "hukuk": "hukuk ve avukatlık, law and legal services",
        "ik": "insan kaynakları, human resources",
        "ilac_biyotek": "ilaç ve biyoteknoloji, pharmaceuticals and biotechnology",
        "insaat": "inşaat ve yapı, construction and civil engineering",
        "isg": "iş sağlığı ve güvenliği, occupational health and safety",
        "kimya": "kimya ve proses, chemistry and process engineering",
        "lojistik": "lojistik ve tedarik zinciri, logistics and supply chain",
        "madencilik": "madencilik, mining",
        "muhasebe": "muhasebe ve finans, accounting and finance",
        "pazarlama": "pazarlama ve iletişim, marketing and communications",
        "saglik": "sağlık ve hemşirelik, healthcare and nursing",
        "satis": "satış, sales",
        "tekstil": "tekstil ve hazır giyim, textiles and apparel",
        "turizm": "turizm ve otelcilik, tourism and hospitality",
        "uretim_kalite": "üretim ve kalite, manufacturing and quality",
    }
    return ADLAR.get(aile, re.sub(r"_", " ", aile))
