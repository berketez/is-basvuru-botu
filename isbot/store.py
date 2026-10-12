"""İlan geçmişi (SQLite).

NEDEN GEREKLİ: Hayalet ilan tespitinin güçlü sinyalleri ZAMAN İÇİNDE ortaya çıkar —
"aynı ilan yeni kimlikle tekrar yayımlandı", "updated_at değişti ama içerik aynı"
(sahte tazeleme), "bu ilan 6 aydır hiç kapanmadı". Bunlar tek bir koşuda görülemez.
Bu yüzden ilk günden itibaren her koşu kaydediliyor; sinyal haftalar geçtikçe güçlenir.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

SEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uid           TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    company       TEXT NOT NULL,
    board_token   TEXT NOT NULL,
    native_id     TEXT NOT NULL,
    title         TEXT NOT NULL,
    title_key     TEXT NOT NULL,
    url           TEXT,
    locations     TEXT,
    department    TEXT,
    description   TEXT,
    posted_at     TEXT,
    updated_at    TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    content_hash  TEXT,
    gorulme_sayisi INTEGER DEFAULT 1,
    kapandi_mi    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_jobs_titlekey ON jobs(title_key);
CREATE INDEX IF NOT EXISTS ix_jobs_token    ON jobs(board_token);

-- Her koşuda her ilan için bir satır: sahte tazeleme buradan yakalanır.
CREATE TABLE IF NOT EXISTS sightings (
    uid          TEXT NOT NULL,
    run_id       INTEGER NOT NULL,
    seen_at      TEXT NOT NULL,
    content_hash TEXT,
    updated_at   TEXT,
    PRIMARY KEY (uid, run_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    n_jobs     INTEGER DEFAULT 0,
    notlar     TEXT
);
"""


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _tarih(s: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


# İlanın tabloda kolonu olmayan alanları. Yalnız tekrar kullanılırken gerekenler.
_EK_RAW = ("workplaceType", "salary", "salary_min", "salary_max", "son_gecerlilik", "sektor")


def _ek(job: Job) -> str | None:
    d = {k: job.raw[k] for k in _EK_RAW if job.raw.get(k) not in (None, "")}
    if job.employment_type:
        d["employment_type"] = job.employment_type
    if job.remote_flag is not None:
        d["remote_flag"] = job.remote_flag
    return json.dumps(d, ensure_ascii=False) if d else None


class Depo:
    def __init__(self, yol: str | Path = "data/jobs.db") -> None:
        self.yol = Path(yol)
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.yol)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SEMA)
        # EK alanlar (istihdam türü, çalışma modeli, maaş, son geçerlilik): tablo ilk
        # sürümde bunları tutmuyordu. Önceki taramadan gelen ilan havuza yeniden
        # alınırken (bkz. son_pano_ilanlari) bu bilgiler kaybolmasın diye eklendi.
        if "ek" not in {r["name"] for r in self.db.execute("PRAGMA table_info(jobs)")}:
            self.db.execute("ALTER TABLE jobs ADD COLUMN ek TEXT")
        self.db.commit()

    # ---------- koşu ----------
    def kosu_baslat(self, notlar: str = "") -> int:
        c = self.db.execute(
            "INSERT INTO runs(started_at, notlar) VALUES(?,?)",
            (datetime.now(timezone.utc).isoformat(), notlar),
        )
        self.db.commit()
        return c.lastrowid

    def kosu_bitir(self, run_id: int, n: int) -> None:
        self.db.execute("UPDATE runs SET n_jobs=? WHERE run_id=?", (n, run_id))
        self.db.commit()

    # ---------- yazma ----------
    def kaydet(self, job: Job, run_id: int) -> dict:
        """İlanı kaydeder/günceller. Geçmişe dayalı sinyalleri döndürür."""
        simdi = datetime.now(timezone.utc).isoformat()
        onceki = self.db.execute("SELECT * FROM jobs WHERE uid=?", (job.uid,)).fetchone()
        sinyal = {"yeni": onceki is None, "sahte_tazeleme": False, "gorulme_sayisi": 1,
                  "ilk_gorulme": simdi}

        if onceki is None:
            self.db.execute(
                """INSERT INTO jobs(uid,source,company,board_token,native_id,title,title_key,url,
                   locations,department,description,posted_at,updated_at,first_seen,last_seen,
                   content_hash,ek)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job.uid, job.source, job.company, job.board_token, job.native_id, job.title,
                 job.title_key, job.url, json.dumps(job.locations, ensure_ascii=False),
                 job.department, job.description, _iso(job.posted_at), _iso(job.updated_at),
                 simdi, simdi, job.content_hash, _ek(job)),
            )
        else:
            # SAHTE TAZELEME: ATS'te updated_at ilerlemiş ama içerik bit bit aynı.
            # İlanı "taze" göstermek için yapılan dokunuş — klasik hayalet davranışı.
            if (onceki["content_hash"] == job.content_hash
                    and onceki["updated_at"] and _iso(job.updated_at)
                    and onceki["updated_at"] != _iso(job.updated_at)):
                sinyal["sahte_tazeleme"] = True
            sinyal["gorulme_sayisi"] = onceki["gorulme_sayisi"] + 1
            sinyal["ilk_gorulme"] = onceki["first_seen"]
            # Başlık, konum, URL ve yayın tarihi de tazelenir: ilan düzenlenince
            # (başlık değişir, konum eklenir) tablo eski hâlde kalıyordu ve hem
            # tekilleştirme hem yeniden-yayım sorgusu bayat title_key ile çalışıyordu.
            # METİN KORUNUR: Türk panosu ilanı liste sayfasından METİNSİZ gelir; önceki
            # taramada çekilmiş metnin üstüne boşu yazılıyordu.
            aciklama = job.description or (onceki["description"] or "")
            self.db.execute(
                """UPDATE jobs SET last_seen=?, updated_at=?, content_hash=?, description=?,
                   title=?, title_key=?, url=?, locations=?, department=?, posted_at=?,
                   gorulme_sayisi=gorulme_sayisi+1, kapandi_mi=0, ek=COALESCE(?, ek)
                   WHERE uid=?""",
                (simdi, _iso(job.updated_at), job.content_hash, aciklama,
                 job.title, job.title_key, job.url,
                 json.dumps(job.locations, ensure_ascii=False), job.department,
                 _iso(job.posted_at), _ek(job), job.uid),
            )

        self.db.execute(
            "INSERT OR REPLACE INTO sightings(uid,run_id,seen_at,content_hash,updated_at) VALUES(?,?,?,?,?)",
            (job.uid, run_id, simdi, job.content_hash, _iso(job.updated_at)),
        )
        return sinyal

    def kapananlari_isaretle(self, run_id: int, board_tokenlar: list[str]) -> int:
        """Bu koşuda taranan panolarda artık görünmeyen ilanları kapandı say.
        (Yeniden yayım tespitinin diğer yarısı.)"""
        if not board_tokenlar:
            return 0
        q = ",".join("?" * len(board_tokenlar))
        c = self.db.execute(
            f"""UPDATE jobs SET kapandi_mi=1
                WHERE board_token IN ({q}) AND kapandi_mi=0
                  AND uid NOT IN (SELECT uid FROM sightings WHERE run_id=?)""",
            (*board_tokenlar, run_id),
        )
        self.db.commit()
        return c.rowcount

    # ---------- okuma ----------
    def yeniden_yayim_sayisi(self, job: Job) -> int:
        """Aynı başlık daha önce BAŞKA kimlikle kaç kez yayımlanıp kapandı?
        >0 ise ilan sürekli döndürülüyor demektir."""
        r = self.db.execute(
            "SELECT COUNT(*) n FROM jobs WHERE title_key=? AND uid<>? AND kapandi_mi=1",
            (job.title_key, job.uid),
        ).fetchone()
        return r["n"]

    def sirket_ilan_sayisi(self, board_token: str) -> int:
        r = self.db.execute(
            "SELECT COUNT(*) n FROM jobs WHERE board_token=? AND kapandi_mi=0", (board_token,)
        ).fetchone()
        return r["n"]

    def istatistik(self) -> dict:
        g = lambda q: self.db.execute(q).fetchone()[0]
        return {
            "ilan": g("SELECT COUNT(*) FROM jobs"),
            "acik": g("SELECT COUNT(*) FROM jobs WHERE kapandi_mi=0"),
            "kapali": g("SELECT COUNT(*) FROM jobs WHERE kapandi_mi=1"),
            "kosu": g("SELECT COUNT(*) FROM runs"),
            "sirket": g("SELECT COUNT(DISTINCT board_token) FROM jobs"),
        }

    def detay_yaz(self, job: Job) -> None:
        """İkinci aşamada çekilen ilan metnini (ve detaydan gelen alanları) saklar.
        Eskiden yazılmıyordu: her tarama aynı ilanın metnini panodan YENİDEN istiyordu."""
        self.db.execute("UPDATE jobs SET description=?, title=?, company=?, locations=?, ek=? "
                        "WHERE uid=?",
                        (job.description, job.title, job.company,
                         json.dumps(job.locations, ensure_ascii=False), _ek(job), job.uid))

    def son_pano_ilanlari(self, kaynaklar: list[str], saat: float,
                          haric: set[str]) -> list[Job]:
        """Son `saat` içinde görülmüş Türk pano ilanları (bu taramada gelmeyenler).

        NEDEN: pano engel verdiğinde ya da istek bütçesi dolduğunda tarama o panodan HİÇ
        ilan alamıyordu. ÖLÇÜLDÜ (2026-10-11): bir CV'nin taraması kariyer.net engelini
        tetikledi; 20 dakika sonraki ikinci CV'nin taramasında 463 kariyer.net ilanının
        hiçbiri yoktu ve kısa liste yalnız alakasız yabancı ilanlardan oluştu. Bu ilanlar
        gerçek ve yeni (son görülme zamanı kartta yazar); kapanmış olabilecekleri için
        süre kısa tutulur."""
        from datetime import timedelta
        if not kaynaklar:
            return []
        sinir = (datetime.now(timezone.utc) - timedelta(hours=saat)).isoformat()
        q = ",".join("?" * len(kaynaklar))
        cikti: list[Job] = []
        for r in self.db.execute(
                f"SELECT * FROM jobs WHERE source IN ({q}) AND last_seen>=? AND kapandi_mi=0",
                (*kaynaklar, sinir)):
            if r["uid"] in haric:
                continue
            ek = json.loads(r["ek"] or "{}")
            j = Job(source=r["source"], company=r["company"], board_token=r["board_token"],
                    native_id=r["native_id"], title=r["title"], url=r["url"] or "",
                    locations=json.loads(r["locations"] or "[]"),
                    description=r["description"] or "", department=r["department"] or "",
                    employment_type=ek.get("employment_type", ""),
                    remote_flag=ek.get("remote_flag"),
                    posted_at=_tarih(r["posted_at"]), updated_at=_tarih(r["updated_at"]),
                    raw={k: v for k, v in ek.items() if k not in ("employment_type",
                                                                  "remote_flag")})
            j.raw["detay_cekildi"] = bool(j.description)
            j.raw["son_gorulme"] = r["last_seen"]
            cikti.append(j)
        return cikti

    def commit(self) -> None:
        self.db.commit()

    def close(self) -> None:
        self.db.commit()
        self.db.close()
