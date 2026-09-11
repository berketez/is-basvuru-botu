"""RemoteOK — şirketler-arası uzaktan iş API'si. https://remoteok.com/api

Tek uçtan son ~100 ilan döner (sorgu parametresi yok, etiketle süzülür).
İlk kayıt yasal uyarı/telif nesnesidir, ilan değildir — atlanır.
Maaş alanları (salary_min/max) dolu geldiğinde nadir ve değerli bir sinyal.
"""
from __future__ import annotations

from ..models import Job
from .base import Kaynak, html_temizle, iso_tarih, kodlama_onar

UC = "https://remoteok.com/api"


class RemoteOK(Kaynak):
    ad = "remoteok"

    def cek(self, sorgu: str = "", etiket: str = "") -> list[Job]:
        d = self._get(UC)
        if not isinstance(d, list):
            return []
        ilanlar: list[Job] = []
        for j in d:
            if not j.get("id") or not j.get("position"):
                continue                                  # ilk kayıt: yasal uyarı nesnesi
            etiketler = j.get("tags") or []
            konum = kodlama_onar((j.get("location") or "").strip())
            ilanlar.append(Job(
                source=self.ad,
                company=kodlama_onar(j.get("company") or "?"),
                board_token="remoteok",
                native_id=str(j.get("id")),
                title=(j.get("position") or "").strip(),
                url=j.get("url") or j.get("apply_url") or "",
                locations=[konum] if konum else ["Remote"],
                description=html_temizle(j.get("description")) + "\n" + " ".join(etiketler),
                department=", ".join(etiketler[:3]),
                remote_flag=True,
                posted_at=iso_tarih(j.get("date")),
                updated_at=iso_tarih(j.get("date")),
                raw={"salary_min": j.get("salary_min"), "salary_max": j.get("salary_max"),
                     "tags": etiketler, "workplaceType": "remote"},
            ))
        return ilanlar
