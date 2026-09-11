# Yol Planı — altı sınırın çözümü

Bu belge **plandır, uygulama değildir**. Her madde için: kök sebep, seçenekler,
seçilen yol, **nasıl doğrulanacağı** ve emek tahmini.

Yazarken canlı doğrulanan şeyler bölüm sonlarında "ölçüldü" diye işaretlidir;
doğrulanmamış varsayımlar "varsayım" diye. İkisini karıştırmamak önemli, çünkü
bu projede bugüne kadarki hataların çoğu doğrulanmamış varsayımdan çıktı.

Mevcut durum (11 Eyl 2026): 73 şirket + 2 toplayıcı, 10.875 ilan / 20 saniye,
27/27 regresyon + 105/105 benchmark kontrolü geçiyor.

---

## 1. Kapsam

**Kök sebep.** İlanlar parçalı silolarda duruyor ve her silonun erişim biçimi farklı.
Bugün yalnızca 5 ATS sağlayıcısının şirket-başına uçlarını ve 2 uzaktan toplayıcıyı
okuyoruz. Bu yüzden havuz yazılım+uzaktan ağırlıklı; mobil/oyun/frontend'de ilan yok,
yazılım dışı meslekler hiç yok.

**Ölçülen.** iOS geliştiricisi 4 aday, oyun geliştiricisi 22 aday alıyor, hepsi alan dışı.
6.622 tekil ilanın yalnızca ~166'sı Türkiye'den erişilebilir konumda.

### 1a. JSON-LD genel tarayıcı — en yüksek getirili tek iş

Şirket kariyer sayfalarının büyük kısmı, Google for Jobs için sayfaya
`schema.org/JobPosting` yapılandırılmış verisi gömüyor (`<script type="application/ld+json">`).
Bu, **sağlayıcıdan bağımsız** tek bir ayrıştırıcıyla binlerce kariyer sayfasını okumak
demek — her ATS için ayrı bağlayıcı yazmaya gerek kalmadan.

- Girdi: şirket alan adı listesi. `/careers`, `/kariyer`, `/jobs`, `/is-ilanlari` denenir.
- Sayfadaki JSON-LD `JobPosting` nesneleri okunur: `title`, `datePosted`,
  `validThrough`, `jobLocation`, `employmentType`, `description`, `hiringOrganization`.
- `datePosted` + `validThrough` **hayalet tespitine doğrudan girdi** (madde 4).
- `robots.txt` programatik okunur (`urllib.robotparser`), izin verilmeyen yol atlanır.

**Doğrulama ölçütü:** 50 rastgele şirket alan adında, en az %40'ında JSON-LD
`JobPosting` bulunabilmeli; bulunanların %95'inde başlık + tarih alanı dolu olmalı.
Bu oran tutmazsa yaklaşım terk edilir, yerine 1b'ye ağırlık verilir.

**Emek:** 1-2 gün. **Risk:** düşük (salt okuma, robots.txt'ye uyumlu).

### 1b. Büyük kurumsal ATS'ler — Workday, SuccessFactors, Oracle ORC

Türkiye'deki ve dünyadaki büyük işverenlerin çoğu bu üçünden birini kullanıyor.
Bugünkü 5 sağlayıcı startup/scale-up ağırlıklı; kurumsal taraf tamamen kör.

- **Workday:** `POST https://{kiracı}.wd{N}.myworkdayjobs.com/wday/cxs/{kiracı}/{site}/jobs`
  Ölçüldü: uç **yaşıyor** (tahmin ettiğim yükle **HTTP 422** döndü, 404 değil — yani
  uç var, yük şeması yanlış). Kiracı + site + veri merkezi (`wd1`/`wd3`/`wd5`…) üçlüsü
  şirketin kariyer URL'sinden çıkarılmalı; yük şeması deneyerek bulunmalı.
- **SAP SuccessFactors:** Koç, Sabancı, Turkcell gibi büyük Türk gruplarında yaygın.
- **Oracle Cloud HCM (ORC):** `.../hcmRestApi/resources/latest/recruitingCEJobRequisitions`
  — Türk bankaları ve büyük kurumlar.

**Doğrulama ölçütü:** her sağlayıcı için 3 gerçek şirkette ilan çekilebilmeli ve
**kimlik ilan konumlarından teyit edilmeli** (bkz. aşağıdaki "sahte eşleşme" dersi).

**Emek:** sağlayıcı başına 1 gün (şema keşfi dahil). **Risk:** orta — yük şemaları
belgesiz, sürüm farkları var.

### 1c. Kariyer.net ve Türk panoları

**Ölçüldü (11 Eyl 2026):** `kariyer.net/robots.txt` ilan sayfalarını yasaklamıyor.
Yasakladıkları: özgeçmişler (`/ozgecmis/*`, `/profil`, `/hesabim`), başvuru akışı
(`/basvuru-tamamlama`, `/basvuru-onay`), giriş sayfaları, arama filtresi (`/filtre/*`)
ve kendi iç servisleri (`/servisler/`, `/Services/`). `Crawl-delay` direktifi yok.
Sitemap'lerini açıkça ilan ediyorlar (9 alt harita; `sitemaps/5` içinde 21.677
"şehir+pozisyon" kategori sayfası). Düz anonim istekle bir kategori sayfası
**HTTP 200, 0,56 saniye, 53 ilan bağlantısı** döndü; bot duvarı yok.

**Seçilen yol — nazik tarama, atlatma değil:**
- `robots.txt` her koşuda yeniden okunur ve programatik uygulanır; `/filtre/*` ve
  `/servisler/` **asla** çağrılmaz.
- Sitemap'ten kategori sayfaları alınır; oradan ilan bağlantıları toplanır.
- İstek hızı: **en fazla 1 istek / 2 sn**, tek iş parçacığı, gece değil kullanıcı
  taraması sırasında. Gerçek `User-Agent` + iletişim URL'si.
- `ETag`/`Last-Modified` ile koşullu istek; değişmeyen sayfa yeniden indirilmez.
- 429/403 görülürse o pano **kalıcı olarak devre dışı** bırakılır ve kullanıcıya söylenir.

**Yapılmayacak:** CAPTCHA çözme, parmak izi sahteciliği, giriş yapmış hesabı sürme.
Gerekçe teknik: giriş yapmış hesapta saklanacak kimlik yok, ceza gecikmeli gelir ve
iş ararken hesabı kaybetmek aracın kazandıracağı her şeyi siler.

**Doğrulama ölçütü:** 1 haftalık sürekli koşumda 0 adet 429/403; çekilen ilanların
%95'inde başlık+şirket+konum dolu; aynı ilan iki koşuda aynı kimlikle eşleşiyor.

**Emek:** 2 gün. **Risk:** orta — site yapısı değişirse kırılır (ATS API'lerinin
aksine sözleşme yok). Bu yüzden kırıldığını anlayan bir sağlık kontrolü şart:
"ilan sayısı bir önceki koşunun %30'unun altına düştüyse ayrıştırıcı bozulmuş olabilir".

### 1d. Çok-şirketli toplayıcılar (ucuz genişleme)

Bugün Remotive + RemoteOK var. Eklenecekler ve neden:

| Kaynak | Neden | Sektör kapsamı |
|---|---|---|
| Adzuna API | ücretsiz katman, çok ülke, **tüm sektörler** | geniş |
| Arbeitnow API | AB odaklı, kimlik doğrulamasız | orta |
| Jobicy / Himalayas | uzaktan, kimlik doğrulamasız | teknoloji |
| WeWorkRemotely RSS | klasik RSS | teknoloji |
| EURES (AB resmî portalı) | resmî, çok ülke, tüm sektörler | geniş |
| İŞKUR açık veri | Türkiye resmî | geniş |

Bunlar **yazılım dışı meslek** sorununun (madde 2 ile birlikte) asıl çözümü:
sektör kapsamı ancak sektörleri içeren kaynaklardan gelir.

**Doğrulama ölçütü:** her kaynak için ilan sayısı, benzersizlik oranı (havuzdaki
diğer kaynaklarla çakışma) ve alan doluluk oranı ölçülür; çakışması %90'ın üstünde
olan kaynak eklenmez (değer katmıyor demektir).

**Emek:** kaynak başına 2-4 saat.

### 1e. `isbot kesfet` — şirket anahtarı keşif komutu

Bugün 73 anahtarı elle doğruladım ve **üç sahte eşleşme** çıktı: `greenhouse/peak`
Teksas'ta bir fizik tedavi kliniği, `greenhouse/insider` ABD'li haber sitesi,
`ashby/novo` başka bir şirket. Bu ders otomatikleştirilmeli.

- Girdi: şirket adı veya alan adı.
- Kariyer sayfası çekilir, ATS imzası aranır (bu tespit kodu zaten yazıldı).
- Anahtar bulununca ilan çekilir ve **kimlik ilan konumlarından teyit edilir**;
  şirket adı/konum beklenenle uyuşmuyorsa **reddedilir**, kullanıcıya gösterilir.
- Onaylanan anahtar `companies.yaml`'a eklenir.

**Doğrulama ölçütü:** bilinen 20 şirketten en az 15'inde doğru anahtar bulunmalı ve
kasten bozuk 5 anahtarın 5'i de reddedilmeli (yanlış pozitif = 0 hedefi).

**Emek:** 1 gün.

### 1f. E-posta alarmı kanalı

LinkedIn/Kariyer.net'e hiç dokunmadan o silolardaki ilanları görmenin yolu:
kullanıcı platformda iş alarmı kurar, platform ilanları **kendi rızasıyla** e-posta
atar, araç kullanıcının **kendi gelen kutusunu** okur.

- IMAP, **salt okuma**, uygulama şifresi (ana şifre değil), yalnız belirli
  göndericiler (`jobalerts-noreply@linkedin.com`, `bilgi@kariyer.net` vb.).
- Gönderici şablonu başına bir ayrıştırıcı; şablon değişirse sağlık kontrolü uyarır.
- Kimlik bilgisi **yalnızca yerel anahtarlıkta** (macOS Keychain / Windows Credential
  Manager), dosyada düz metin asla.

**Doğrulama ölçütü:** 2 hafta boyunca gelen alarm e-postalarının %90'ından en az bir
ilan çıkarılabilmeli ve çıkarılan ilanların URL'leri canlı olmalı.

**Emek:** 2-3 gün. **Risk:** kimlik bilgisi taşıma sorumluluğu getiriyor — bu yüzden
**varsayılan kapalı**, kullanıcı açıkça açmalı.

---

## 2. Yetenek sözlüğü

**Kök sebep.** Sözlük elle yazıldı: 138 kalem, yazılım/mühendislik odaklı. Bir alan
sözlükte yoksa tespit edilemiyor; kullanıcı "genel_yazılım" yedeğine düşüyor.

### 2a. ESCO'yu taban taksonomi yap

ESCO = AB'nin resmî beceri/meslek taksonomisi. ~13.900 beceri, ~3.000 meslek,
tüm sektörler, açık lisans, kimlik doğrulamasız API.

**Ölçüldü (11 Eyl 2026):**
- `GET https://ec.europa.eu/esco/api/search?text=python&language=en&type=skill` çalışıyor.
- Beceri kaydı **alternatif etiketler** veriyor: `Python (computer programming)` için
  `Python3000`, `Python prog`, `Python2`, `Python 3k`, `Py3K`. **Bu, eş anlam
  sorununun (madde 5) bedava ve açıklanabilir çözümü.**
- Almanca çalışıyor (başlık çevrili, alternatifler var).
- **Türkçe YOK.** `language=tr` istediğimde başlık İngilizce'ye düşüyor ve Türkçe
  alternatif etiket sayısı 0. Türkiye AB üyesi olmadığı için ESCO'da tam dil desteği yok.

**Sonuç — plan buna göre kuruluyor:**
- ESCO **İngilizce** taban taksonomi + eş anlam kaynağı olarak alınır (ilanların
  ezici çoğunluğu zaten İngilizce).
- **Türkçe için ESCO'ya güvenilmez.** Türkçe beceri etiketleri ayrı kurulur:
  (i) mevcut 138 kalemin Türkçe karşılıkları elle yazılır, (ii) Türkçe ilanlardan
  sık geçen terimler çıkarılıp elle onaylanır. Bu, ESCO'nun çözdüğünü iddia
  edemeyeceğimiz bir iştir; plan bunu açıkça ayrı kalem olarak tutuyor.

**Doğrulama ölçütü:** 15 CV'lik benchmark'a 10 yazılım-dışı CV eklenir (hukuk,
muhasebe, tasarım, hemşirelik, öğretmenlik, lojistik, satış, İK, pazarlama, şef).
Her biri için "olmalı" yetenek listesi elle yazılır; hedef: 10/10 CV'de en az 4
doğru yetenek tespiti, yanlış pozitif 0.

**Emek:** 2-3 gün (ESCO içe aktarma + eşleme) + 1 gün Türkçe katman.

### 2b. Sözlük dışı terimler için serbest çıkarım

Taksonomi ne kadar büyürse büyüsün kuyruk hep olacak. Bu yüzden ikinci katman:

- CV'nin "Yetenekler/Skills" bölümündeki virgülle ayrılmış öğeler, madde imli
  listeler ve büyük harfli teknoloji benzeri belirteçler **aday terim** sayılır.
- Bu terimler taksonomiye sorulmaz; doğrudan **ilan havuzunda aranır**.
- Ayırt ediciliği IDF ile ölçülür (bu mekanizma zaten var). Havuzun %40'ında geçen
  terim zaten puan taşımaz; hiç geçmeyen terim de taşımaz. Kalan orta bant değerlidir.

Bu katman sayesinde **bilinmeyen bir meslek bile** çalışır: eşleşme sinyali, CV ile
ilan metninin ortak nadir terimleridir; taksonomi yalnızca rol ailesi için gerekir.

**Doğrulama ölçütü:** taksonomiden tamamen silinmiş bir alanla (ör. tüm güvenlik
kalemleri çıkarılıp) pentester CV'si koşulur; serbest çıkarım sayesinde ilk 5'te en az
3 güvenlik ilanı gelmeli.

**Emek:** 1-2 gün.

### 2c. Rol ailelerini ESCO meslek ağacından türet

Bugün `roller.yaml` 15 aile ile elle yazıldı ve yalnız teknoloji alanlarını kapsıyor.
ESCO'nun meslek (occupation) ağacı, beceri→meslek bağlarını hazır veriyor.
Plan: kullanıcının becerileri ESCO becerilerine eşlenir, bu becerileri isteyen
meslek grupları bulunur, o meslek gruplarının etiketlerinden ilan başlığı kalıpları
üretilir. Böylece rol aileleri **tüm sektörler için otomatik** doğar.

**Doğrulama ölçütü:** 25 CV'lik genişletilmiş benchmark'ta her CV'nin ilk 5 sonucunda
"alan içi" oranı ≥ %60 (bugün teknoloji CV'lerinde 5/5, yazılım dışında ölçülmedi).

**Emek:** 2 gün. **Risk:** ESCO meslek etiketleri ilan başlıklarıyla birebir
örtüşmeyebilir ("software developer" vs "Senior Backend Engineer"); eşleme katmanı
gerekebilir.

---

## 3. CV ayrıştırma sağlamlığı

**Kök sebep.** `pdftotext -layout` + düzenli ifade. Tek kolonlu, düz CV'de çalışıyor.

### 3a. Düzen farkında çıkarım (iki kolon, tablo)

`PyMuPDF` (zaten kurulu) metin bloklarını **koordinatlarıyla** veriyor. Plan:
- Blokların `x0` değerleri kümelenir; iki belirgin küme varsa **iki kolonlu** kabul edilir
  ve bloklar kolon-kolon, sonra yukarıdan aşağı sıralanır.
- Tablo benzeri hizalı blok grupları satır olarak birleştirilir.
- Sıra: PyMuPDF düzen analizi → `pdftotext -layout` → ham metin (kademeli yedek).

**Doğrulama ölçütü:** 15 CV'nin her biri 4 düzende üretilir (tek kolon, iki kolon,
tablolu, LaTeX) = 60 dosya. Hedef: 60/60'ında deneyim yılı ±1,5 ve yetenek tespiti
tek kolonlu sürümün ≥%80'i.

**Emek:** 2 gün.

### 3b. Taranmış PDF

Bugün: metin çıkmazsa net hata veriyor (sessizce yanlış yapmıyor — bu iyi).
Plan: sayfa başına metin uzunluğu ~0 ise **taranmış** teşhisi konur ve kullanıcıya
şu söylenir: "bu PDF'te metin katmanı yok". `ocrmypdf`/Tesseract kuruluysa OCR
önerilir; değilse kurulum bağlantısı verilir. **OCR'ı paketin içine gömmek yok** —
80 MB'lık uygulama 400 MB olur.

**Doğrulama ölçütü:** taranmış bir PDF yüklendiğinde kullanıcı 1 cümlede ne
yapacağını öğreniyor; sessiz başarısızlık 0.

**Emek:** yarım gün.

### 3c. Çalışma izni — tahmin değil, zorunlu adım

Bu alan CV'den **çıkarılamaz** ve yanlış olursa tüm konum filtresi anlamsızlaşır.

- Bugün: uyarı var ama kullanıcı atlayabiliyor.
- Plan: **tarama, çalışma izni onaylanmadan başlamaz.** Panelde engelleyici adım.
- İpuçları önerilebilir (telefon ülke kodu, adres, CV dili) ama **asla gerçek diye
  işaretlenmez** — yalnızca önceden işaretli öneri olarak sunulur, kullanıcı onaylar.

**Doğrulama ölçütü:** profil yokken veya izin onaylanmamışken `POST /api/tara`
**400 döner**; arayüz adımı gösterir.

**Emek:** yarım gün.

### 3d. İsteğe bağlı LLM destekli çıkarım — uydurma korumasıyla

Kural tabanlı ayrıştırıcı **varsayılan kalır** (bedava, açıklanabilir, çevrimdışı).
Kullanıcı isterse yerel LLM (Ollama/LM Studio) veya kendi API anahtarıyla
yapılandırılmış çıkarım açılır.

**Uydurma koruması — zorunlu:** LLM'in ürettiği her olgusal atom (şirket adı, teknoloji,
sayı, tarih) kaynak CV metninde **aranır**; bulunmayan atom içeren alan **reddedilir**.
Yani LLM yalnızca *seçebilir ve düzenleyebilir*, *ekleyemez*.

**Doğrulama ölçütü:** kasten tuzaklı 10 CV (yanıltıcı başlıklar, eksik tarihler) ile
koşulur; LLM çıktısında kaynak CV'de olmayan tek bir şirket/teknoloji/sayı bulunmamalı.

**Emek:** 2 gün.

---

## 4. Hayalet ilan tespiti

**Kök sebep.** Güçlü sinyaller (sahte tazeleme, yeniden yayım) **zaman** ister;
ilk koşuda elde sadece yaş + kalıp var.

### 4a. Hazır geçmiş dağıt — asıl çözüm

Kullanıcının haftalarca beklemesine gerek yok: **biz** tarayıcıyı sürekli koşturup
anonim bir hayalet-sinyal veri kümesi yayınlayabiliriz.

- Şema: `ilan_parmak_izi` (şirket + normalize başlık özeti) → `ilk_gorulme`,
  `yeniden_yayim_sayisi`, `sahte_tazeleme_sayisi`, `toplam_gorulme`, `son_gorulme`.
- Kişisel veri yok, ilan metni yok — yalnız özet ve sayaçlar.
- Depoda küçük bir SQLite/JSON anlık görüntüsü; zamanlanmış iş günlük günceller.
- İlk açılışta indirilir → kullanıcı **1. günden** güçlü sinyale sahip olur.

**Doğrulama ölçütü:** anlık görüntü ile ilk koşuda işaretlenen hayaletlerin ≥%80'i,
4 hafta sonraki gerçek gözlemle (ilan hâlâ açık mı, yeniden mi yayımlandı) uyuşmalı.

**Emek:** 2 gün + sürekli koşum altyapısı.

### 4b. Gün-1 sinyallerini çoğalt (geçmiş gerektirmeyenler)

- **Şirket içi yaş anomalisi:** ilan yaşı, o şirketin ilanlarının medyan yaşının
  kaç katı? Medyanı 20 gün olan şirkette 300 günlük ilan güçlü sinyaldir.
  **Bu havuzdan anında hesaplanabilir, geçmiş gerektirmez.**
- `validThrough` alanı (JSON-LD, madde 1a): geçmiş tarih → ilan ölü.
- Maaş yok + "sürekli alım" dili + çok konum + genel başlık birleşimi.
- Aynı ilanın birden çok panoda farklı tarihlerle görünmesi.
- Şirketin açık ilan sayısı / tahmini büyüklüğü oranı (havuz ilanı göstergesi).

**Doğrulama ölçütü:** her yeni sinyal tek başına ölçülür; ayırt ediciliği olmayan
(etiketli örneklemde hayalet/gerçek ayrımı yapmayan) sinyal **eklenmez**.

**Emek:** 1-2 gün.

### 4c. Eşikleri kalibre et — bugün elle konmuş

Ağırlıklar (yaş > 365 → +0,50 gibi) makul ama **ölçülmedi**. Plan:
- 200 ilanlık örneklem seçilir, 6 hafta boyunca haftalık kontrol edilir
  (hâlâ açık mı? yeniden mi yayımlandı? kapandı mı?).
- Bu etiketlerle ağırlıklar uydurulur (basit lojistik regresyon yeter).
- Sonuç: kesinlik/duyarlılık sayısı **yayınlanır**. "Hayalet tespiti var" demek
  yerine "şu kesinlikte" demek.

**Emek:** 6 hafta takvim süresi, ~1 gün fiili iş. **Bunun kısayolu yok.**

---

## 5. Anlamsal eşleştirme

**Kök sebep.** Anahtar kelime eşleştirmesi eş anlamı kaçırıyor ("K8s" ≠ "Kubernetes").

**Tasarım kısıtı:** sert filtreler (konum, çalışma izni, kıdem) **deterministik kalmalı**.
Orada hata pahalıdır ve açıklanabilirlik şarttır. Anlamsal katman yalnızca
*sıralamaya* girer, elemeye değil.

### 5a. Eş anlam grafiği (ESCO alternatif etiketleri) — önce bu

Ölçüldü: ESCO her beceri için alternatif etiketler veriyor. Bu, gömme modeline gerek
kalmadan eş anlam sorununun büyük kısmını çözer: bedava, çevrimdışı, açıklanabilir,
pakete ~1-2 MB ekler.

**Doğrulama ölçütü:** elle yazılmış 100 eş anlam çiftinden (K8s/Kubernetes,
ML/machine learning, RAG/retrieval augmented generation…) en az 70'i grafikten
karşılanmalı.

**Emek:** 1 gün.

### 5b. İsteğe bağlı yerel gömme

Kullanıcıda Ollama/LM Studio varsa gömme modeli oradan kullanılır (paket büyümez,
maliyet sıfır, veri makineden çıkmaz). Yoksa 5a ile devam edilir.

- Hibrit skor: `0,7 × deterministik + 0,3 × anlamsal`, ikisi de arayüzde **ayrı ayrı**
  gösterilir ki kullanıcı neye güveneceğini bilsin.

**Emek:** 1-2 gün.

### 5c. İlk 30 için LLM yeniden sıralama (isteğe bağlı)

Yalnız ilk 30 aday LLM'e sorulur (ucuz), çıktı: uyum puanı + **gerekçe cümlesi**.
Deterministik puanın yerine geçmez, yanında görünür.

**Doğrulama ölçütü:** benchmark'a "yeniden yazılmış ilan" seti eklenir — aynı iş,
farklı sözcüklerle. Hedef: bu ilanlar ilk 10'da kalmalı.

**Emek:** 1-2 gün.

---

## 6. Başvuru katmanı

**Değişmez kısıt (doğrulandı):** ATS'lerin başvuru uçları **işverenin** API anahtarını
ister (Greenhouse'un POST ucu Basic Auth istiyor; bu anahtar adayda yoktur).
Dolayısıyla başvuru **tarayıcıda form doldurarak** yapılır. Bu, araştırdığım olgun
projelerde de böyle — gizli bir kanal yok.

### 6a. Cevap bankası

Form soruları tekrar ediyor. Şema: soru tipi (metin/seçim/evet-hayır/sayı),
normalize soru anahtarı, cevap, son kullanım tarihi.

Tipik kalemler: çalışma izni, vize sponsorluğu ihtiyacı, ihbar süresi, maaş beklentisi,
"X ile kaç yıl deneyim", taşınmaya açıklık, başlangıç tarihi, "neden bu şirket".

**Kural:** demografik/EEO soruları (cinsiyet, etnik köken, engellilik, gazilik)
**asla otomatik doldurulmaz** — boş bırakılır, kullanıcı kendisi karar verir.

**Emek:** 1-2 gün.

### 6b. İlana özel CV + ön yazı — uydurma yasağı mekanik olmalı

"LLM'e uydurma deme" yetmez. Mekanizma:
1. Üretici yalnızca kaynak CV'deki cümleleri **seçer ve sıralar**, yeni iddia yazmaz.
2. Üretim sonrası **atom denetimi**: çıktıdaki her şirket adı, teknoloji, sayı ve
   tarih kaynak CV'de aranır. Eşleşmeyen atom içeren cümle **atılır**.
3. Çıktı ATS-güvenli biçimde: tablo/kolon/grafik yok, standart başlıklar, gerçek metin.

**Doğrulama ölçütü:** 15 CV × 5 ilan = 75 üretimde, kaynak CV'de olmayan **tek bir**
olgusal atom bulunmamalı. Bu sıfır toleranslı bir testtir.

**Emek:** 2-3 gün.

### 6c. Form doldurma — Chrome eklentisi (MV3)

**Neden eklenti, Playwright değil:** eklenti kullanıcının **kendi tarayıcısında,
kendi oturumunda** çalışır. Otomasyon sürücüsü yoktur, dolayısıyla tespit yüzeyi de
yoktur. Kullanıcı ekranın başındadır.

- İçerik betiği alanları etiket metni, `name`, `aria-label` ve ATS'e özel
  seçicilerle eşler (Greenhouse/Lever/Ashby/Workday alan adları kararlıdır).
- Doldurduğu her alanı **görsel olarak işaretler**.
- **Gönder düğmesine dokunmaz.** Kullanıcı basar.
- Bilinmeyen soru → yan panel sorar, cevap bankaya kaydedilir.

**Bilinen sınır — dürüstçe:** tarayıcı güvenliği gereği eklenti `<input type=file>`
değerini programatik olarak **ayarlayamaz**. CV dosyası seçimi yarı-manuel kalır:
araç uyarlanmış CV'yi bilinen bir klasöre yazar ve "şu dosyayı seç" der.

**Doğrulama ölçütü:** 4 ATS'in gerçek başvuru formunda (test ilanıyla, gönderilmeden)
alanların ≥%80'i doğru doldurulmalı; yanlış alana yazma **0** olmalı.

**Emek:** 4-5 gün.

### 6d. Başvuru takibi + geri besleme döngüsü

SQLite: ilan kimliği, başvuru tarihi, kullanılan CV, verilen cevaplar, durum
(başvuruldu / ret / görüşme / teklif / yanıtsız), kaynak, o günkü uygunluk puanı.

**Asıl değeri şu:** puan bandı ile yanıt oranını karşılaştırmak. "80+ puanlı
başvurularda yanıt oranı %X, 40-60 bandında %Y" — bu, **puanlamanın gerçekten
işe yarayıp yaramadığının tek dürüst ölçüsü**. Bugün böyle bir ölçü yok.

**Emek:** 1-2 gün.

### 6e. Hacim disiplini — bilinçli sınır

Günlük başvuru üst sınırı (öneri: 10) ve her başvuru için ayrı onay.
Gerekçe teknik değil, sonuç odaklı: yüksek hacimli düşük uyumlu başvuru yanıt
oranını düşürür ve ATS tarafında aday kalite skorunu bozar.

---

## Sıralama önerisi

| Sıra | İş | Neden önce | Emek |
|---|---|---|---|
| 1 | 1a JSON-LD tarayıcı + 1d toplayıcılar | Kapsam her şeyin önkoşulu; havuz zenginleşmeden diğer iyileştirmeler ölçülemez | 2-3 gün |
| 2 | 2a ESCO + 2b serbest çıkarım | Yazılım dışı meslekleri açar; 5a eş anlamı da buradan gelir | 4-5 gün |
| 3 | 6a+6b+6c başvuru katmanı | Aracın asıl amacı; onsuz "iş arama" aracı | 7-10 gün |
| 4 | 1c Kariyer.net + 1b kurumsal ATS | Türkiye kapsamı | 3-4 gün |
| 5 | 3a-3c CV sağlamlığı | Gerçek dünya CV'leri | 3 gün |
| 6 | 4a-4b hayalet güçlendirme | Sürekli koşum altyapısı gerekiyor | 3-4 gün |
| 7 | 6d takip + geri besleme | Puanlamanın işe yarayıp yaramadığını ölçer | 1-2 gün |
| 8 | 4c kalibrasyon | 6 hafta takvim süresi ister, erken başlatılmalı ama geç biter | 1 gün + bekleme |

**Not:** 4c (kalibrasyon) takvim süresi istediği için **1. sırayla birlikte
başlatılmalı** — örneklem bugün seçilip haftalık gözlem bugün başlarsa, 6 hafta
sonra sonuç hazır olur.

## Yazarken doğrulananlar

| İddia | Sonuç |
|---|---|
| ESCO API kimlik doğrulamasız çalışıyor | ölçüldü, HTTP 200 |
| ESCO alternatif etiket (eş anlam) veriyor | ölçüldü: Python → Py3K, Python prog, Python2… |
| ESCO Türkçe destekliyor | **ölçüldü: HAYIR**, `language=tr` İngilizce başlığa düşüyor, 0 Türkçe alternatif |
| Workday'in genel JSON ucu var | ölçüldü: 422 döndü (uç var, yük şeması keşfedilmeli), 404 değil |
| kariyer.net robots.txt ilan sayfalarını yasaklamıyor | ölçüldü |
| kariyer.net anonim istekle okunabiliyor | ölçüldü: HTTP 200, 0,56 sn, 53 ilan bağlantısı |
| ATS başvuru uçları işveren anahtarı istiyor | Greenhouse belgesinden; bağımsız projede de aynı tespit |
