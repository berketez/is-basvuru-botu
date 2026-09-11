"""Komut satırı arayüzü."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .sources import KAYNAKLAR

k = Console()


def _tara(a) -> int:
    from .pipeline import tara
    if not Path(a.profil).exists():
        k.print(f"[red]Profil yok:[/] {a.profil}\n"
                f"Önce üret:  [bold]python -m isbot cv-import <CV dosyan> -o {a.profil}[/]")
        return 1

    k.print(f"[dim]profil:[/] {a.profil}   [dim]eşik:[/] {a.min_puan} puan, hayalet ≥{a.hayalet_esigi}")
    with k.status("[bold]ilanlar çekiliyor…") as st:
        def ilerle(ad, n):
            st.update(f"[bold]{ad}[/] — {n} ilan")
        r = tara(a.profil, a.sirketler, a.db, min_puan=a.min_puan,
                 hayalet_esigi=a.hayalet_esigi, ilerleme=ilerle)

    k.print(f"\n[bold]{r.cekilen}[/] ilan tarandı → "
            f"[red]{r.elenen}[/] filtrede elendi, "
            f"[yellow]{r.hayalet_elenen}[/] hayalet elendi, "
            f"[green]{len(r.sonuclar)}[/] aday kaldı"
            + (f", [dim]{r.kapanan} ilan kapanmış[/]" if r.kapanan else ""))
    for h in r.hatalar[:6]:
        k.print(f"  [dim red]! {h}[/]")

    if not r.sonuclar:
        k.print("\n[yellow]Eşiği geçen ilan yok.[/] --min-puan düşür veya profili gevşet.")
        return 0

    # ŞİRKET ÇEŞİTLİLİĞİ: tek şirket kısa listeyi işgal etmesin.
    # (ölçüldü: Canonical ilk 20 satırın 20'sini almıştı — 73 şirketlik havuzda işe yaramaz)
    gosterilen, sayac = [], {}
    for s_ in r.sonuclar:
        n = sayac.get(s_.job.company, 0)
        if n >= a.sirket_basi:
            continue
        sayac[s_.job.company] = n + 1
        gosterilen.append(s_)

    t = Table(show_lines=False, header_style="bold")
    for s, j in [("#", "right"), ("Puan", "right"), ("Şirket", "left"), ("Pozisyon", "left"),
                 ("Konum", "left"), ("Yaş", "right"), ("Hayalet", "left")]:
        t.add_column(s, justify=j, overflow="fold")
    for i, s in enumerate(gosterilen[:a.adet], 1):
        renk = "green" if s.nihai >= 60 else ("yellow" if s.nihai >= 40 else "white")
        yas = f"{s.hayalet.yas_gun:.0f}g" if s.hayalet.yas_gun is not None else "?"
        hb = {"taze": "[green]taze[/]", "normal": "[dim]normal[/]",
              "şüpheli": "[yellow]şüpheli[/]", "hayalet": "[red]hayalet[/]"}[s.hayalet.bant]
        t.add_row(str(i), f"[{renk}]{s.nihai}[/]", s.job.company, s.job.title[:52],
                  (s.puan.konum_durumu or "")[:22], yas, hb)
    k.print(t)

    hedef = Path(a.cikti or f"out/ilanlar-{date.today().isoformat()}.md")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(_markdown(r, a.adet, gosterilen), encoding="utf-8")
    from .pipeline import json_yaz
    jyol = json_yaz(r)
    k.print(f"\n[dim]gerekçeli tam rapor →[/] [bold]{hedef}[/]")
    k.print(f"[dim]arayüz verisi      →[/] [bold]{jyol}[/]")
    return 0


def _markdown(r, adet: int, gosterilen=None) -> str:
    sat = [f"# İlan raporu — {date.today().isoformat()}", "",
           f"{r.cekilen} ilan tarandı · {r.elenen} filtrede elendi · "
           f"{r.hayalet_elenen} hayalet elendi · **{len(r.sonuclar)} aday**", ""]
    for i, s in enumerate((gosterilen or r.sonuclar)[:adet], 1):
        j, p, h = s.job, s.puan, s.hayalet
        yas = f"{h.yas_gun:.0f} gün" if h.yas_gun is not None else "bilinmiyor"
        sat += [f"## {i}. {j.title} — {j.company}  `{s.nihai}`", "",
                f"- **Bağlantı:** {j.url}",
                f"- **Konum:** {p.konum_durumu} · {', '.join(j.locations[:4]) or '—'}",
                f"- **Yaş:** {yas} · **tazelik:** {h.bant} (risk {h.risk:.2f}, kanıt: {h.kanit_gucu})",
                f"- **Rol eşleşmesi:** {p.rol_ailesi} ({p.rol_puan:.0f}/40) · "
                f"**yetenek:** {p.yetenek_puan:.0f}/45 · **kıdem:** {p.kidem}"
                + (f" · **istenen deneyim:** {p.istenen_yil} yıl" if p.istenen_yil else ""),
                f"- **Eşleşen yetenekler:** {', '.join(p.eslesen_yetenekler[:14]) or '—'}"]
        if p.eksik_yetenekler:
            sat.append(f"- **eksik:** {', '.join(p.eksik_yetenekler[:8])}")
        for u in p.uyarilar:
            sat.append(f"- **uyarı:** {u}")
        for g in h.gerekceler:
            etiket = "taze" if "yeni yayımlanmış" in g else "hayalet"
            sat.append(f"- **{etiket}:** {g}")
        sat.append("")
    return "\n".join(sat)


def _cv_import(a) -> int:
    from .cv_import import profil_uret, yaz
    try:
        p = profil_uret(a.cv)
    except Exception as e:
        k.print(f"[red]CV okunamadı:[/] {e}")
        return 1
    h = yaz(p, a.cikti)
    g, z = p["yetenekler"]["guclu"], p["yetenekler"]["zayif"]
    k.print(f"[green]Profil üretildi:[/] [bold]{h}[/]")
    k.print(f"  deneyim: [bold]{p['kimlik']['deneyim_yil']} yıl[/] "
            f"(gönüllü/kulüp dahil {p['kimlik']['_deneyim_toplam_gonullu_dahil']}) "
            f"— {p['kimlik']['_deneyim_kaynagi']}")
    k.print(f"  kıdem tavanı: [bold]{p['sert_filtreler']['max_kidem']}[/] · "
            f"{len(g)} güçlü, {len(z)} zayıf yetenek")
    k.print(f"  güçlü: [dim]{', '.join(list(g)[:12])}…[/]")
    k.print("\n[yellow]TASLAKTIR.[/] Şunları elle kontrol et: "
            "[bold]calisma_izni, zorunlu_konum_kosulu, max_kidem, deneyim_yil[/]")
    return 0


def _dogrula(a) -> int:
    if a.kaynak not in KAYNAKLAR:
        k.print(f"[red]Bilinmeyen kaynak.[/] Seçenekler: {', '.join(KAYNAKLAR)}")
        return 1
    try:
        js = KAYNAKLAR[a.kaynak]().cek(a.anahtar, a.anahtar)
    except Exception as e:
        k.print(f"[red]Geçersiz:[/] {type(e).__name__}: {str(e)[:90]}")
        return 1
    k.print(f"[green]Geçerli:[/] {a.kaynak}/{a.anahtar} → [bold]{len(js)}[/] ilan")
    k.print("[yellow]Kimliği TEYİT ET:[/] token tahmini sahte eşleşme üretir "
            "(ör. 'greenhouse/peak' → Teksas'ta fizik tedavi kliniği).")
    for j in js[:6]:
        yas = f"{j.age_days:.0f}g" if j.age_days is not None else "?"
        k.print(f"   [dim]{yas:>6}[/]  {j.title[:48]:50} [cyan]{', '.join(j.locations[:2])}[/]")
    return 0


def _panel(a) -> int:
    try:
        from .server import calistir
    except ImportError as e:
        k.print(f"[red]Flask gerekli:[/] pip install flask   ({e})")
        return 1
    calistir(port=a.port, tarayici_ac=not a.tarayici_acma)
    return 0


def _durum(a) -> int:
    from .store import Depo
    d = Depo(a.db)
    s = d.istatistik()
    d.close()
    k.print(f"[bold]Veritabanı:[/] {a.db}")
    k.print(f"  {s['ilan']} ilan ({s['acik']} açık, {s['kapali']} kapanmış) · "
            f"{s['sirket']} şirket · {s['kosu']} koşu")
    if s["kosu"] < 2:
        k.print("[yellow]  Not:[/] hayalet tespitinin zamana dayalı sinyalleri (sahte tazeleme,\n"
                "  yeniden yayım) en az 2 koşu ister. Botu düzenli çalıştırdıkça keskinleşir.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="isbot", description="İş ilanı keşif ve eşleştirme botu (açık ATS uçları üzerinden)")
    alt = ap.add_subparsers(dest="komut", required=True)

    t = alt.add_parser("tara", help="ilanları çek, puanla, kısa liste çıkar")
    t.add_argument("--profil", default="config/profile.local.yaml")
    t.add_argument("--sirketler", default="config/companies.yaml")
    t.add_argument("--db", default="data/jobs.db")
    t.add_argument("--min-puan", type=float, default=25.0, dest="min_puan")
    t.add_argument("--hayalet-esigi", type=float, default=0.70, dest="hayalet_esigi")
    t.add_argument("-n", "--adet", type=int, default=25)
    t.add_argument("-o", "--cikti", default=None)
    t.add_argument("--sirket-basi", type=int, default=3, dest="sirket_basi",
                   help="kısa listede tek şirketten en fazla kaç ilan (varsayılan 3)")
    t.set_defaults(fn=_tara)

    c = alt.add_parser("cv-import", help="CV'den profil taslağı üret (PDF/TeX/DOCX/MD/TXT)")
    c.add_argument("cv")
    c.add_argument("-o", "--cikti", default="config/profile.local.yaml")
    c.set_defaults(fn=_cv_import)

    d = alt.add_parser("dogrula", help="bir ATS anahtarının geçerliliğini sına")
    d.add_argument("kaynak", help=" | ".join(KAYNAKLAR))
    d.add_argument("anahtar")
    d.set_defaults(fn=_dogrula)

    w = alt.add_parser("panel", help="lokal web panelini başlat (tarayıcıda açılır)")
    w.add_argument("--port", type=int, default=8733)
    w.add_argument("--tarayici-acma", action="store_true", dest="tarayici_acma",
                   help="tarayıcıyı kendiliğinden açma")
    w.set_defaults(fn=_panel)

    s = alt.add_parser("durum", help="veritabanı istatistikleri")
    s.add_argument("--db", default="data/jobs.db")
    s.set_defaults(fn=_durum)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
