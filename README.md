# is-basvuru-bot

CV'nizi alır, şirketlerin **herkese açık ilan API'lerinden** iş ilanı toplar, CV'nize
göre puanlar, **hayalet ilanları** ayıklar ve gerekçeli bir kısa liste çıkarır.

Kişiye özel değildir: motor tamamen `config/profile.yaml` güdümlüdür, kendi CV'nizle
çalışır. Profil dosyasını CV'nizden otomatik üretebilirsiniz.

```bash
git clone https://github.com/berketez/is-basvuru-botu.git
cd is-basvuru-botu
pip install requests pyyaml rich pypdf flask
python -m isbot panel
```

## Neden scraping / bot yok

Bu araç LinkedIn, Kariyer.net gibi platformlara **otomatik istek atmaz** ve bot
korumalarını atlatmaya çalışmaz. Sebebi pratik: o platformlarda oturum açmış bir hesapla
otomasyon yapmak hesabın askıya alınmasıyla sonuçlanır ve iş arayan biri için bu
kaybedilecek en pahalı şeydir.

Onun yerine **ön kapıdan** girer:

- **İlanlar çoğunlukla platformlara ait değildir.** Şirket Greenhouse/Lever/Ashby/Workable
  kullanıyorsa, ilan o sistemin **kimlik doğrulaması istemeyen, herkese açık JSON ucunda**
  durur. Atlatılacak koruma yoktur; o uçlar okunmak için vardır. Üstelik scraping'den
  iyidir: yapılandırılmış veri, HTML değişince kırılmaz.
- **Platforma özel ilanlar için** platformun kendi **iş alarmı e-postaları** kullanılır
  (kullanıcı alarmı kurar, platform ilanı kendisi gönderir, araç kullanıcının kendi gelen
  kutusunu okur). *Henüz yazılmadı — yol haritasında.*
- **Başvurunun kendisi** API ile mümkün değildir; Greenhouse'un başvuru ucu işverenin
  anahtarını ister. Dolayısıyla başvuru, formu doldurup **son "gönder" tıklamasını
  kullanıcıya bırakarak** yapılır. *Henüz yazılmadı — yol haritasında.*

## Kurulum

### Seçenek A — hazır uygulama (Python kurmak gerekmez)

macOS'ta `./kur.sh` bir kez koşturulur; uygulama `~/Applications/IsBasvuruBotu.app`
altına kurulur (derleme çıktısı silinir, sistemde tek kopya kalır). Sonra çift tıkla:
yerel sunucu açılır, tarayıcı kendiliğinden gelir; CV'yi sürükler, **Tara**'ya
basarsın. Terminal görmezsin.

- Veriler `~/is-basvuru-bot/` altında tutulur (profil, veritabanı, çıktılar).
- Sunucu **yalnızca 127.0.0.1**'e bağlanır; ağdaki başka makineler erişemez.
- CV makineden hiç çıkmaz.
- **Kapatmak:** Dock simgesine sağ tık → Çık. Sunucu da kapanır.
- Zaten açıkken simgeye tıklamak ikinci sunucu başlatmaz, panel sekmesini geri açar.
- **Bir şey ters giderse:** Finder'dan açılan uygulamanın terminal çıktısı yoktur;
  her şey `~/Library/Logs/IsBasvuruBotu.log` dosyasına yazılır. Önce oraya bak.

Windows'ta ya da elle paketlemek için:

```bash
pip install pyinstaller
pyinstaller --noconfirm isbot-panel.spec
# macOS -> dist/IsBasvuruBotu.app     Windows -> dist/IsBasvuruBotu/IsBasvuruBotu.exe
```

macOS notu: paket ad-hoc imzalanır. Başka bir makineye kopyalarsan Gatekeeper uyarır;
kullanıcı sağ tık → Aç demeli. Sorunsuz dağıtım için Apple geliştirici sertifikası +
notarization gerekir (yıllık ücretli). `com.apple.provenance` niteliği yüzünden
`codesign --deep` bazı sistemlerde hata verir; uygulamanın lokal çalışmasını etkilemez.

### Seçenek B — kaynaktan (geliştirme)

```bash
pip install requests pyyaml rich pypdf flask
python -m isbot panel      # web paneli
```

## Kullanım (komut satırı)

```bash
# 1) CV'nizden profil taslağı üretin (PDF / TeX / DOCX / MD / TXT)
python -m isbot cv-import ~/cv.pdf -o config/profile.local.yaml

# 2) Taslağı gözden geçirin — özellikle: calisma_izni, zorunlu_konum_kosulu, max_kidem
#    (bunlar CV'den güvenilir biçimde çıkarılamaz)

# 3) Tarayın
python -m isbot tara --min-puan 25 -n 25

# Yardımcılar
python -m isbot dogrula greenhouse anthropic   # bir ATS anahtarını sına
python -m isbot durum                          # veritabanı istatistikleri
python -m isbot panel                          # web panelini aç
```

Çıktı: terminalde tablo + `out/ilanlar-<tarih>.md` içinde her ilan için gerekçe
(hangi yetenekler eşleşti, neyi tutturamıyorsunuz, konum neden uygun, ilan kaç günlük).

## Hayalet ilan tespiti

Hayalet/havuz ilanı ("talent pool", yıllardır açık duran kadro) tespiti iki grup
sinyale dayanır. İlk koşuda yalnızca birinci grup çalışır; araç düzenli koştukça
veritabanı büyür ve tespit keskinleşir.

**Anında:** ilan yaşı (>1 yıl, >2 yıl, >3 yıl kademeleri) · "talent pool / expression of
interest / genel başvuru" kalıpları · "ileride açılacak pozisyonlar için" ifadeleri ·
konum enflasyonu · yayın tarihinin hiç verilmemesi

**Zamanla (≥2 koşu):** *sahte tazeleme* — güncelleme tarihi ilerlemiş ama ilan metni
harfi harfine aynı · *yeniden yayım* — aynı başlık kapanıp yeni kimlikle açılmış ·
hiç kapanmama

## Arayüz

![panel](docs/panel-genel.png)

İş sitelerinin standart filtreleri var: arama, **çalışma şekli** (uzaktan/hibrit/ofis),
**istihdam türü** (tam zamanlı/yarı zamanlı/sözleşmeli/staj), yayın tarihi, en az
uygunluk puanı, şirket ve **hayalet ilan** bandı. Bir karta tıklayınca gerekçe açılır:
hangi yetenekler eşleşti, neyi tutturamıyorsun, konum neden uygun, tazelik sinyalleri.

Çalışma şekli ve istihdam türü ATS'ler bunu tutarsız verdiği için türetilir
(Greenhouse hiç vermiyor). Çıkarılamıyorsa **"belirtilmemiş"** yazar — uydurulmaz.

**Nereden çalışabilirsin** adımı CV'den çıkarılamaz, elle işaretlenir: Türkiye, uzaktan
(global), uzaktan (EMEA) ve **çalışma izninin olduğu ülkeler**. Ülke listesi sabit
değildir; motorun tanıdığı ülkeler `/api/ulkeler` ucundan gelir ve arayüzde aranıp
eklenir (İsviçre, Kanada, Hollanda…). Ülke eklemek için tek yer düzenlenir:
`isbot/scoring.py` içindeki `ULKELER` kataloğu — arayüz kendiliğinden güncellenir.

Türkiye işaretliyken ülke içindeki ilanların **hepsi** gelir: yerinde, hibrit, uzaktan.
Hangisi olduğu kartın üstünde etiketle yazar; yalnız birini istiyorsan **çalışma şekli**
filtresi kullanılır. Konum satırı yalnız şehir içeriyorsa ("Zurich", "Berlin") ülke
şehirden çözülür; çözülemeyen kapsam **uygun sayılmaz** (fail-closed).

## Kaynaklar

**Şirket başına** (anahtar = ATS'teki şirket token'ı): Greenhouse, Lever, Ashby,
Workable, SmartRecruiters.

**Şirketler-arası** (anahtar = arama sorgusu ya da tüm akış): Remotive, RemoteOK,
**Arbeitnow** (Almanya/AB, tüm sektörler), **The Muse** (ABD, tüm sektörler, kıdem
bilgisini kendisi veriyor), **Himalayas** (son geçerlilik tarihi + maaş), **Jobicy**,
**We Work Remotely**.

**Türkiye** (HTML, robots.txt'ye uyumlu, iki aşamalı): **Kariyer.net**, **Eleman.net**. Bunlar önemli çünkü
Greenhouse/Lever/Ashby'nin şirketler-arası indeksi yoktur — her şirketi tek tek eklemek
gerekir. Toplayıcılar tek istekte yüzlerce şirketi tarar. Remotive'in
`candidate_required_location` alanı ("Worldwide", "USA Only") ilanın kendi beyanıdır;
konumu metinden çıkarmaktan çok daha güvenilir.

## Şirket listesi

`config/companies.yaml` — 74 şirket, anahtarların tamamı canlı doğrulanmış.

**Yeni şirket eklerken kimliği teyit edin.** Anahtar tahmini sahte eşleşme üretir:
doğrulama sırasında `greenhouse/peak` Teksas'ta bir fizik tedavi kliniği,
`greenhouse/insider` ABD'li bir haber sitesi çıktı. `python -m isbot dogrula <kaynak>
<anahtar>` komutu ilan konumlarını da basar; oradan teyit edin.

Anahtarı bulmak: şirketin kariyer sayfası URL'sinin son kısmı —
`job-boards.greenhouse.io/ANAHTAR`, `jobs.lever.co/ANAHTAR`,
`jobs.ashbyhq.com/ANAHTAR`, `apply.workable.com/ANAHTAR`.

### Türkiye kapsamı hakkında dürüst not

Türk şirketlerinin büyük kısmı kariyer.net veya kendi sistemleri üzerinden ilan verir ve
herkese açık API'leri yoktur. Yalnızca uluslararası ölçekte çalışanlar Lever/Greenhouse
kullanır (Trendyol, Dream Games, Peak Games, iyzico, Midas, Picus, Intenseye doğrulandı).
Türkiye kapsamının asıl çözümü yol haritasındaki **e-posta alarmı kanalıdır**.

## Türk panoları ve nezaket kuralları

kariyer.net ve eleman.net'ten ilan okunur. Bu panolarda herkese açık API yoktur,
dolayısıyla HTML okunur — ama yapılan şey **nazik tarama**dır, atlatma değil:

- `robots.txt` her koşumda okunur ve **programatik uygulanır**. kariyer.net'te
  `/filtre/*`, `/servisler/`, `/ozgecmis/*` yasaktır; o yollara hiç gidilmez.
- İstek aralığı **4 saniye** ve zaman damgası **diske yazılır**. Süreç-içi sayaç
  yetmez: ard arda çalışan betikler sayacı sıfırlar, gerçek hız yükselir.
  (Ölçüldü: geliştirme sırasında bu yüzden 403 yendi.)
- 403/429 alınırsa o panoya **6 saat dokunulmaz**. Israr engeli uzatır.
- CAPTCHA çözme, parmak izi sahteciliği, IP değiştirerek engeli dolanma **yoktur**.
  Engel yendiyse doğru davranış beklemektir; VPN ile devam etmek, sitenin koyduğu
  sınırı kasten dolanmak olur ve aracı kullanan herkesi riske atar.

### Geliştirirken canlı siteye istek atma

Ayrıştırıcı üzerinde çalışırken kayıtlı sayfa örnekleri kullanılır:

```bash
ISBOT_ORNEK=kaydet python -m isbot tara    # çekilen sayfaları tests/ornekler/ altına yaz
ISBOT_ORNEK=oku    python tests/test_regresyon.py   # ağa hiç çıkmadan ayrıştırıcıyı sına
```

Regresyon testi bu modu kullanır ve soketi kapatarak ağa çıkılmadığını doğrular.

## Benchmark

```bash
tests/hepsi.sh                       # hepsi: regresyon + benchmark + kesinlik
python tests/benchmark.py --yenile   # havuzu yeniden çek
```

Üç test takımı var:

| Takım | Ne ölçer | Ağ |
|---|---|---|
| `test_regresyon.py` | Düzeltilen 26 hatanın geri gelmemesi (101 kontrol) | yok |
| `benchmark.py` | 15 CV'nin ayrıştırılması + eleme/konum/negatif kontrol (105 kontrol) | önbellek |
| `kesinlik.py` | **Her CV'nin ilk 10 sonucunda alan dışı ilan sayısı — hedef 0** | önbellek |

`tests/ornekler/` (Türk panolarından kaydedilmiş sayfa örnekleri) **depoda yoktur** —
üçüncü tarafa ait içerik, yerelde kalır. O örneklere bağlı beş kontrol dosyalar yoksa
sessizce atlanır, kalan 96 kontrol ağa hiç çıkmadan koşar.

15 sahte CV (farklı sektör ve seviye) iki katmanda sınanır. Beklentiler
`tests/beklenen.yaml` içinde **elle** yazılmıştır — motorun çıktısına bakılarak değil,
CV'ler okunarak. Döngüsel doğrulamayı önlemek için sıra budur.

**A) Yapısal** — deneyim yılı (±1,5 tolerans), kıdem tavanı, tespit edilmesi gereken
yetenekler, tespit edilmemesi gereken yetenekler (yanlış pozitif). Son durum: **15/15**.

**B) Alaka** — tek ilan havuzu 15 profile karşı puanlanır; ilk 5 sonuçta kendi eleme
kalıbına uyan başlık geçmiş mi (sızıntı), konum uygunluğu bozulmuş mu, alan anahtar
kelimeleri tutuyor mu. İki de **negatif kontrol** var: makine mühendisi yeni mezun bu
yazılım havuzundan neredeyse hiç sonuç almamalı (1 aday alıyor).

Son koşu: `docs/benchmark-sonuc.txt`.

### Türk panoları ve nezaket kuralları

kariyer.net ve eleman.net'ten ilan okunur. Bu panolarda herkese açık API yoktur,
dolayısıyla HTML okunur — ama yapılan şey **nazik tarama**dır, atlatma değil:

- `robots.txt` her koşumda okunur ve **programatik uygulanır**. kariyer.net'te
  `/filtre/*`, `/servisler/`, `/ozgecmis/*` yasaktır; o yollara hiç gidilmez.
- İstek aralığı **4 saniye** ve zaman damgası **diske yazılır**. Süreç-içi sayaç
  yetmez: ard arda çalışan betikler sayacı sıfırlar, gerçek hız yükselir.
  (Ölçüldü: geliştirme sırasında bu yüzden 403 yendi.)
- 403/429 alınırsa o panoya **6 saat dokunulmaz**. Israr engeli uzatır.
- CAPTCHA çözme, parmak izi sahteciliği, IP değiştirerek engeli dolanma **yoktur**.
  Engel yendiyse doğru davranış beklemektir; VPN ile devam etmek, sitenin koyduğu
  sınırı kasten dolanmak olur ve aracı kullanan herkesi riske atar.

### Geliştirirken canlı siteye istek atma

Ayrıştırıcı üzerinde çalışırken kayıtlı sayfa örnekleri kullanılır:

```bash
ISBOT_ORNEK=kaydet python -m isbot tara    # çekilen sayfaları tests/ornekler/ altına yaz
ISBOT_ORNEK=oku    python tests/test_regresyon.py   # ağa hiç çıkmadan ayrıştırıcıyı sına
```

Regresyon testi bu modu kullanır ve soketi kapatarak ağa çıkılmadığını doğrular.

## Benchmark'ın ölçmediği şey

"Alan tutması" ham anahtar kelime eşleşmesidir; bir frontend geliştiricisine gelen
"Full-Stack Engineer" ilanı 0/5 sayılır ama makul bir eşleşmedir. Yani alaka sayıları
kaliteyi bir miktar olduğundan kötü gösterir. Havuzda o alan hiç yoksa (mobil, oyun)
motor komşu alandan sonuç getirir ve bunları **"alan dışı"** diye etiketleyip puanını
%45 kırar — böylece alan içi eşleşmelerin altına sıralanır.

## Yol haritası

- [ ] Lokal web paneli + `.app`/`.exe` paketleme (Python kurulumu gerekmesin)
- [ ] İş alarmı e-postalarından ilan okuma (LinkedIn / Kariyer.net kapsamı)
- [ ] Başvuru hazırlama: ilana özel CV + ön yazı, formu doldur, gönderimi kullanıcıya bırak
- [x] ~~15 CV'lik yapısal benchmark~~ (tests/benchmark.py, 105 kontrol)
- [ ] ESCO taksonomisi + serbest terim çıkarımı (yazılım dışı meslek kapsamı)

## Paket bütünlüğü

Uygulama açılışta zorunlu veri dosyalarını denetler; `GET /api/saglik` sonucu verir.
Derleme sırasında da `assert` ile kontrol edilir — eksik veri dosyasıyla paket
üretilemez. (Bir sürümde `roller.yaml` pakete girmemiş ve rol aileleri sessizce
çalışmamıştı; bu denetim onun tekrarını engelliyor.)

## Platform

macOS, Linux, Windows. Tek platform bağımlısı parça PDF okumadır: `pdftotext` varsa
kullanılır, yoksa `pypdf`'e düşer (ikisi aynı sonucu verir, sınandı).
