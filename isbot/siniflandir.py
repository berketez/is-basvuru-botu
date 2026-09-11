"""İlanı filtrelenebilir kategorilere ayırır: çalışma şekli ve istihdam türü.

NEDEN GEREKLİ: İş sitelerinin standart filtreleri bunlar (uzaktan/hibrit/ofis,
tam zamanlı/yarı zamanlı/sözleşmeli/staj). Ama ATS'ler bunu tutarsız veriyor:
  Ashby    -> workplaceType: remote|hybrid|onsite   + employmentType: FullTime
  Lever    -> workplaceType + categories.commitment: Full-time|Internship
  Workable -> location.workplace + type
  Greenhouse -> HİÇBİRİ (594 ilanda tek alan yok)
Bu yüzden ATS alanı varsa o kullanılır, yoksa başlık/metinden çıkarım yapılır.
Çıkarım yapılamıyorsa "bilinmiyor" döner — uydurulmaz.
"""
from __future__ import annotations

import re

from .models import Job

UZAKTAN = re.compile(r"(?i)\b(fully[- ]remote|100% remote|remote[- ]first|work from home|"
                     r"wfh|tamamen uzaktan|remote position|remote role|distributed team)\b")
# Konum/başlık alanı için: orada "Hybrid" yazıyorsa ilanın kendi beyanıdır.
HIBRIT = re.compile(r"(?i)\b(hybrid|hibrit|(\d\s*(days?|gün)\s*(a week|per week|haftada)?"
                    r"\s*(in|at)\s*(the\s*)?office)|office[- ]based with|part[- ]remote)\b")
# İLAN METNİ için: "hybrid" sözcüğü metinde çalışma şeklinden BAŞKA anlamlarda da
# geçiyor. ÖLÇÜLDÜ: 301 ilan, konum alanı "Remote" dediği hâlde metindeki
# "This is a hybrid technical and commercial role" cümlesi yüzünden HİBRİT
# etiketleniyordu; kullanıcı "uzaktan" filtresini işaretleyince bu ilanlar kayboluyordu.
# Bu yüzden metinde yalnız ÇALIŞMA DÜZENİNİ anlatan kalıplar sayılır.
HIBRIT_METIN = re.compile(
    r"(?i)("
    r"\bhybrid\s*(work|working|model|schedule|setup|arrangement|policy|environment|"
    r"office|remote|position|roles?\s*(are|is)?\s*(based|located))\b|"
    r"\b(work|working|schedule|arrangement|model|policy)\s*(is|:)?\s*hybrid\b|"
    r"\bhibrit\b|"
    r"\d\s*(days?|gün)\s*(a week|per week|haftada)?\s*(in|at)\s*(the\s*)?office|"
    r"office[- ]based with|part[- ]remote)")
OFIS = re.compile(r"(?i)\b(on[- ]?site|onsite|in[- ]office|ofisten|office[- ]based|"
                  r"in[- ]person|relocat)\b")

TAM = re.compile(r"(?i)\b(full[- ]?time|tam zamanlı|permanent|fte)\b")
YARIM = re.compile(r"(?i)\b(part[- ]?time|yarı zamanlı)\b")
SOZLESME = re.compile(r"(?i)\b(contract|contractor|freelance|temporary|fixed[- ]term|"
                      r"sözleşmeli|geçici|b2b)\b")
STAJ = re.compile(r"(?i)\b(intern|internship|stajyer|staj|working student|apprentice|"
                  r"co[- ]op|new ?grad|graduate program)\b")

CALISMA = ("uzaktan", "hibrit", "ofis", "bilinmiyor")
ISTIHDAM = ("tam zamanlı", "yarı zamanlı", "sözleşmeli", "staj", "bilinmiyor")


def calisma_sekli(job: Job) -> str:
    """uzaktan | hibrit | ofis | bilinmiyor"""
    ham = (job.raw.get("workplaceType") or "").lower()
    if ham in ("remote", "hybrid", "onsite"):
        return {"remote": "uzaktan", "hybrid": "hibrit", "onsite": "ofis"}[ham]

    alan = " ".join(job.locations) + " " + job.title
    metin = job.description[:5000]
    # SIRA ÖNEMLİ: konum alanı ilanın KENDİ beyanıdır, metin ise serbest yazıdır.
    # Alan bir şey diyorsa metin onu ezemez.
    if HIBRIT.search(alan):
        return "hibrit"
    if re.search(r"(?i)\b(remote|uzaktan|anywhere)\b", alan):
        return "uzaktan"
    if job.remote_flag is True:
        return "uzaktan"
    if HIBRIT_METIN.search(metin):
        return "hibrit"
    if UZAKTAN.search(metin):
        return "uzaktan"
    if OFIS.search(metin) or job.locations:
        return "ofis"
    return "bilinmiyor"


def istihdam_turu(job: Job) -> str:
    """tam zamanlı | yarı zamanlı | sözleşmeli | staj | bilinmiyor"""
    ham = re.sub(r"[^a-z]", "", (job.employment_type or "").lower())
    esle = {"fulltime": "tam zamanlı", "parttime": "yarı zamanlı", "permanent": "tam zamanlı",
            "contract": "sözleşmeli", "contractor": "sözleşmeli", "temporary": "sözleşmeli",
            "intern": "staj", "internship": "staj", "graduate": "staj"}
    if ham in esle:
        return esle[ham]

    alan = job.title + " " + (job.employment_type or "")
    if STAJ.search(alan):
        return "staj"
    metin = job.description[:4000]
    if STAJ.search(metin) and not TAM.search(alan):
        return "staj"
    if YARIM.search(alan) or YARIM.search(metin):
        return "yarı zamanlı"
    if SOZLESME.search(alan) or SOZLESME.search(metin):
        return "sözleşmeli"
    if TAM.search(alan) or TAM.search(metin):
        return "tam zamanlı"
    return "bilinmiyor"
