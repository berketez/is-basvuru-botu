"""Türk panoları için sayfa önbelleği, istek defteri ve süreçler arası kilit.

NEDEN: kariyer.net PerimeterX (HUMAN) bot koruması arkasında (yanıtta `_pxhd` çerezi;
ölçüldü 2026-10-12). Koruma, art arda gelen istekleri sayıp IP'yi saatlerce kapatıyor:
4 sn arayla ~45, 8 sn arayla ~30 istekten sonra 403 geldi. Ölçülen asıl kayıp şuydu:
bir kullanıcının taraması engeli tetikledi, 20 dakika sonra ikinci bir CV'nin taraması
kariyer.net'e HİÇ ulaşamadı ve kısa listesi yalnız alakasız yabancı ilanlardan oluştu.

Koruma atlatılmaz (parmak izi taklidi, CAPTCHA çözme, IP değiştirme YOK). Yapılan şey
daha AZ istek atmak:
  - aynı sayfa ikinci kez istenmez: liste sayfası saatlerce, ilan metni günlerce geçerli;
    ikinci CV'nin taraması birincinin sayfalarını yeniden kullanır,
  - pano başına kayan pencereli istek bütçesi tutulur (diskte, süreçler arası),
  - istekler pano başına TEK sıradan geçer: eskiden her sorgu ayrı iş parçacığında
    koşuyordu ve "en az 8 sn arayla" sayacı kilitsiz olduğu için aynı anda birden çok
    istek gidebiliyordu.
Engel ya da bütçe varken önbellekteki (bayat) sayfa kullanılır ve bu kullanıcıya söylenir.
"""
from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
import zlib

from ..yollar import veri_dosya

_SEMA = """
CREATE TABLE IF NOT EXISTS sayfa (
    url    TEXT PRIMARY KEY,
    alindi REAL NOT NULL,
    govde  BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS istek (
    pano  TEXT NOT NULL,
    zaman REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_istek ON istek(pano, zaman);
"""

_kilitler: dict[str, threading.Lock] = {}
_kilitler_kilidi = threading.Lock()


def _baglan() -> sqlite3.Connection:
    # Her çağrıda yeni bağlantı: sqlite3 bağlantısı iş parçacıkları arasında paylaşılmaz.
    db = sqlite3.connect(veri_dosya("data", "pano-onbellek.db"), timeout=30)
    db.executescript(_SEMA)
    return db


def oku(url: str) -> tuple[float, str] | None:
    """(alınma zamanı, sayfa) ya da None."""
    try:
        with contextlib.closing(_baglan()) as db:
            r = db.execute("SELECT alindi, govde FROM sayfa WHERE url=?", (url,)).fetchone()
    except sqlite3.Error:
        return None
    if not r:
        return None
    try:
        return r[0], zlib.decompress(r[1]).decode("utf-8")
    except (zlib.error, UnicodeDecodeError):
        return None


def yaz(url: str, govde: str) -> None:
    try:
        with contextlib.closing(_baglan()) as db, db:
            db.execute("INSERT OR REPLACE INTO sayfa(url, alindi, govde) VALUES(?,?,?)",
                       (url, time.time(), zlib.compress(govde.encode("utf-8"), 6)))
    except sqlite3.Error:
        pass                        # önbellek yazılamazsa tarama yine çalışır


def istek_kaydet(pano: str) -> None:
    try:
        with contextlib.closing(_baglan()) as db, db:
            db.execute("INSERT INTO istek(pano, zaman) VALUES(?,?)", (pano, time.time()))
    except sqlite3.Error:
        pass


def istek_sayisi(pano: str, saniye: float) -> int:
    """Son `saniye` içinde panoya atılan (ağa çıkan) istek sayısı."""
    try:
        with contextlib.closing(_baglan()) as db:
            return db.execute("SELECT COUNT(*) FROM istek WHERE pano=? AND zaman>?",
                              (pano, time.time() - saniye)).fetchone()[0]
    except sqlite3.Error:
        return 0


def temizle(gun: float = 30) -> None:
    """Eski sayfaları ve istek kayıtlarını siler (önbellek sınırsız büyümesin)."""
    sinir = time.time() - gun * 86400
    try:
        with contextlib.closing(_baglan()) as db, db:
            db.execute("DELETE FROM sayfa WHERE alindi<?", (sinir,))
            db.execute("DELETE FROM istek WHERE zaman<?", (time.time() - 2 * 86400,))
    except sqlite3.Error:
        pass


@contextlib.contextmanager
def pano_kilidi(pano: str):
    """Panoya giden istekleri TEK sıraya sokar: aynı süreçteki iş parçacıkları için
    threading.Lock, ard arda çalışan süreçler (iki tarama, panel + komut satırı) için
    dosya kilidi. Kilit, "son isteğin zamanını oku → bekle → iste → zamanı yaz" adımlarını
    bölünmez kılar; eskiden iki iş parçacığı aynı damgayı okuyup aynı anda istek atıyordu."""
    with _kilitler_kilidi:
        k = _kilitler.setdefault(pano, threading.Lock())
    with k:
        dosya = open(veri_dosya("data", f"pano-{pano}.lock"), "a+")
        try:
            try:
                import fcntl
                fcntl.flock(dosya.fileno(), fcntl.LOCK_EX)
            except ImportError:                       # Windows: süreç içi kilit yeterli
                pass
            yield
        finally:
            dosya.close()                             # kapanınca flock kendiliğinden düşer
