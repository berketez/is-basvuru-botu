"""Lokal web paneli.

Tasarım kararı — NEDEN LOKAL, BARINDIRILAN DEĞİL:
CV ve başvuru geçmişi kişisel veridir. Sunucuda tutmak KVKK/GDPR yükümlülüğü, depolama
ve fatura demektir. Lokal çalıştırınca CV makineden hiç çıkmaz, maliyet sıfırdır.
Kullanıcı `.app`/`.exe` dosyasına çift tıklar; sunucu 127.0.0.1'de kalkar, tarayıcı
kendiliğinden açılır. Terminal görmez, Python kurmaz.

Sunucu YALNIZCA 127.0.0.1'e bağlanır — ağdaki başka makineler erişemez.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import yaml
from flask import Flask, jsonify, request, send_from_directory

from .cv_import import profil_tazele, profil_uret, yaz as profil_yaz
from .yollar import ilk_kurulum, kaynak_dosya, oz_denetim, veri_dosya, veri_kok

ilk_kurulum()
_EKSIK = oz_denetim()          # pakete girmemiş veri dosyası varsa arayüzde söylenir
KOK = kaynak_dosya("isbot", "web")
VARSAYILAN_PROFIL = veri_dosya("config", "profile.local.yaml")
SONUC_JSON = veri_dosya("out", "sonuclar.json")
SIRKETLER = veri_dosya("config", "companies.yaml")

app = Flask(__name__, static_folder=None)

# Tarama durumu (tek kullanıcılı lokal uygulama; basit modül durumu yeterli)
_durum: dict = {"calisiyor": False, "asama": "", "cekilen": 0, "sirket": "",
                "bitti": False, "hata": None, "baslangic": None}

# HER AÇILIŞ TEMİZ BAŞLAR: uygulama açıldığında panel boş gelir; kullanıcı CV'yi
# yükleyip "Tara"ya basana kadar ne profil ne de eski sonuç gösterilir.
# NEDEN: Önceki koşumun sonuçlarını açılışta göstermek onları GÜNCEL sanmaya yol
# açıyor. İlan listesi çabuk bayatlar; bayat listeyi taze gibi sunmak yanıltıcıdır.
# Dosyalar diskte DURUR (hiçbir şey silinmez), yalnızca bu oturumda gösterilmez.
_oturum_hazir = False
_kilit = threading.Lock()


# ----------------------------- sayfa -----------------------------
@app.get("/")
def sayfa():
    return send_from_directory(KOK, "index.html")


@app.get("/favicon.ico")
def favicon():
    # Gömülü tek renkli SVG: dış istek yok, konsolda 404 gürültüsü kalmaz.
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
           '<rect width="32" height="32" rx="7" fill="#4c9aff"/>'
           '<text x="16" y="23" font-size="19" font-family="sans-serif" '
           'text-anchor="middle" fill="#fff">İ</text></svg>')
    return app.response_class(svg, mimetype="image/svg+xml")


@app.get("/<path:dosya>")
def statik(dosya: str):
    if (KOK / dosya).is_file():
        return send_from_directory(KOK, dosya)
    return ("bulunamadı", 404)


# ----------------------------- profil -----------------------------
@app.get("/api/saglik")
def saglik():
    """Paket bütünlüğü. Eksik veri dosyası sessizce arızaya yol açmasın."""
    # "uygulama" alanı künyedir: ikinci çift tıklamada bu portta koşanın biz mi
    # yoksa alakasız başka bir program mı olduğu buradan anlaşılır.
    return jsonify({"uygulama": "isbasvurubotu",
                    "saglikli": not _EKSIK, "eksik_dosyalar": _EKSIK})


@app.get("/api/profil")
def profil_oku():
    if not VARSAYILAN_PROFIL.exists():
        return jsonify({"var": False})
    p = yaml.safe_load(VARSAYILAN_PROFIL.read_text(encoding="utf-8")) or {}
    if not _oturum_hazir:
        # Oturum yeni: profil gösterilmez ama kullanıcının ÖNCEKİ konum tercihleri
        # döndürülür ki CV yüklenince kutular hazır işaretli gelsin.
        return jsonify({"var": False, "onceki_konum": (p.get("sert_filtreler") or {})
                        .get("zorunlu_konum_kosulu", [])})
    return jsonify({
        "var": True,
        "deneyim_yil": (p.get("kimlik") or {}).get("deneyim_yil"),
        "calisma_izni": (p.get("kimlik") or {}).get("calisma_izni", []),
        "max_kidem": (p.get("sert_filtreler") or {}).get("max_kidem"),
        "konum_kosulu": (p.get("sert_filtreler") or {}).get("zorunlu_konum_kosulu", []),
        "guclu_yetenek": list((p.get("yetenekler") or {}).get("guclu") or {}),
        "sorgular": p.get("arama_sorgulari", []),
        "not": p.get("_NOT"),
    })


@app.post("/api/cv")
def cv_yukle():
    """CV dosyasını alır, profil taslağı üretir. Dosya diske geçici olarak yazılır,
    işlenir, sonra silinir — CV içeriği makinede kalır, hiçbir yere gönderilmez."""
    f = request.files.get("cv")
    if not f or not f.filename:
        return jsonify({"hata": "dosya gelmedi"}), 400
    uzanti = Path(f.filename).suffix.lower()
    if uzanti not in (".pdf", ".tex", ".docx", ".md", ".txt"):
        return jsonify({"hata": f"desteklenmeyen tür: {uzanti or '?'} "
                                "(PDF, TeX, DOCX, MD, TXT)"}), 400
    gecici = veri_dosya("out", f"cv_gecici{uzanti}")
    gecici.parent.mkdir(parents=True, exist_ok=True)
    f.save(gecici)
    try:
        p = profil_uret(gecici)
        profil_yaz(p, VARSAYILAN_PROFIL)
    except Exception as e:
        return jsonify({"hata": f"{type(e).__name__}: {e}"}), 400
    finally:
        gecici.unlink(missing_ok=True)
    global _oturum_hazir
    _oturum_hazir = True          # CV yüklendi: oturum artık hazır
    return jsonify({
        "tamam": True,
        "deneyim_yil": p["kimlik"]["deneyim_yil"],
        "deneyim_kaynagi": p["kimlik"]["_deneyim_kaynagi"],
        "max_kidem": p["sert_filtreler"]["max_kidem"],
        "guclu_yetenek": list(p["yetenekler"]["guclu"]),
        "gozden_gecir": p["kimlik"]["calisma_izni"] == ["GÖZDEN GEÇİR"],
    })


@app.get("/api/ulkeler")
def ulke_listesi():
    """Arayüzdeki ülke seçici bunu okur.

    NEDEN UÇ VAR: Arayüzde ABD/BK/Almanya diye ÜÇ sabit kutu vardı; motor ise
    onlarca ülkeyi tanıyordu. İsviçre'de çalışma izni olan kullanıcı bunu
    işaretleyemediği için o ilanlar eleniyordu. Liste artık motordan gelir —
    ülke eklemek için yalnızca scoring.ULKELER düzenlenir, arayüz kendiliğinden
    günceldir. Türkiye listede yok: yukarıda kendi kutusu var.
    """
    from .scoring import BOLGE_ADI, ULKELER
    return jsonify([{"etiket": e, "ad": ad, "bolge": BOLGE_ADI.get(b, b),
                     "arama": " ".join((ad.lower(), e, *takma))}
                    for e, ad, b, takma in ULKELER if e != "turkey"])


@app.post("/api/profil/konum")
def konum_kaydet():
    """Kullanıcı arayüzden çalışma izni/konum koşulunu düzeltir.
    cv-import bunu CV'den güvenilir çıkaramaz, o yüzden elle onay şart."""
    from .scoring import ULKE_ADI
    veri = request.get_json(silent=True) or {}
    izinler = [x for x in (veri.get("izinler") or []) if isinstance(x, str)]
    # Motorun tanımadığı etiket profile yazılmaz: sessizce hiçbir ilana uymayan
    # bir koşul, kullanıcıya "seçtim ama hiç sonuç gelmiyor" diye geri döner.
    gecerli = {"remote_global", "remote_emea"} | set(ULKE_ADI)
    izinler = [x for x in dict.fromkeys(izinler) if x in gecerli]
    if not izinler:
        return jsonify({"hata": "en az bir konum koşulu seç"}), 400
    p = yaml.safe_load(VARSAYILAN_PROFIL.read_text(encoding="utf-8")) or {}
    p.setdefault("kimlik", {})["calisma_izni"] = izinler
    p.setdefault("sert_filtreler", {})["zorunlu_konum_kosulu"] = izinler
    VARSAYILAN_PROFIL.write_text(
        yaml.safe_dump(p, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
    return jsonify({"tamam": True, "izinler": izinler})


# ----------------------------- tarama -----------------------------
def _tara_arkaplan(min_puan: float):
    from .pipeline import json_yaz, tara
    try:
        # Motor güncellendiyse profilin türetilen kısımlarını tazele.
        # Yoksa yeni eleme kalıpları mevcut kullanıcıya hiç ulaşmaz.
        # Hata SESSİZCE yutulmamalı: ilk sürümde try/except:pass vardı ve tazeleme
        # hiç çalışmadığı halde kimse fark etmedi. Hata artık duruma yazılır.
        try:
            pr = yaml.safe_load(VARSAYILAN_PROFIL.read_text(encoding="utf-8")) or {}
            eski_surum = pr.get("_motor_surumu")
            pr, degisen = profil_tazele(pr)
            # İçerik değişmese bile sürüm damgası diske yazılmalı; yoksa tazeleme
            # her taramada boşuna tekrar koşar ve dosya hep "eski" görünür.
            if degisen or pr.get("_motor_surumu") != eski_surum:
                profil_yaz(pr, VARSAYILAN_PROFIL)
            with _kilit:
                _durum["tazelendi"] = ", ".join(degisen) if degisen else "gerek yok"
        except Exception as e:
            with _kilit:
                _durum["tazelendi"] = f"HATA {type(e).__name__}: {e}"
        def ilerle(ad, n):
            with _kilit:
                _durum["sirket"] = ad
                _durum["cekilen"] += n

        def asama_bildir(ad):
            with _kilit:
                _durum["asama"] = ad
        with _kilit:
            _durum.update(calisiyor=True, bitti=False, hata=None, cekilen=0,
                          asama="ilanlar çekiliyor", baslangic=time.time())
        r = tara(str(VARSAYILAN_PROFIL), str(SIRKETLER),
                 str(veri_dosya("data", "jobs.db")), min_puan=min_puan, ilerleme=ilerle,
                 asama_bildir=asama_bildir)
        json_yaz(r, str(SONUC_JSON))
        with _kilit:
            _durum.update(calisiyor=False, bitti=True, asama="tamamlandı",
                          cekilen=r.cekilen)
    except Exception as e:
        with _kilit:
            _durum.update(calisiyor=False, bitti=True, hata=f"{type(e).__name__}: {e}")


@app.post("/api/tara")
def tarama_baslat():
    with _kilit:
        if _durum["calisiyor"]:
            return jsonify({"hata": "tarama sürüyor"}), 409
    if not VARSAYILAN_PROFIL.exists():
        return jsonify({"hata": "önce CV yükle"}), 400
    threading.Thread(target=_tara_arkaplan, args=(0.0,), daemon=True).start()
    return jsonify({"basladi": True})


@app.get("/api/tara/durum")
def tarama_durum():
    with _kilit:
        d = dict(_durum)
    if d.get("baslangic"):
        d["gecen_sn"] = round(time.time() - d["baslangic"])
    return jsonify(d)


# ----------------------------- sonuçlar -----------------------------
@app.get("/api/sonuclar")
def sonuclar():
    if not _oturum_hazir:
        return jsonify({"ilanlar": [], "bos": True, "oturum_yeni": True})
    if not SONUC_JSON.exists():
        return jsonify({"ilanlar": [], "bos": True})
    return app.response_class(SONUC_JSON.read_text(encoding="utf-8"),
                              mimetype="application/json")


def tarayicida_ac(adres: str) -> bool:
    """Paneli varsayılan tarayıcıda açar.

    NEDEN webbrowser DEĞİL: macOS'ta webbrowser.open() osascript'e Apple Event
    yollar. Masaüstünden (LaunchServices) açılan imzasız bir .app'in Apple Event
    izni yoktur -- Info.plist'te NSAppleEventsUsageDescription de yok -- istek
    sessizce düşer, tarayıcı AÇILMAZ. Terminalden çalışınca izin Terminal'e ait
    olduğu için sorun görünmez; tam da bu yüzden gözden kaçtı.
    /usr/bin/open LaunchServices kullanır, hiçbir izin istemez.
    """
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["/usr/bin/open", adres],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError as hata:
            print(f"  /usr/bin/open başarısız ({hata}); webbrowser deneniyor")
    import webbrowser
    return webbrowser.open(adres)


def calistir(port: int = 8733, tarayici_ac: bool = True) -> None:
    adres = f"http://127.0.0.1:{port}/"
    if tarayici_ac:
        threading.Timer(1.0, lambda: tarayicida_ac(adres)).start()
    print(f"\n  İş Başvuru Botu paneli:  {adres}\n  (kapatmak için Ctrl+C)\n")
    # 127.0.0.1: yalnız bu makine erişir. debug/reloader kapalı (paketlemede sorun çıkarır).
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
