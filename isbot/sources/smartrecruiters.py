"""SmartRecruiters Posting API — https://api.smartrecruiters.com/v1/companies/{token}/postings
Kimlik doğrulaması YOK. Türkiye'de yaygın (Getir, Trendyol vb. kullanıyor)."""
from __future__ import annotations

from ..models import Job
from .base import Kaynak, bekle, html_temizle, iso_tarih


class SmartRecruiters(Kaynak):
    ad = "smartrecruiters"
    UC = "https://api.smartrecruiters.com/v1/companies/{t}/postings?limit=100&offset={o}"

    def cek(self, board_token: str, sirket_adi: str) -> list[Job]:
        ilanlar: list[Job] = []
        offset = 0
        while True:
            d = self._get(self.UC.format(t=board_token, o=offset))
            parca = d.get("content", [])
            for j in parca:
                loc = j.get("location") or {}
                konum = ", ".join(x for x in [loc.get("city"), loc.get("region"), loc.get("country")] if x)
                uzak = loc.get("remote")
                ilanlar.append(Job(
                    source=self.ad,
                    company=sirket_adi or board_token,
                    board_token=board_token,
                    native_id=str(j.get("id")),
                    title=(j.get("name") or "").strip(),
                    url=j.get("applyUrl") or f"https://jobs.smartrecruiters.com/{board_token}/{j.get('id')}",
                    locations=[konum] if konum else [],
                    description=html_temizle(str(j.get("jobAd", ""))),
                    department=(j.get("department") or {}).get("label", "") if isinstance(j.get("department"), dict) else "",
                    employment_type=(j.get("typeOfEmployment") or {}).get("label", "") if isinstance(j.get("typeOfEmployment"), dict) else "",
                    remote_flag=bool(uzak) if uzak is not None else None,
                    posted_at=iso_tarih(j.get("releasedDate")),
                    updated_at=iso_tarih(j.get("releasedDate")),
                ))
            offset += len(parca)
            if len(parca) < 100 or offset >= d.get("totalFound", 0):
                break
            bekle()
        return ilanlar
