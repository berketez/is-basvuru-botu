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
                yer = j.get("location") or {}
                konum = ", ".join(x for x in [yer.get("city"), yer.get("region"),
                                              yer.get("country")] if x)
                uzak = bool(yer.get("workplace") == "remote" or j.get("remote"))
                kimlik = j.get("shortcode") or j.get("id") or j.get("slug")
                ilanlar.append(Job(
                    source=self.ad,
                    company=sirket_adi or board_token,
                    board_token=board_token,
                    native_id=str(kimlik),
                    title=(j.get("title") or "").strip(),
                    url=j.get("url") or f"https://apply.workable.com/{board_token}/j/{kimlik}/",
                    locations=[konum] if konum else [],
                    description=html_temizle(j.get("description")),
                    department=j.get("department") or "",
                    employment_type=j.get("type") or "",
                    remote_flag=uzak or None,
                    posted_at=iso_tarih(j.get("published_on") or j.get("created_at")),
                    updated_at=iso_tarih(j.get("published_on") or j.get("created_at")),
                ))
            imlec = d.get("nextPage") or d.get("token")
            if not imlec or not parca:
                break
            bekle()
        return ilanlar
