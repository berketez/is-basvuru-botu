"""Lever Postings API — https://api.lever.co/v0/postings/{token}?mode=json
Kimlik doğrulaması YOK. Sadece createdAt verir (updated_at yok) → tazelik sinyali daha zayıf."""
from __future__ import annotations

from ..models import Job
from .base import Kaynak, html_temizle, iso_tarih


class Lever(Kaynak):
    ad = "lever"
    UC = "https://api.lever.co/v0/postings/{t}?mode=json"

    def cek(self, board_token: str, sirket_adi: str) -> list[Job]:
        d = self._get(self.UC.format(t=board_token))
        if not isinstance(d, list):
            return []
        ilanlar: list[Job] = []
        for j in d:
            kat = j.get("categories") or {}
            konumlar = list(kat.get("allLocations") or [])
            if kat.get("location") and kat["location"] not in konumlar:
                konumlar.insert(0, kat["location"])
            wt = (j.get("workplaceType") or "").lower()
            metin = j.get("descriptionPlain") or html_temizle(j.get("description"))
            ek = j.get("additionalPlain") or ""
            ilanlar.append(Job(
                source=self.ad,
                company=sirket_adi or board_token,
                board_token=board_token,
                native_id=str(j.get("id")),
                title=(j.get("text") or "").strip(),
                url=j.get("hostedUrl") or j.get("applyUrl") or "",
                locations=konumlar,
                description=f"{metin}\n{ek}".strip(),
                department=kat.get("department") or "",
                employment_type=kat.get("commitment") or "",
                remote_flag=True if wt == "remote" else (False if wt in ("onsite", "hybrid") else None),
                posted_at=iso_tarih(j.get("createdAt")),
                updated_at=iso_tarih(j.get("createdAt")),
                raw={"workplaceType": wt, "team": kat.get("team")},
            ))
        return ilanlar
