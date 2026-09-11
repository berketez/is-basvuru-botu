"""Remotive — ŞİRKETLER-ARASI uzaktan iş API'si. https://remotive.com/api/remote-jobs

NEDEN ÖNEMLİ: Greenhouse/Lever/Ashby'nin şirketler-arası indeksi yoktur; her şirketi
tek tek eklemek gerekir. Bu yüzden 74 şirketlik havuzda erişilebilir ilan sayısı ~166'da
kalıyordu. Remotive tek sorguda yüzlerce şirketi tarar ve hepsi uzaktan ilan.

Ayrıca `candidate_required_location` alanı ilanın kendi beyanıdır ("Worldwide",
"USA Only", "Europe"...). Konumu metinden ÇIKARMAK yerine OKUYORUZ — çok daha güvenilir.
"""
from __future__ import annotations

from ..models import Job
from .base import Kaynak, bekle, html_temizle, iso_tarih

UC = "https://remotive.com/api/remote-jobs?search={q}"


class Remotive(Kaynak):
    ad = "remotive"

    def cek(self, sorgu: str, etiket: str = "") -> list[Job]:
        """Burada 'board_token' bir ŞİRKET değil ARAMA SORGUSUDUR (ör. 'machine learning')."""
        d = self._get(UC.format(q=sorgu.replace(" ", "%20")))
        ilanlar: list[Job] = []
        for j in d.get("jobs", []):
            konum = (j.get("candidate_required_location") or "").strip()
            ilanlar.append(Job(
                source=self.ad,
                company=j.get("company_name") or "?",
                board_token=f"remotive:{sorgu}",
                native_id=str(j.get("id")),
                title=(j.get("title") or "").strip(),
                url=j.get("url") or "",
                # Konum listesi ilanın KENDİ beyanı: "Worldwide", "Europe", "USA Only"...
                locations=[p.strip() for p in konum.split(",") if p.strip()] or ["Remote"],
                description=html_temizle(j.get("description")),
                department=j.get("category") or "",
                employment_type=j.get("job_type") or "",
                remote_flag=True,
                posted_at=iso_tarih(j.get("publication_date")),
                updated_at=iso_tarih(j.get("publication_date")),
                raw={"salary": j.get("salary"), "tags": j.get("tags"),
                     "workplaceType": "remote", "beyan_konum": konum},
            ))
        bekle()
        return ilanlar
