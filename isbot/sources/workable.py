"""Workable public job board API.

Kimlik doğrulaması YOK ama GET değil POST ister (kariyer sayfasının SPA'sı böyle çağırıyor):
    POST https://apply.workable.com/api/v3/accounts/{token}/jobs
Avrupa ve Türkiye'de yaygın. Not: v1 widget ucu ('/api/v1/widget/accounts/{t}')
hesap var olsa bile boş liste döndürüyor — v3 kullanılmalı.
"""
from __future__ import annotations

from ..models import Job
from .base import Kaynak, bekle, html_temizle, iso_tarih

UC = "https://apply.workable.com/api/v3/accounts/{t}/jobs"


class Workable(Kaynak):
    ad = "workable"

    def cek(self, board_token: str, sirket_adi: str) -> list[Job]:
        ilanlar: list[Job] = []
        imlec = None
        for _ in range(20):                       # sayfalama üst sınırı
            govde = {"query": "", "location": [], "department": [], "worktype": [], "remote": []}
            if imlec:
                govde["token"] = imlec
            d = self._post(UC.format(t=board_token), json=govde)
            parca = d.get("results", [])
            for j in parca:
                # v3 çok konumlu ilanlar için `locations` listesi veriyor; `location`
                # yalnız ilkidir. Gizli (hidden) konumlar ilanda gösterilmiyor, alınmaz.
                yerler = [y for y in (j.get("locations") or [j.get("location") or {}])
                          if isinstance(y, dict) and not y.get("hidden")]
                konumlar = []
                for yer in yerler:
                    konum = ", ".join(x for x in [yer.get("city"), yer.get("region"),
                                                  yer.get("country")] if x)
                    if konum and konum not in konumlar:
                        konumlar.append(konum)
                uzak = bool(j.get("workplace") == "remote" or j.get("remote"))
                kimlik = j.get("shortcode") or j.get("id") or j.get("slug")
                # Ölçüldü (2026-10-08): `department` artık liste (["T-Tech"]) ve tarih
                # `published` anahtarında; eski `published_on`/`created_at` gelmiyor,
                # bu yüzden Workable ilanlarının yaşı hiç okunmuyordu.
                bolum = j.get("department") or ""
                if isinstance(bolum, list):
                    bolum = ", ".join(str(b) for b in bolum if b)
                tarih = iso_tarih(j.get("published") or j.get("published_on") or j.get("created_at"))
                ilanlar.append(Job(
                    source=self.ad,
                    company=sirket_adi or board_token,
                    board_token=board_token,
                    native_id=str(kimlik),
                    title=(j.get("title") or "").strip(),
                    url=j.get("url") or f"https://apply.workable.com/{board_token}/j/{kimlik}/",
                    locations=konumlar,
                    description=html_temizle(j.get("description")),
                    department=bolum,
                    employment_type=j.get("type") or "",
                    remote_flag=uzak or None,
                    posted_at=tarih,
                    updated_at=tarih,
                ))
            imlec = d.get("nextPage") or d.get("token")
            if not imlec or not parca:
                break
            bekle()
        return ilanlar
