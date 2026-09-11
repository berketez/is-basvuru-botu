#!/usr/bin/env python3
"""Paketlenmiş uygulamanın giriş noktası.

Çift tıklanınca: yerel sunucu 127.0.0.1'de kalkar, tarayıcı kendiliğinden açılır.
Kullanıcı terminal görmez, Python kurmaz.

DİKKAT -- çift tıklama ile terminalden çalıştırmak macOS'ta AYNI ŞEY DEĞİL.
İlk sürüm terminalde kusursuz çalışıyordu, Finder'dan açılınca Dock simgesi
sonsuza kadar zıplıyor ve tarayıcı hiç açılmıyordu. İki ayrı sebebi vardı:

1) DOCK ZIPLAMASI. LaunchServices ile açılan bir .app, "açıldım" diye sisteme
   kaydolmazsa Dock beklemeyi sürdürür. Salt Flask koşan bir süreç hiç kaydolmaz
   (`lsappinfo find bundleid=...` bomboş dönüyordu). Çözüm: Flask arka plan
   thread'ine alındı, ana thread NSApplication çalıştırıyor. Uygulama artık
   gerçek bir Dock uygulaması; simge zıplamayı bırakıyor, sağ tık > Çık çalışıyor.

2) TARAYICI AÇILMAMASI. Ayrıntı ve çözüm: isbot/server.py -> tarayicida_ac().

Ayrıca Finder'dan açılınca stdout/stderr hiçbir yere gitmez; arıza sessiz kalır.
O yüzden her şey ~/Library/Logs/IsBasvuruBotu.log dosyasına yazılıyor.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ADRES = "127.0.0.1"
ILK_PORT = 8733
PORT_DENEMESI = 12
GUNLUK = Path.home() / "Library" / "Logs" / "IsBasvuruBotu.log"


# ----------------------------- günlük -----------------------------
def gunluge_yonlendir() -> None:
    """Finder'dan açılınca stdout/stderr yok olur; dosyaya al.

    PyInstaller'ın penceresiz kipinde sys.stdout None olabilir, o yüzden
    içe aktarmalardan ÖNCE çağrılır: Flask/werkzeug kendi akışını bağlamadan.
    """
    try:
        GUNLUK.parent.mkdir(parents=True, exist_ok=True)
        akis = open(GUNLUK, "a", buffering=1, encoding="utf-8")
    except OSError:
        return                                   # günlük tutulamıyorsa da çalış
    sys.stdout = akis
    sys.stderr = akis
    print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} açılıyor (pid {os.getpid()}) ---")


# ----------------------------- port -----------------------------
def panel_adresi(port: int) -> str:
    return f"http://{ADRES}:{port}/"


def port_bos_mu(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex((ADRES, port)) != 0


def bizim_panel_mi(port: int) -> bool:
    """Bu portta koşan BİZ miyiz, alakasız bir program mı?

    Künyeye bakılıyor (/api/saglik -> "uygulama"). Yalnız "port dolu" bilgisiyle
    karar verilse, başka bir programın portuna tarayıcı açardık.
    """
    try:
        with urllib.request.urlopen(panel_adresi(port) + "api/saglik", timeout=2) as yanit:
            return b"isbasvurubotu" in yanit.read(500)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def sunucu_ayaga_kalkti_mi(port: int, en_fazla_sn: float = 20.0) -> bool:
    """Tarayıcıyı sunucu YANIT VERMEDEN açmak boş sayfa gösterir; bekle."""
    son = time.monotonic() + en_fazla_sn
    while time.monotonic() < son:
        if bizim_panel_mi(port):
            return True
        time.sleep(0.25)
    return False


# ----------------------------- Cocoa (Dock kaydı) -----------------------------
def _objc_kur():
    """libobjc + AppKit bağlar, mesaj gönderici döndürür. Olmazsa None.

    pyobjc kullanılmıyor: pakete ~30 MB ve bir sürü gizli içe aktarma eklerdi.
    Gereken üç çağrı ctypes ile doğrudan yapılıyor.
    """
    import ctypes
    import ctypes.util
    from ctypes import c_char_p, c_void_p

    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")
    except (OSError, TypeError) as hata:
        print(f"  AppKit yüklenemedi: {hata}")
        return None, None

    objc.objc_getClass.restype = c_void_p
    objc.objc_getClass.argtypes = [c_char_p]
    objc.sel_registerName.restype = c_void_p
    objc.sel_registerName.argtypes = [c_char_p]

    def gonder(hedef, secici, *arg, donus=c_void_p, tipler=()):
        # DİKKAT: arm64'te objc_msgSend her çağrıda DOĞRU imzayla çağrılmalı;
        # tek bir genel prototip yeterli değil, bozuk argüman çökmeye yol açar.
        f = objc.objc_msgSend
        f.restype = donus
        f.argtypes = [c_void_p, c_void_p, *tipler]
        return f(hedef, objc.sel_registerName(secici), *arg)

    return objc, gonder


def _tekrar_tiklamayi_izle(objc, gonder, geri_cagri) -> None:
    """Dock simgesine yeniden tıklanınca panel sekmesini geri aç.

    Uygulama zaten koşuyorken simgeye tıklamak yeni bir süreç başlatmaz, yalnız
    var olanı öne alır. Penceresi olmayan bir uygulamada bu hiçbir şey yapmazdı:
    sekmesini kapatmış kullanıcı panele dönemezdi. Burada "öne geldik mi" diye
    bakılıp sekme yeniden açılıyor.
    """
    from ctypes import c_int

    NSWorkspace = objc.objc_getClass(b"NSWorkspace")
    if not NSWorkspace:
        return
    benim_pid = os.getpid()
    onceden_ondeydi = True            # açılışta tetiklenmesin
    while True:
        time.sleep(0.8)
        try:
            calisma_alani = gonder(NSWorkspace, b"sharedWorkspace")
            onde = gonder(calisma_alani, b"frontmostApplication")
            ondeyiz = bool(onde) and gonder(onde, b"processIdentifier", donus=c_int) == benim_pid
        except Exception as hata:                # izleyici çökerse uygulama yaşasın
            print(f"  ön plan izleyicisi durdu: {hata}")
            return
        if ondeyiz and not onceden_ondeydi:
            print("  simgeye yeniden tıklandı, panel açılıyor")
            geri_cagri()
        onceden_ondeydi = ondeyiz


def dock_uygulamasi_olarak_calis(geri_cagri) -> bool:
    """Sisteme 'açıldım' de ve olay döngüsünü sür. Başarılıysa GERİ DÖNMEZ.

    False dönerse çağıran sonsuz beklemeye düşer: panel yine çalışır, yalnız
    Dock simgesi zıplamayı sürdürür.
    """
    from ctypes import c_bool, c_int

    objc, gonder = _objc_kur()
    if objc is None:
        return False
    sinif = objc.objc_getClass(b"NSApplication")
    if not sinif:
        print("  NSApplication sınıfı bulunamadı")
        return False
    uygulama = gonder(sinif, b"sharedApplication")
    if not uygulama:
        print("  sharedApplication boş döndü")
        return False

    # 0 = NSApplicationActivationPolicyRegular: Dock'ta görün, menü çubuğu al.
    gonder(uygulama, b"setActivationPolicy:", c_int(0), donus=c_bool, tipler=[c_int])
    gonder(uygulama, b"finishLaunching")         # zıplamayı bitiren çağrı bu
    print("  Dock kaydı tamam")

    threading.Thread(target=_tekrar_tiklamayi_izle,
                     args=(objc, gonder, geri_cagri), daemon=True).start()

    # activateIgnoringOtherApps ÇAĞRILMIYOR: odağı tarayıcıdan çalardı.
    gonder(uygulama, b"run")                     # olay döngüsü; geri dönmez
    return True


# ----------------------------- ana akış -----------------------------
def main() -> int:
    gunluge_yonlendir()

    from isbot.server import calistir, tarayicida_ac
    from isbot.yollar import ilk_kurulum, veri_kok

    for yeni in ilk_kurulum():
        print(f"  hazır ayar kopyalandı: {yeni}")
    print(f"  veri klasörü: {veri_kok()}")

    # Port meşgulse: bizsek var olanı göster, değilse sıradakini dene.
    port = ILK_PORT
    for _ in range(PORT_DENEMESI):
        if port_bos_mu(port):
            break
        if bizim_panel_mi(port):
            print(f"  panel zaten {port} portunda çalışıyor, sekme açılıyor")
            tarayicida_ac(panel_adresi(port))
            return 0
        port += 1
    else:
        print("boş port bulunamadı", file=sys.stderr)
        return 1

    adres = panel_adresi(port)
    # Flask arka planda: ana thread Dock olay döngüsüne lazım.
    threading.Thread(target=calistir, kwargs={"port": port, "tarayici_ac": False},
                     daemon=True).start()

    if not sunucu_ayaga_kalkti_mi(port):
        print("sunucu ayağa kalkmadı; günlüğe bak", file=sys.stderr)
        tarayicida_ac(f"file://{GUNLUK}")        # kullanıcı sebebi görsün
        return 1
    print(f"  panel hazır: {adres}")
    tarayicida_ac(adres)

    if not dock_uygulamasi_olarak_calis(lambda: tarayicida_ac(adres)):
        print("  Dock kaydı yapılamadı; panel yine de çalışıyor")
        threading.Event().wait()                 # sunucuyu ayakta tut
    return 0


if __name__ == "__main__":
    sys.exit(main())
