"""ATS bağlayıcıları için ortak taban.

Tasarım ilkesi: hepsi HERKESE AÇIK, kimlik doğrulaması istemeyen uçlar.
Atlatılacak koruma yok — bu uçlar okunmak için var. Yine de nazik davranıyoruz:
gerçek User-Agent, istekler arası gecikme, hata toleransı.
"""
from __future__ import annotations

import html
import random
import re
import time
from datetime import datetime, timezone

import requests

from ..models import Job

# HTTP basliklari latin-1 olmak zorunda -> UA saf ASCII kalmali.
UA = "is-basvuru-bot/0.1 (+https://github.com/berketez/is-basvuru-bot) personal job search tool"
TIMEOUT = 20
GECIKME = (0.6, 1.4)   # istekler arası saniye — sunucuya nazik ol
YENIDEN_DENEME = 3     # 429/5xx/timeout için deneme sayısı
GERI_CEKILME = 1.5     # üstel geri çekilme taban saniyesi


class KaynakHatasi(Exception):
    pass


def _oturum() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    return s


def bekle() -> None:
    time.sleep(random.uniform(*GECIKME))


def kodlama_onar(s: str) -> str:
    """UTF-8 baytları latin-1 sanılmış metni onarır ('Ã¶' -> 'ö', 'Ù\x85' -> Arapça harf).
    RemoteOK bazı konum alanlarını bu şekilde çift kodlanmış gönderiyor."""
    if not s or not any(ch in s for ch in "ÃÂÙØÐ"):
        return s
    try:
        onarilmis = s.encode("latin-1").decode("utf-8")
        # Onarım gerçekten iyileştirdiyse kullan (bozuk işaret sayısı azaldıysa)
        if sum(s.count(c) for c in "ÃÂÙØ") > sum(onarilmis.count(c) for c in "ÃÂÙØ"):
            return onarilmis
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return s


def html_temizle(s: str | None) -> str:
    """HTML ilan metnini düz metne indirger (puanlama bunu tarar)."""
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "• ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def iso_tarih(v) -> datetime | None:
    """ATS'lerin farklı tarih formatlarını tek tipe indirger."""
    if v is None:
        return None
    if isinstance(v, (int, float)):                       # Lever: epoch ms
        try:
            return datetime.fromtimestamp(v / 1000, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(v, str):
        t = v.strip().replace("Z", "+00:00")
        try:
            d = datetime.fromisoformat(t)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


class Kaynak:
    """Her ATS bağlayıcısı bunu uygular."""
    ad: str = "base"

    def __init__(self) -> None:
        self.s = _oturum()

    def cek(self, board_token: str, sirket_adi: str) -> list[Job]:
        raise NotImplementedError

    def _istek(self, yontem: str, url: str, **kw):
        """Geçici hatalarda yeniden dener (429 ve 5xx), kalıcı hatalarda denemez.

        NEDEN: Her taramada workable/ttech 429 veriyordu ve o şirket tamamen
        atlanıyordu. 429 geçici bir durumdur — beklenip tekrar denenmeli.
        404 (yanlış anahtar) kalıcıdır, denemek boşa istek olur.
        """
        son_hata = None
        for deneme in range(YENIDEN_DENEME):
            try:
                r = self.s.request(yontem, url, timeout=TIMEOUT, **kw)
            except (requests.Timeout, requests.ConnectionError) as e:
                son_hata = e
                time.sleep(GERI_CEKILME * (2 ** deneme) + random.uniform(0, 0.4))
                continue
            if r.status_code == 404:
                raise KaynakHatasi(f"404 — anahtar geçersiz: {url}")
            if r.status_code == 429:
                # Hız sınırı saniyeler içinde açılmaz. Uzun uzun beklemek yerine BİR kez
                # kısa deneyip vazgeçiyoruz: 74 şirketlik taramada tek şirket için 60 sn
                # harcamak taramanın tamamını geciktiriyordu.
                son_hata = KaynakHatasi("429 — hız sınırı")
                if deneme >= 1:
                    break
                bekleme = r.headers.get("Retry-After")
                try:
                    sn = min(float(bekleme), 5.0) if bekleme else 2.0
                except ValueError:
                    sn = 2.0
                time.sleep(sn)
                continue
            if 500 <= r.status_code < 600:
                son_hata = KaynakHatasi(f"{r.status_code} — sunucu hatası")
                time.sleep(GERI_CEKILME * (2 ** deneme) + random.uniform(0, 0.4))
                continue
            r.raise_for_status()
            return r.json()
        raise KaynakHatasi(f"{YENIDEN_DENEME} denemede başarısız: {son_hata}")

    def _get(self, url: str, **kw):
        return self._istek("GET", url, **kw)

    def _post(self, url: str, **kw):
        return self._istek("POST", url, **kw)
