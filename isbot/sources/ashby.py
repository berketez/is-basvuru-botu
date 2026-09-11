"""Ashby Job Board API — https://api.ashbyhq.com/posting-api/job-board/{token}
Kimlik doğrulaması YOK. publishedAt + isRemote + workplaceType verir."""
from __future__ import annotations

from ..models import Job
from .base import Kaynak, html_temizle, iso_tarih


class Ashby(Kaynak):
    ad = "ashby"
    UC = "https://api.ashbyhq.com/posting-api/job-board/{t}?includeCompensation=true"

    def cek(self, board_token: str, sirket_adi: str) -> list[Job]:
        d = self._get(self.UC.format(t=board_token))
        ilanlar: list[Job] = []
        for j in d.get("jobs", []):
            if j.get("isListed") is False:
                continue
            konumlar = [j.get("location")] if j.get("location") else []
            for s in (j.get("secondaryLocations") or []):
                ad = s.get("location") if isinstance(s, dict) else s
                if ad and ad not in konumlar:
                    konumlar.append(ad)
            wt = (j.get("workplaceType") or "").lower()
            uzak = j.get("isRemote")
            if uzak is None and wt:
                uzak = wt == "remote"
            ilanlar.append(Job(
                source=self.ad,
                company=sirket_adi or d.get("name") or board_token,
                board_token=board_token,
                native_id=str(j.get("id")),
                title=(j.get("title") or "").strip(),
                url=j.get("jobUrl") or j.get("applyUrl") or "",
                locations=[k for k in konumlar if k],
                description=j.get("descriptionPlain") or html_temizle(j.get("descriptionHtml")),
                department=j.get("department") or j.get("team") or "",
                employment_type=j.get("employmentType") or "",
                remote_flag=uzak,
                posted_at=iso_tarih(j.get("publishedAt")),
                updated_at=iso_tarih(j.get("updatedAt") or j.get("publishedAt")),
                raw={"compensation": j.get("compensation"), "workplaceType": wt},
            ))
        return ilanlar
