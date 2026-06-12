# Yapay Zeka Tabanlı Ürün Eşleştirme Sistemi

**Nabil Hassan** · Trendbox · Haziran 2026

---

## Özet

Trendbox kataloğunda barkodu eksik ürünlerin, barkodlu referans ürünlerle metin analizi yoluyla eşleştirilmesi için uçtan uca bir sistem geliştirdim. Ham CSV verisinden operatör arayüzüne kadar tüm katmanlar çalışır durumda: veri önişleme, iki aşamalı eşleştirme pipeline'ı, güven skoruna dayalı otomatik triage ve insan onayı gerektiren durumlar için review arayüzü.

Kaynak kod: [github.com/Nabilhassan12345/trendbox-product-matching](https://github.com/Nabilhassan12345/trendbox-product-matching)

---

## Problem

Elimizde farklı kaynaklardan gelen ~100 bin satırlık bir ürün listesi var. Bunların bir kısmında barkod tam, bir kısmında eksik veya hiç yok. Aynı ürün farklı kaynaklarda farklı yazılıyor — örneğin `Nutella 400gr` ile `Nutella Fındık Kreması 400 g` aynı SKU'ya karşılık geliyor ama metin olarak farklı.

| | |
|---|---:|
| Toplam satır | 100.585 |
| Barkodlu | 58.434 |
| Eşleştirilecek (barkodsuz) | 42.151 |
| Aynı barkoda birden fazla yazım | 9.132 barkod |

Amaç: barkodlu ürünleri referans kabul ederek barkodsuz satırları doğru barkodla bağlamak. Yanlış otomatik eşleşme katalog kalitesini bozacağından, sistemin belirsiz durumlarda operatöre sorması gerekiyor.

---

## Veri hazırlığı

Eşleştirmeden önce ürün isimlerini standart forma çeviriyorum. Uygulama `src/preprocess.py` içinde.

Normalizasyon adımları: küçük harfe çevirme, Türkçe karakterlerin ASCII karşılığına dönüşümü (`ş→s`, `ğ→g`), birim standardizasyonu (`400gr` → `400 g`), noktalama ve gereksiz karakterlerin temizlenmesi, ardından marka ve ağırlık bilgisinin isimden çıkarılması. Taze ürünler (`domates 1 adet` gibi) ile markalı FMCG ürünleri ayrı sınıflandırılıyor; bu ayrım güven skorundaki marka cezasını etkiliyor.

Örnek:

```
Nutella Fındık Kreması 400 gr  →  nutella findik kremasi 400 g
ÜLKER HANIMELLER 150GR          →  ulker hanimeller 150 g
```

Veri profili analizi (`scripts/profile_data.py`) gösterdi ki eski yaklaşımda barkod deduplikasyonu 27 binden fazla satır kaybettiriyordu. Bu yüzden SQLite'ta barkod başına tek canonical satır tutulurken, arama indeksinde aynı barkoda ait tüm yazım varyantları (58.434 alias satır) indeksleniyor.

---

## Yapay zeka ve NLP yaklaşımı

### Mimari

Sistem üç katmanlı çalışıyor:

1. **Stage 0** — Deterministik exact/fuzzy isim eşleşmesi. ML'e gitmeden önce bilinen yazımlar doğrudan çözülüyor. Batch sonucunda 3.391 ürün bu aşamada kapandı.
2. **Stage 1** — Karakter düzeyinde TF-IDF ile cosine similarity. 58 bin referans arasından 50 aday milisaniyeler içinde çekiliyor (~31 ms/sorgu).
3. **Stage 2** — `paraphrase-multilingual-MiniLM-L12-v2` embedding modeli ile semantic rerank. Top 3 aday döndürülüyor (~77 ms/sorgu, iki aşamalı toplam).

Stage 1 hız için, Stage 2 doğruluk için. 42 bin sorguyu doğrudan embedding ile karşılaştırmak hem yavaş hem de farklı marka/boyut varyantlarında yanıltıcı skorlar üretiyor.

### Vektör veritabanı

Referans embedding'leri FAISS indeksinde tutuluyor (`faiss-cpu`). Bu ölçekte (~58k referans) yerel FAISS yeterli: ek altyapı maliyeti yok, diskten yüklenebiliyor, arama milisaniye düzeyinde. Pinecone veya Qdrant gibi hosted çözümler dağıtık senaryo veya milyonlarca vektör için anlamlı; bu proje için gereksiz.

### Güven skoru ve triage

Her aday için ensemble skor hesaplanıyor:

```
confidence = 0.50 × TF-IDF + 0.50 × embedding
           + marka/ağırlık bonusu
           − marka/ağırlık uyumsuzluk cezası
```

Embedding modeli aynı ürünün farklı marka veya boyut varyantlarına yüksek skor verebiliyor; bu yüzden TF-IDF'e eşit ağırlık verdim ve marka/ağırlık uyumsuzluğunda sert ceza uyguladım.

| Güven | Karar |
|------:|-------|
| > 0.90 | Otomatik onay |
| 0.60 – 0.90 | Operatör incelemesi |
| < 0.60 | Otomatik red |

### Değerlendirme

Aynı barkoda farklı yazıma sahip ürünlerden ground truth oluşturup held-out test yaptım (`scripts/evaluate.py`, 100 sorgu):

| Yaklaşım | Recall@1 | Recall@3 |
|----------|---------:|---------:|
| TF-IDF | 69% | 85% |
| Embedding (FAISS) | 55% | 65% |
| İki aşamalı (prod) | 66% | 83% |

TF-IDF tek başına bu veri setinde güçlü; embedding tek başına zayıf kalıyor. İki aşamalı pipeline ikisinin güçlü yanlarını birleştiriyor.

Kullanılan kütüphaneler: scikit-learn, sentence-transformers, faiss-cpu, numpy.

---

## Arayüz ve operatör katkısı

Orta güven aralığındaki eşleşmeler Streamlit review arayüzüne düşüyor. Operatör eşleştirilecek ürünü, AI'ın önerdiği top-3 adayı (barkod, referans isim, TF-IDF/embedding skorları, açıklama metni) görüyor ve Onayla veya Reddet diyor. Kararlar SQLite'a yazılıyor.

Arayüzde ayrıca onaylanan/reddedilen geçmiş, otomatik reddedilenleri yeniden kuyruğa alma, analytics sayfasında throughput ve pipeline istatistikleri var. Backend FastAPI üzerinden REST endpoint'ler sunuyor.

Teknoloji: Streamlit (UI), FastAPI (API), SQLAlchemy + SQLite (persistans).

---

## Sonuçlar

38.541 barkodsuz ürün üzerinde batch matching çalıştırıldı:

| Durum | Adet |
|-------|-----:|
| Otomatik onay | 9.363 |
| Operatör incelemesi bekleyen | 10.520 |
| Otomatik red | 18.656 |

Ortalama rank-1 güven skoru: 0,62. Operatör kuyruğundaki ~10,5 bin ürün henüz nihai karar bekliyor; otomatik onay oranı konservatif eşikler sayesinde yanlış pozitif riskini sınırlıyor.

---

## Çalıştırma

```bash
git clone https://github.com/Nabilhassan12345/trendbox-product-matching.git
cd trendbox-product-matching
pip install -r requirements.txt
python pipeline.py
```

UI: http://localhost:8501 · API: http://localhost:8000/docs

Testler: `python tests/run_all_tests.py`
