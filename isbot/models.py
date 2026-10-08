"""Tüm ATS'lerden gelen ilanların normalize edildiği tek veri modeli."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    # --- kimlik ---
    source: str                 # greenhouse | lever | ashby | workable | smartrecruiters | recruitee
    company: str                # şirketin okunur adı
    board_token: str            # ATS'teki şirket anahtarı
    native_id: str              # ATS'in kendi ilan kimliği
    # --- içerik ---
    title: str
    url: str
    locations: list[str] = field(default_factory=list)
    description: str = ""       # düz metin (HTML temizlenmiş)
    department: str = ""
    employment_type: str = ""
    remote_flag: bool | None = None      # ATS açıkça söylüyorsa
    # --- zaman (hayalet tespitinin temeli) ---
    posted_at: datetime | None = None    # ilk yayın
    updated_at: datetime | None = None   # son güncelleme
    # --- iç kullanım ---
    first_seen: datetime = field(default_factory=_now)
    last_seen: datetime = field(default_factory=_now)
    raw: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # ATS'ler alan biçimini habersiz değiştiriyor: Workable v3 `department`'ı
        # ["T-Tech"] diye LİSTE döndürmeye başladı, liste SQLite'a yazılamadığı için
        # tek bir ilan BÜTÜN taramayı düşürdü ("Error binding parameter 10").
        # Metin alanları burada metne indirgenir; kaynak bağlayıcısı unutsa da depo çökmez.
        for ad in ("company", "title", "url", "description", "department", "employment_type"):
            v = getattr(self, ad)
            if isinstance(v, (list, tuple)):
                setattr(self, ad, ", ".join(str(x) for x in v if x))
            elif v is None:
                setattr(self, ad, "")
            elif not isinstance(v, str):
                setattr(self, ad, str(v))
        self.locations = [str(k) for k in (self.locations or []) if k]

    @property
    def uid(self) -> str:
        """Kalıcı benzersiz kimlik. Aynı ilan yeniden yayımlanırsa native_id değişir,
        bu yüzden hayalet tespiti ayrıca title_key üzerinden de bakar."""
        return f"{self.source}:{self.board_token}:{self.native_id}"

    @property
    def title_key(self) -> str:
        """Yeniden yayım (repost) tespiti için normalize başlık.
        'Senior ML Engineer (Remote)' ve 'Senior ML Engineer' aynı anahtara düşer."""
        t = self.title.lower()
        t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)            # parantez içi
        t = re.sub(r"[^a-z0-9+#]+", " ", t)
        t = re.sub(r"\b(remote|hybrid|onsite|f\s?m\s?d|m\s?f\s?d|w)\b", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return f"{self.board_token}|{t}"

    @property
    def content_hash(self) -> str:
        """İçerik parmak izi. updated_at değişip bu değişmiyorsa → sahte tazeleme."""
        blob = f"{self.title}|{'|'.join(sorted(self.locations))}|{self.description}"
        return hashlib.sha256(blob.encode("utf-8", "ignore")).hexdigest()[:16]

    @property
    def age_days(self) -> float | None:
        ref = self.posted_at or self.updated_at
        if ref is None:
            return None
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        # Saat dilimi hataları ilanı 'gelecekte' gösterebiliyor; yaş negatif olamaz.
        return max(0.0, (_now() - ref).total_seconds() / 86400.0)

    @property
    def text(self) -> str:
        """Puanlamanın taradığı birleşik metin."""
        return f"{self.title}\n{self.department}\n{' '.join(self.locations)}\n{self.description}"
