# NovelReader2

**Roman indirme, çeviri ve okuma uygulaması**

NovelReader2; çevrim içi romanları desteklenen web sitelerinden indirmek, bölüm metinlerini yerel olarak saklamak, Türkçeye çevirmek ve tek bir arayüz üzerinden okumak için geliştirilen Python tabanlı bir masaüstü uygulamasıdır.

Projenin temel hedefi yalnızca roman indirmek değildir. İndirme, çeviri, arşivleme ve okuma işlemlerini birbirinden ayırarak yönetilebilir bir roman kütüphanesi oluşturmaktır. Kullanıcı, indirdiği orijinal metinleri koruyabilir, çevirileri ayrı saklayabilir ve işlemlere daha sonra kaldığı yerden devam edebilir.

> **Proje durumu:** Geliştirme aşamasındadır. Desteklenen sitelerin sayfa yapıları değişebilir. Özelliklerin bulunması, her sitede ve her romanda hatasız çalışacağının garantisi değildir.

---

## İçindekiler

- [Özellikler](#özellikler)
- [Arayüz sekmeleri](#arayüz-sekmeleri)
- [Sistem gereksinimleri](#sistem-gereksinimleri)
- [Kurulum](#kurulum)
- [Kullanım kılavuzu](#kullanım-kılavuzu)
- [İndirme sistemi nasıl çalışır?](#indirme-sistemi-nasıl-çalışır)
- [Çeviri sistemi](#çeviri-sistemi)
- [Metin temizleme ve Words Filter](#metin-temizleme-ve-words-filter)
- [Roman ve bölüm yönetimi](#roman-ve-bölüm-yönetimi)
- [Görünüm ve kişiselleştirme](#görünüm-ve-kişiselleştirme)
- [Veri yapısı ve güvenliği](#veri-yapısı-ve-güvenliği)
- [Desteklenen siteler](#desteklenen-siteler)
- [Sorun giderme](#sorun-giderme)
- [Bilinen sınırlamalar](#bilinen-sınırlamalar)
- [Geliştirme planı](#geliştirme-planı)
- [Katkıda bulunma](#katkıda-bulunma)
- [Lisans](#lisans)

---

## Özellikler

### Roman indirme

- Desteklenen sitelerden roman bilgilerini alma.
- Romanın ilk bölüm adresinden başlayarak bölümleri sırasıyla indirme.
- Bölüm başlıklarını ve kaynak adreslerini saklama.
- İndirme miktarını kullanıcı tarafından belirleme.
- İndirmeyi durdurma ve daha sonra devam ettirme.
- İndirme işlemini arka planda yürütme.
- İndirme durumunu ve işlem kayıtlarını arayüzden takip etme.
- İndirilmiş bölümleri tekrar indirmek yerine eksik bölümlerden devam etme.

### Çeviri

- İndirilmiş bölümleri Google Translate tabanlı çeviri sistemiyle Türkçeye çevirme.
- Orijinal metni değiştirmeden çeviriyi ayrı dosyalarda saklama.
- İndirme ve çeviri işlemlerini birbirinden bağımsız yürütme.
- Çeviri miktarını sınırlandırma.
- Hata alınan çeviriler için yeniden deneme.
- Daha önce eksik kalmış çevirileri yeniden işleme.
- Çeviri başarısız olduğunda isteğe bağlı olarak orijinal metni yedek biçiminde saklama.
- Romanın bilgi sayfasını da çevirebilme.

### Kütüphane ve okuma

- Romanları tek bir listede görüntüleme.
- İndirilen ve çevrilen bölüm sayılarını takip etme.
- Yazar, tür, açıklama, yayın durumu ve kapak bilgilerini görüntüleme.
- Bölüm listesinden orijinal veya çevrilmiş metni açma.
- Okuma ekranında önceki ve sonraki bölüme geçme.
- Çevirisi bulunan bölümleri öncelikli gösterme; çeviri yoksa orijinal metni kullanma.
- Kaynak sayfasını tarayıcıda açma.
- Romanın toplam bölüm sayısını elle düzenleme.
- Romanı **Bitti** veya **Devam ediyor** olarak işaretleme.

### Kişiselleştirme

- Windows tema tercihini algılama.
- Açık ve koyu tema arasında geçiş yapma.
- Arka plan, panel, düğme, yazı ve seçili alan renklerini özelleştirme.
- Okuma yazı tipini, yazı boyutunu ve satır aralığını değiştirme.
- Görünüm ayarlarını kalıcı olarak kaydetme.
- Pencere boyutunu ve konumunu saklama.

---

## Arayüz sekmeleri

NovelReader2, farklı işlemleri ayrı sekmelerde toplar.

### 1. Downloads

Roman ekleme, indirme ve indirme sürecini takip etme alanıdır.

Bu sekmede:

- İlk bölümün URL adresi girilir.
- Roman eklenir veya roman bilgileri yenilenir.
- İndirme yapılacak roman seçilir.
- İndirilecek bölüm sayısı belirlenir.
- İndirme başlatılır veya durdurulur.
- İndirme günlüğü ve işlem durumu izlenir.
- Roman listesi yenilenir.

Bölüm sayısı alanında `0` kullanılması, mevcut eksik bölümlerin tamamının indirilmesini ifade eder.

### 2. Novel List

Kütüphanedeki romanların ve çeviri işlemlerinin yönetildiği sekmedir.

Roman listesinde indirme ve çeviri sayıları görüntülenir. Bir roman seçildiğinde ön izleme alanında mevcut roman bilgileri gösterilir.

Bu sekmeden:

- Romanın bilgileri incelenebilir.
- Toplam bölüm sayısı elle değiştirilebilir.
- Yayın durumu kaydedilebilir.
- Bölüm listesi açılabilir.
- Çeviri başlatılabilir veya durdurulabilir.
- Eksik çeviriler yeniden denenebilir.
- İstenirse roman yerel kütüphaneden silinebilir.

**Dikkat:** Roman silme işlemi onay gerektirir ve seçilen romanın yerel bölüm dosyalarını ve kütüphane kaydını kaldırır. Silmeden önce gerekli dosyaların yedeğini almak önerilir.

### 3. Chapters

Seçilen romanın bölüm listesini gösterir.

Bölümlerin durumları genel olarak şu şekildedir:

- **Bekliyor:** Henüz indirilmemiş veya işlenmemiş bölüm.
- **İndirildi:** Orijinal metni mevcut bölüm.
- **Çevrildi:** Çevirisi bulunan bölüm.

Bu sekmeden orijinal metin veya çeviri açılabilir; eksik bölümler indirme işlemine gönderilebilir.

### 4. Reader

Bölümlerin okunabildiği okuma ekranıdır.

- Önceki ve sonraki bölüme geçilebilir.
- Çeviri mevcutsa çevrilmiş metin görüntülenir.
- Orijinal metne ihtiyaç duyulduğunda Chapters sekmesinden açılabilir.
- Bölümün kaynak adresi üzerinden özgün web sayfasına ulaşılabilir.

### 5. Words Filter

Sitelerin bölüm metinlerinde tekrar eden reklam veya istenmeyen ifadeleri temizlemek için kullanılır.

Her site için ayrı bir ifade listesi tutulur. Bir satıra bir kelime veya ifade yazılır. Eşleşmeler büyük/küçük harf duyarsızdır.

### 6. Görünüm

Uygulamanın renk ve okuma metni ayarlarının düzenlendiği sekmedir.

- Ana arka plan rengi
- Panel ve metin alanı rengi
- Düğme rengi
- Yazı rengi
- Seçili alanların rengi
- Yazı tipi
- Yazı boyutu
- Satır aralığı

Renkler HEX biçiminde girilebilir; örneğin `#242629`. Renk seçici de kullanılabilir. Ön izleme alanı değişikliklerin görünümünü kontrol etmeyi sağlar.

**Uygula ve kaydet** ayarları kalıcılaştırır. **Varsayılanlara dön** geçerli tema için varsayılan renkleri yükler.

---

## Sistem gereksinimleri

Mevcut sürüm Windows üzerinde çalışacak şekilde hazırlanmıştır.

- Windows 10 veya Windows 11
- Python 3.10 veya üzeri
- İnternet bağlantısı
- Python paketlerini kurmak için `pip`
- Roman sayfalarına erişebilen bir internet bağlantısı

Gerekli Python paketleri `requirements.txt` dosyasında listelenir:

- `requests`
- `beautifulsoup4`
- `googletrans-py`
- `Pillow`

Arayüz Python'un Tkinter kütüphanesini kullanır. Desteklenen standart Python Windows kurulumlarında Tkinter genellikle hazır gelir.

---

## Kurulum

### 1. Python kurulumu

Bilgisayarınızda Python 3.10 veya daha yeni bir sürüm bulunmalıdır.

Kurulumu kontrol etmek için Komut İstemi'ni açıp şu komutu çalıştırın:

```bat
py --version
```

Komut çalışmıyorsa Python kurulumunu ve PATH ayarlarını kontrol edin.

### 2. Projeyi indirme

GitHub deposunu ZIP olarak indirebilir veya Git ile klonlayabilirsiniz.

ZIP yöntemiyle indirdiğiniz projeyi istediğiniz bir klasöre çıkarın. Örnek:

```text
NovelReader2/
├── app.py
├── reader.bat
├── requirements.txt
├── README.md
├── core/
├── sites/
└── tests/
```

### 3. Gerekli paketleri yükleme

Komut İstemi'ni proje klasöründe açın ve çalıştırın:

```bat
py -m pip install -r requirements.txt
```

İsteğe bağlı olarak sanal ortam kullanabilirsiniz:

```bat
py -m venv .venv
.venv\Scripts\activate
py -m pip install -r requirements.txt
```

### 4. Uygulamayı başlatma

Normal kullanım için `reader.bat` dosyasına çift tıklayın.

Alternatif olarak Komut İstemi'nden:

```bat
py app.py
```

komutunu kullanabilirsiniz. Bu yöntem, hata mesajlarını konsolda görmeyi kolaylaştırır.

### Güncelleme

Yeni sürümü mevcut proje klasörünün üzerine çıkarın. **Mevcut `data/` klasörünüzü silmeyin veya yenisiyle değiştirmeyin.**

Dağıtım paketleri kullanıcı verilerini içermeyecek şekilde hazırlanır. Bununla birlikte güncellemeden önce `data/` klasörünün yedeğini almak her zaman iyi bir uygulamadır.

---

## Kullanım kılavuzu

### İlk romanı ekleme

1. Uygulamayı açın.
2. Downloads sekmesine geçin.
3. Desteklenen bir sitedeki romanın ilk bölüm URL adresini ilgili alana yapıştırın.
4. **Romanı Ekle / Bilgileri Yenile** düğmesine basın.
5. Roman bilgileri alındıktan sonra romanın listeye eklenmesini bekleyin.
6. İndirmek istediğiniz romanı listeden seçin.

Uygulama, sitenin yapılandırmasına göre romanın başlangıç bölümünü belirler. Her sitenin sayfa yapısı farklı olabileceği için doğru URL kullanılması önemlidir.

### Bölümleri indirme

1. Downloads sekmesinden romanı seçin.
2. Bölüm sayısı alanına indirmek istediğiniz yeni bölüm sayısını girin.
3. **İndirmeyi başlat** düğmesine basın.
4. İlerlemeyi ve olası hataları indirme günlüğünden takip edin.

Örnekler:

- `10`: En fazla 10 yeni bölüm indir.
- `50`: En fazla 50 yeni bölüm indir.
- `0`: Mevcut eksik bölümlerin tamamını indirmeyi dene.

İndirme sırasında işlem durdurulabilir. Uygulama daha sonra yeniden başlatıldığında kayıtlı bölüm bilgileri üzerinden devam etmeye çalışır.

### Bölümleri çevirmek

1. Novel List sekmesine geçin.
2. Çevirmek istediğiniz romanı seçin.
3. Bölüm sayısı alanına çeviri miktarını girin.
4. **Çeviriyi başlat** düğmesine basın.
5. İşlem durumunu takip edin.

`0`, indirilmiş ve henüz çevrilmemiş tüm uygun bölümleri işlemeye çalışır.

İndirme ve çeviri ayrı işlemler olduğundan, bir romanın çevirisi devam ederken başka bir romanın indirilmesi mümkündür.

### Başarısız çevirileri yeniden denemek

Novel List sekmesindeki **Eksik Bölümleri Çevir** düğmesi, daha önce başarısız olmuş veya orijinal metni yedek olarak saklanmış bölümleri yeniden işlemeyi amaçlar.

Çeviri işlemi başarısız olursa uygulama en fazla üç deneme yapar. Yeniden denemeler de başarısız olduğunda, ilgili seçenek açıksa orijinal metin yedek olarak tutulur. Böyle bir yedek okunabilir; ancak başarılı bir Türkçe çeviri sayılmaz.

### Bölüm okumak

1. Novel List sekmesinden romanı seçin.
2. **Bölümleri Aç** düğmesine basın.
3. Chapters sekmesinde okumak istediğiniz bölümü seçin.
4. **Orijinali oku** veya **Çeviriyi oku** seçeneklerinden birini kullanın.

Reader sekmesindeki önceki/sonraki kontrolleriyle okumaya devam edebilirsiniz.

### Metin temizleme

1. Words Filter sekmesini açın.
2. Site listesinden ilgili siteyi seçin.
3. Temizlemek istediğiniz kelime veya ifadeleri satır satır girin.
4. **Kaydet** düğmesine basın.

Kurallar yeni indirilen metinlere ve çeviri öncesi temizleme sürecine uygulanır. Filtreyi değiştirmek, daha önce oluşturulmuş tüm çeviri dosyalarını otomatik olarak yeniden oluşturmaz.

### Görünümü değiştirme

1. Görünüm sekmesini açın.
2. Değiştirmek istediğiniz renk alanını seçin veya HEX kodunu girin.
3. Yazı tipi, boyut ve satır aralığını ayarlayın.
4. Ön izleme alanını kontrol edin.
5. **Uygula ve kaydet** düğmesine basın.

---

## İndirme sistemi nasıl çalışır?

NovelReader2, desteklenen `next_chain` sitelerinde bölüm listesinin tamamını önceden taramak yerine, ilk bölümden başlayıp her bölümün **Next** bağlantısını takip eder.

Genel akış:

1. Romanın başlangıç bölümü belirlenir.
2. Bölüm sayfası açılır ve metin çıkarılır.
3. Bölüm başlığı, kaynak adresi ve metin kaydedilir.
4. Sayfadaki sonraki bölüm bağlantısı bulunur.
5. İşlem sonraki bölümde tekrarlanır.

Bu yaklaşım, binlerce bölüm içeren romanlarda başlangıçta tüm bölüm bağlantılarını toplamaya gerek bırakmaz.

Uygulama, sitenin bildirdiği toplam bölüm sayısını ve gerçekten indirilen bölüm sayısını ayrı tutar. Böylece sitede görünen toplam sayı, indirmenin tamamlandığı anlamına gelmez.

Next bağlantısı bulunamazsa veya bağlantı zincirinde döngü tespit edilirse işlem günlüğüne uyarı veya hata yazılır. Bu durum romanın tamamının indirildiği anlamına gelmez.

---

## Çeviri sistemi

Çeviri işlemi `googletrans-py` paketi üzerinden Google Translate tabanlı bir arayüz kullanır. Çeviri için internet bağlantısı gereklidir.

Uygulama orijinal metinleri korur; çevirileri ayrı dosyalarda saklar. Böylece çeviri hataları orijinal metnin üzerine yazmaz.

Çeviri sistemi için önemli noktalar:

- Büyük romanları küçük partiler hâlinde çevirmek daha güvenli olabilir.
- Google tarafındaki hız sınırları veya servis değişiklikleri çeviriyi etkileyebilir.
- Hata alınan bölümler daha sonra yeniden denenebilir.
- Orijinal metin yedeği ile gerçek çeviri birbirinden ayrı değerlendirilir.
- Romanın bilgi sayfası, bölüm numarası `0` olan ayrı bir kayıt olarak tutulabilir.

`googletrans-py`, resmî bir Google Translate API entegrasyonu değildir. Bu nedenle erişim ve kararlılık konusunda garanti verilemez.

---

## Metin temizleme ve Words Filter

Roman sayfalarında reklam metinleri, uygulama tanıtımları, gezinme kontrolleri veya başka istenmeyen içerikler bulunabilir.

NovelReader2 iki temizleme yaklaşımını destekler.

### Site yapılandırmasındaki temizleme kuralları

`sites/` altındaki site JSON dosyaları, sayfa yapısına özgü temizleme kurallarını tanımlayabilir:

- `remove_selectors`: İstenmeyen HTML öğelerini CSS seçicileriyle kaldırır.
- `remove_exact_lines`: Tam eşleşen satırları kaldırır.
- `remove_text_patterns`: Belirli metin kalıplarını düzenli ifadelerle temizler.

Örnek:

```json
"content_cleanup": {
  "remove_selectors": [".ad-container", ".reader-toolbar"],
  "remove_exact_lines": ["Read more on our app"],
  "remove_text_patterns": ["^Advertisement:.*$"]
}
```

### Words Filter sekmesi

Words Filter, kullanıcı tarafından tanımlanan tam kelime ve ifadeleri temizler. Her satır ayrı bir ifadedir ve eşleştirme büyük/küçük harf duyarsız yapılır.

Aşırı genel filtreler gerçek hikâye cümlelerini de silebilir. Bu nedenle yalnızca gerçekten istenmeyen ifadeleri eklemek önerilir.

---

## Roman ve bölüm yönetimi

Roman bilgileri ile bölüm kayıtları birbirinden ayrı saklanır. Bölüm kimliği, kaynak URL'sinden türetilen bir hash ile belirlenir. Bu yaklaşım, bölüm başlıkları değişse bile kayıtların yönetilmesine yardımcı olur.

Romanın toplam bölüm sayısı şu değerlerden farklı olabilir:

- Web sitesinin bildirdiği toplam sayı
- Uygulamanın keşfettiği bölüm sayısı
- İndirilen bölüm sayısı
- Çevrilen bölüm sayısı

Bu sayılar aynı şeyi ifade etmez. Örneğin sitede 1.000 bölüm bildirilirken yalnızca 300 bölüm indirilmiş olabilir.

Toplam bölüm sayısı gerektiğinde Novel List ön izlemesinden elle değiştirilebilir. Romanın **Bitti / Devam ediyor** durumu da aynı alandan kaydedilebilir.

---

## Görünüm ve kişiselleştirme

Uygulama Windows'un açık/koyu tema tercihini algılayabilir. Tema düğmesi sistem teması, açık tema ve koyu tema arasında geçiş yapar.

Görünüm sekmesinde şu alanlar kişiselleştirilebilir:

| Ayar | Açıklama |
|---|---|
| Arka plan | Ana pencerenin temel rengi |
| Panel | Paneller ve metin alanlarının rengi |
| Düğme | Düğmelerin arka plan rengi |
| Yazı | Metin rengi |
| Vurgu | Seçili ve vurgulanan alanların rengi |
| Yazı tipi | Okuma metni için font ailesi |
| Yazı boyutu | Metnin büyüklüğü |
| Satır aralığı | Okuma metnindeki satır boşluğu |

Kişiselleştirme ayarları `data/appearance_settings.json` dosyasında tutulur. Roman ve çeviri dosyalarından ayrıdır.

---

## Veri yapısı ve güvenliği

Uygulamanın kullanıcı verileri `data/` klasöründe tutulur. Bu klasör dağıtım ZIP'inin parçası değildir; güncellemelerde mevcut klasör korunmalıdır.

Örnek veri düzeni:

```text
NovelReader2/
├── app.py
├── reader.bat
├── requirements.txt
├── README.md
├── core/
├── sites/
├── tests/
└── data/
    ├── novels/
    │   └── <site>_<novel-id>/
    │       ├── metadata.json
    │       ├── chapters.json
    │       ├── info.txt
    │       ├── chapters/
    │       │   └── <chapter-id>.txt
    │       └── translated/
    │           └── <chapter-id>.txt
    ├── appearance_settings.json
    └── ...
```

- `metadata.json`: Romanın başlık, yazar, tür, açıklama ve diğer metadata bilgileri.
- `chapters.json`: Bölüm kayıtları, kaynak adresleri ve işlem durumları.
- `info.txt`: Romanın bilgi sayfasının orijinal metni.
- `chapters/`: İndirilen orijinal bölüm metinleri.
- `translated/`: Çeviri dosyaları.
- `appearance_settings.json`: Görünüm tercihleri.

Gerçek dosya içeriği ve klasörler sürüme göre değişebilir.

### Veri kaybını önlemek için

- Uygulamayı güncellemeden önce `data/` klasörünü yedekleyin.
- Yeni sürümün ZIP dosyasından `data/` klasörü çıkmasını beklemeyin.
- Kütüphaneden roman silerken onay ekranını dikkatle kontrol edin.
- Çeviri ve orijinal dosyaların aynı şey olmadığını unutmayın.
- Sorun giderirken `data/` klasörünü silerek başlamayın.

---

## Desteklenen siteler

Mevcut yapılandırmalarda şu siteler bulunur:

| Site | Yapılandırma |
|---|---|
| FreeWebNovel | `sites/freewebnovel.json` |
| NovelBuddy | `sites/novelbuddy.json` |

Destek, ilgili sitenin mevcut HTML yapısına ve yapılandırma seçicilerine bağlıdır. Siteler tasarımlarını veya erişim politikalarını değiştirdiğinde indirme sistemi etkilenebilir.

Yeni site desteği eklemek için çoğunlukla sitenin başlık, bölüm içeriği, başlangıç bölümü ve sonraki bölüm bağlantısını tanımlayan yapılandırma gerekir. Her sitenin aynı yöntemle çalışacağı garanti edilmez.

---

## Sorun giderme

### Uygulama açılmıyor

Komut İstemi'ni proje klasöründe açıp şu komutu çalıştırın:

```bat
py app.py
```

Hata mesajını kontrol edin. Python sürümünü ve bağımlılıkların kurulmuş olduğunu doğrulayın:

```bat
py --version
py -m pip install -r requirements.txt
```

### Roman bilgileri alınamıyor

- URL adresinin doğru olduğundan emin olun.
- Sitenin normal tarayıcıda açıldığını kontrol edin.
- Sitenin HTML yapısı değişmiş olabilir.
- Site yapılandırmasındaki seçicilerin güncellenmesi gerekebilir.

### İndirme erken duruyor

İndirme günlüğünü kontrol edin. Sonraki bölüm bağlantısı bulunamamış, site erişimi engellenmiş veya bölüm zinciri değişmiş olabilir. Uygulamanın gördüğü bölüm sayısı, sitenin bildirdiği toplam sayıdan düşük olabilir.

### Çeviri çalışmıyor

- İnternet bağlantısını kontrol edin.
- Küçük bir bölüm grubuyla deneyin.
- Google Translate tarafındaki geçici sınırlamalar veya değişiklikler nedeniyle çeviri başarısız olabilir.
- Başarısız bölümleri daha sonra yeniden deneyin.

### Çeviri sayısı beklenenden az

Orijinal metni yedek olarak saklanan bölümler okunabilir olsa bile başarılı çeviri sayısına dahil edilmez. Novel List sekmesindeki **Eksik Bölümleri Çevir** seçeneğini kullanın.

### Renk veya görünüm ayarları beklediğim gibi değil

Görünüm sekmesindeki renk kodlarını kontrol edin. HEX renkleri `#RRGGBB` biçiminde olmalıdır. Gerekirse **Varsayılanlara dön** düğmesini kullanın.

---

## Bilinen sınırlamalar

- Uygulama geliştirme aşamasındadır; tüm web sitelerinde uçtan uca başarı garantisi yoktur.
- Site tasarımındaki veya erişim yöntemlerindeki değişiklikler indirmeyi bozabilir.
- Çeviri, internet erişimine ve üçüncü taraf bir arayüze bağlıdır.
- Çok büyük indirme ve çeviri işlemlerinde ağ veya servis kaynaklı hatalar görülebilir.
- Mevcut site yapılandırmaları sınırlıdır; her roman sitesinin desteklendiği anlamına gelmez.
- GUI'nin tüm Windows sürümleri, ekran ölçeklendirme oranları ve tema kombinasyonlarında eksiksiz test edildiği varsayılmamalıdır.

---

## Geliştirme planı

Aşağıdaki maddeler geliştirme fikirleri ve olası sonraki adımlardır; mevcut sürümde tamamlanmış özellikler olarak değerlendirilmemelidir.

### Site desteğini genişletme

- Yeni roman siteleri için yapılandırmalar eklemek.
- Site yapılandırmalarını daha kolay düzenlenebilir hâle getirmek.
- Site seçicilerinin bozulduğunu tespit etmeyi kolaylaştırmak.
- Yeni siteler için test senaryoları geliştirmek.

### Kütüphane ve veri yönetimi

- Kayıtlı romanların ve bölüm dosyalarının tutarlılığını denetleyen araçlar geliştirmek.
- Eksik dosya ve hatalı kayıtları tespit etmek.
- Yedekleme ve geri yükleme akışlarını iyileştirmek.
- Büyük kütüphanelerde listeleme ve arama deneyimini geliştirmek.

### Okuma deneyimi

- Okuma ekranının görünüm seçeneklerini geliştirmek.
- Okuma konumunu ve kullanıcı tercihlerini daha ayrıntılı yönetmek.
- Bölüm gezinmesini ve uzun metinlerin görüntülenmesini iyileştirmek.

### İndirme ve çeviri

- İndirme hatalarının daha anlaşılır raporlanması.
- Çeviri görevlerinin takibini ve yeniden deneme mekanizmasını geliştirmek.
- Büyük romanlar için uzun süreli işlemlerin dayanıklılığını artırmak.
- Alternatif çeviri sağlayıcılarının değerlendirilmesi.

Bu plan kesin bir sürüm takvimi değildir. Öncelikler test sonuçlarına ve geliştirme ihtiyaçlarına göre değişebilir.

---

## Katkıda bulunma

Hata bildirimleri ve geliştirme önerileri memnuniyetle karşılanır.

Bir hata bildirirken mümkünse şu bilgileri ekleyin:

- İşletim sistemi ve Python sürümü
- Kullanılan site
- İşlemin hangi sekmede yapıldığı
- Sorunun tekrar üretilebildiği adımlar
- İlgili hata günlüğü
- Beklenen davranış ve gerçekleşen davranış

Kişisel roman arşivinizi veya özel dosyalarınızı paylaşmanız gerekmez. Günlükleri paylaşmadan önce kişisel bilgileri ve özel URL'leri kaldırın.

Kod katkılarında mevcut kullanıcı verilerinin ve dosya yollarının geriye dönük uyumluluğunu korumak önemlidir.

---

## Lisans

Bu depoya ait lisans bilgisi, GitHub deposunda bulunan lisans dosyası üzerinden belirlenmelidir. Açık bir lisans dosyası yoksa projenin yeniden dağıtım ve kullanım koşulları ayrıca belirtilmelidir.

NovelReader2, üçüncü taraf web sitelerinden bağımsız bir projedir. İndirilen içeriklerin kullanımında ilgili sitelerin koşullarına, telif haklarına ve yürürlükteki mevzuata uyulması kullanıcının sorumluluğundadır.
