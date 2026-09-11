from .ashby import Ashby
from .base import Kaynak, KaynakHatasi
from .greenhouse import Greenhouse
from .lever import Lever
from .remoteok import RemoteOK
from .remotive import Remotive
from .smartrecruiters import SmartRecruiters
from .toplayicilar import Arbeitnow, Himalayas, Jobicy, TheMuse, WeWorkRemotely
from .tr_panolar import ElemanNet, KariyerNet, TrPano
from .workable import Workable

# Şirket-başına kaynaklar: anahtar = ATS'teki şirket token'ı
KAYNAKLAR: dict[str, type[Kaynak]] = {
    k.ad: k for k in (Greenhouse, Lever, Ashby, SmartRecruiters, Workable)
}

# Şirketler-arası kaynaklar. İkiye ayrılır:
#  - SORGU alanlar: arama terimi başına bir istek (Remotive)
#  - AKIŞ olanlar : tüm akışı sayfalayarak okur, sorgu almaz
SORGU_KAYNAKLARI: dict[str, type[Kaynak]] = {Remotive.ad: Remotive}
AKIS_KAYNAKLARI: dict[str, type[Kaynak]] = {
    k.ad: k for k in (RemoteOK, Arbeitnow, TheMuse, Himalayas, Jobicy, WeWorkRemotely)
}

# Türk panoları: HTML okunur, robots.txt'ye uyulur, hız sınırlıdır ve İKİ AŞAMALIDIR
# (liste taraması ucuz, detay yalnız aday olanlar için). Türkçe pozisyon sorgusu alırlar.
TR_KAYNAKLARI: dict[str, type[TrPano]] = {k.ad: k for k in (KariyerNet, ElemanNet)}

TUM_KAYNAKLAR = {**KAYNAKLAR, **SORGU_KAYNAKLARI, **AKIS_KAYNAKLARI, **TR_KAYNAKLARI}

__all__ = ["KAYNAKLAR", "SORGU_KAYNAKLARI", "AKIS_KAYNAKLARI", "TR_KAYNAKLARI",
           "TUM_KAYNAKLAR", "TrPano", "KariyerNet", "ElemanNet",
           "Kaynak", "KaynakHatasi", "Greenhouse", "Lever", "Ashby", "SmartRecruiters",
           "Workable", "Remotive", "RemoteOK", "Arbeitnow", "TheMuse", "Himalayas",
           "Jobicy", "WeWorkRemotely"]
