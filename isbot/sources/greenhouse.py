"""Greenhouse Job Board API — https://boards-api.greenhouse.io/v1/boards/{token}/jobs
Kimlik doğrulaması YOK. first_published + updated_at verir → hayalet tespiti için en zengin kaynak."""
from __future__ import annotations

from ..models import Job
from .base import Kaynak, html_temizle, iso_tarih


class Greenhouse(Kaynak):
    ad = "greenhouse"
    UC = "https://boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true"

    def cek(self, board_token: str, sirket_adi: str) -> list[Job]:
        d = self._get(self.UC.format(t=board_token))
        ilanlar: list[Job] = []
        for j in d.get("jobs", []):
            konum = (j.get("location") or {}).get("name", "") or ""
            konumlar = [p.strip() for p in konum.replace("|", ";").split(";") if p.strip()]
            ofisler = [o.get("name", "") for o in (j.get("offices") or []) if o.get("name")]
            for o in ofisler:
                if o and o not in konumlar:
                    konumlar.append(o)
            bolumler = ", ".join(b.get("name", "") for b in (j.get("departments") or []))
            ilanlar.append(Job(
                source=self.ad,
                company=sirket_adi or j.get("company_name") or board_token,
                board_token=board_token,
                native_id=str(j.get("id")),
                title=j.get("title", "").strip(),
                url=j.get("absolute_url", ""),
                locations=konumlar,
                description=html_temizle(j.get("content")),
                department=bolumler,
                posted_at=iso_tarih(j.get("first_published")),
                updated_at=iso_tarih(j.get("updated_at")),
                raw={"requisition_id": j.get("requisition_id")},
            ))
        return ilanlar
