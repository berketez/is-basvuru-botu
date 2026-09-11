"""Şirketler-arası toplayıcılar — hepsi kimlik doğrulamasız.

NEDEN ÖNEMLİ: Greenhouse/Lever/Ashby'nin şirketler-arası indeksi yoktur; her şirketi
tek tek eklemek gerekir. Ayrıca o havuz yazılım ağırlıklıdır. Toplayıcılar hem
yüzlerce şirketi tek istekte tarar hem de YAZILIM DIŞI sektörleri getirir.

Ölçüldü (11 Eyl 2026): Arbeitnow'un ilk kaydı "Medizinische Fachangestellte"
(tıbbi sekreter), The Muse'unki "Investment Consultant" — yani sektör kapsamı gerçek.

Not: Bu modüldeki kaynaklar 'sorgu' parametresi almaz; tüm akışı sayfalayarak okur.
Filtreleme sonradan puanlama katmanında yapılır.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from ..models import Job
from .base import Kaynak, bekle, html_temizle, iso_tarih, kodlama_onar


def _epok(v) -> datetime | None:
    """Bazı toplayıcılar epoch saniyeyi STRING olarak gönderiyor."""
    if v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return iso_tarih(v)
    if n > 1e11:            # milisaniye
        n /= 1000.0
    try:
        return datetime.fromtimestamp(n, tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


class Arbeitnow(Kaynak):
    """https://www.arbeitnow.com/api/job-board-api — Almanya/AB, TÜM SEKTÖRLER."""
    ad = "arbeitnow"
    UC = "https://www.arbeitnow.com/api/job-board-api?page={s}"
    SAYFA = 3

    def cek(self, sorgu: str = "", etiket: str = "") -> list[Job]:
        ilanlar: list[Job] = []
        for s in range(1, self.SAYFA + 1):
            d = self._get(self.UC.format(s=s))
            kayitlar = d.get("data", [])
            for j in kayitlar:
                turler = j.get("job_types") or []
                ilanlar.append(Job(
                    source=self.ad,
                    company=kodlama_onar(j.get("company_name") or "?"),
                    board_token="arbeitnow",
                    native_id=str(j.get("slug") or j.get("url")),
                    title=kodlama_onar(j.get("title") or "").strip(),
                    url=j.get("url") or "",
                    locations=[kodlama_onar(j.get("location") or "")] if j.get("location") else [],
                    description=html_temizle(j.get("description")),
                    department=", ".join(j.get("tags") or [])[:120],
                    employment_type=turler[0] if turler else "",
                    remote_flag=bool(j.get("remote")),
                    posted_at=_epok(j.get("created_at")),
                    updated_at=_epok(j.get("created_at")),
                    raw={"tags": j.get("tags"),
                         "workplaceType": "remote" if j.get("remote") else ""},
                ))
            if len(kayitlar) < 50:
                break
            bekle()
        return ilanlar


class TheMuse(Kaynak):
    """https://www.themuse.com/api/public/jobs — ABD ağırlıklı, TÜM SEKTÖRLER.
    Kıdem bilgisini (`levels`) doğrudan veriyor; çıkarım yapmaya gerek yok."""
    ad = "themuse"
    UC = "https://www.themuse.com/api/public/jobs?page={s}"
    SAYFA = 4

    def cek(self, sorgu: str = "", etiket: str = "") -> list[Job]:
        ilanlar: list[Job] = []
        for s in range(1, self.SAYFA + 1):
            d = self._get(self.UC.format(s=s))
            kayitlar = d.get("results", [])
            for j in kayitlar:
                sirket = (j.get("company") or {}).get("name") or "?"
                konumlar = [x.get("name", "") for x in (j.get("locations") or []) if x.get("name")]
                seviyeler = [x.get("name", "") for x in (j.get("levels") or []) if x.get("name")]
                kategoriler = [x.get("name", "") for x in (j.get("categories") or []) if x.get("name")]
                uzak = any("flexible" in k.lower() or "remote" in k.lower() for k in konumlar)
                ilanlar.append(Job(
                    source=self.ad,
                    company=sirket,
                    board_token="themuse",
                    native_id=str(j.get("id")),
                    title=(j.get("name") or "").strip(),
                    url=(j.get("refs") or {}).get("landing_page", ""),
                    locations=konumlar,
                    description=html_temizle(j.get("contents")),
                    department=", ".join(kategoriler),
                    remote_flag=uzak or None,
                    posted_at=iso_tarih(j.get("publication_date")),
                    updated_at=iso_tarih(j.get("publication_date")),
                    # `levels` ATS'in kendi kıdem beyanı — metinden çıkarımdan güvenilir.
                    raw={"seviye": seviyeler, "kategori": kategoriler},
                ))
            if not kayitlar:
                break
            bekle()
        return ilanlar


class Himalayas(Kaynak):
    """https://himalayas.app/jobs/api — uzaktan. expiryDate veriyor (hayalet sinyali)."""
    ad = "himalayas"
    UC = "https://himalayas.app/jobs/api?limit=100&offset={o}"
    SAYFA = 3

    def cek(self, sorgu: str = "", etiket: str = "") -> list[Job]:
        ilanlar: list[Job] = []
        for s in range(self.SAYFA):
            d = self._get(self.UC.format(o=s * 100))
            kayitlar = d.get("jobs", [])
            for j in kayitlar:
                kisit = j.get("locationRestrictions") or []
                maas = None
                if j.get("minSalary") and j.get("maxSalary"):
                    maas = f"{j['minSalary']}-{j['maxSalary']} {j.get('currency') or ''}".strip()
                ilanlar.append(Job(
                    source=self.ad,
                    company=kodlama_onar(j.get("companyName") or "?"),
                    board_token="himalayas",
                    native_id=str(j.get("guid") or j.get("applicationLink")),
                    title=(j.get("title") or "").strip(),
                    url=j.get("applicationLink") or "",
                    locations=kisit or ["Remote"],
                    description=html_temizle(j.get("description") or j.get("excerpt")),
                    department=", ".join(j.get("categories") or []),
                    employment_type=j.get("employmentType") or "",
                    remote_flag=True,
                    posted_at=_epok(j.get("pubDate")),
                    updated_at=_epok(j.get("pubDate")),
                    raw={"salary": maas, "seviye": j.get("seniority"),
                         "son_gecerlilik": j.get("expiryDate"), "workplaceType": "remote"},
                ))
            if len(kayitlar) < 100:
                break
            bekle()
        return ilanlar


class Jobicy(Kaynak):
    """https://jobicy.com/api/v2/remote-jobs — uzaktan, sektör etiketli."""
    ad = "jobicy"
    UC = "https://jobicy.com/api/v2/remote-jobs?count=50"

    def cek(self, sorgu: str = "", etiket: str = "") -> list[Job]:
        d = self._get(self.UC)
        ilanlar: list[Job] = []
        for j in d.get("jobs", []):
            turler = j.get("jobType") or []
            maas = None
            if j.get("salaryMin") and j.get("salaryMax"):
                maas = f"{j['salaryMin']}-{j['salaryMax']} {j.get('salaryCurrency') or ''}".strip()
            ilanlar.append(Job(
                source=self.ad,
                company=kodlama_onar(j.get("companyName") or "?"),
                board_token="jobicy",
                native_id=str(j.get("id")),
                title=(j.get("jobTitle") or "").strip(),
                url=j.get("url") or "",
                locations=[x.strip() for x in (j.get("jobGeo") or "").split(",") if x.strip()] or ["Remote"],
                description=html_temizle(j.get("jobDescription") or j.get("jobExcerpt")),
                department=", ".join(j.get("jobIndustry") or []),
                employment_type=turler[0] if turler else "",
                remote_flag=True,
                posted_at=iso_tarih(j.get("pubDate")),
                updated_at=iso_tarih(j.get("pubDate")),
                raw={"salary": maas, "seviye": j.get("jobLevel"), "workplaceType": "remote"},
            ))
        return ilanlar


class WeWorkRemotely(Kaynak):
    """https://weworkremotely.com/remote-jobs.rss — klasik RSS, uzaktan."""
    ad = "weworkremotely"
    UC = "https://weworkremotely.com/remote-jobs.rss"
    OGE = re.compile(r"<item>(.*?)</item>", re.S)

    def _alan(self, blok: str, ad: str) -> str:
        m = re.search(rf"<{ad}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{ad}>", blok, re.S)
        return (m.group(1).strip() if m else "")

    def cek(self, sorgu: str = "", etiket: str = "") -> list[Job]:
        r = self.s.get(self.UC, timeout=25)
        r.raise_for_status()
        ilanlar: list[Job] = []
        for blok in self.OGE.findall(r.text):
            baslik = html_temizle(self._alan(blok, "title"))
            # WWR başlığı "Şirket: Pozisyon" biçiminde
            sirket, _, poz = baslik.partition(":")
            if not poz:
                sirket, poz = "?", baslik
            bag = self._alan(blok, "link")
            ilanlar.append(Job(
                source=self.ad,
                company=sirket.strip() or "?",
                board_token="weworkremotely",
                native_id=bag.rsplit("/", 1)[-1] or bag,
                title=poz.strip(),
                url=bag,
                locations=[self._alan(blok, "region") or "Remote"],
                description=html_temizle(self._alan(blok, "description")),
                department=self._alan(blok, "category"),
                remote_flag=True,
                posted_at=iso_tarih(self._alan(blok, "pubDate")) or None,
                raw={"workplaceType": "remote"},
            ))
        return ilanlar
