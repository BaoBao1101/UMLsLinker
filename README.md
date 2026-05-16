# OpenUMLS-Linker — Hướng dẫn nhanh (Vi)

Hướng dẫn ngắn cho người nhận dữ liệu: chép/copy các file raw vào đúng chỗ
và chạy từng bước ETL → CSV → SQLite → (tùy chọn) build vector index.

## Cấu trúc thư mục

- `data/`
  - `data/raw/`       : Nơi bạn copy/paste ontologies (MeSH, OBO, OWL, CSV xrefs).
  - `data/processed/` : Nơi các CSV + DB + index sẽ được sinh ra.

- `src/etl/`           : ETL scripts (`build_database.py`, `csv_to_sqlite.py`, ...)
- `src/linker/`        : index + linker code (`build_vector_index.py`, neural/rule linker)
- `src/pipeline/`        : Logic cho spaCy chia hộp và bỏ context vào các hộp, và chạy API test web (`router.py` và `app.py`)
- `src/router/cascading_router/`        : Test mẫu

## File raw cần copy vào `data/raw/`
- MeSH XML (ví dụ): `desc2026.xml` → `data/raw/desc2026.xml`
- ChEBI OBO: `chebi_lite.obo` → `data/raw/chebi_lite.obo`
- HPO: `hp.obo` → `data/raw/hp.obo`
- MONDO (hoặc mondo-base): `mondo-base.obo` → `data/raw/mondo-base.obo`
- (Bất kỳ file `.obo`, `.owl`, `.xml` bổ sung nào cũng đặt vào `data/raw/`)

## File data processed (đã up Google Drive, copy paste thôi, phase này đã batch thành vector, copy paste đỡ mất thời gian)
- data/processed: 
## alt_ids.csv, concepts.csv, definition.csv, open_umls_duck.db (tùy ý vì file này là bản raw database), relations.csv, synonyms.csv, vector_meta.csv, xrefs.csv

- data/processed/vector_index:
## meta.csv, vectors.npy


* Luu7 ý: Nếu đã parse các file vào data/processed và data/processed/vector_index thì CHỈ CHẠY STEP 0 để cài REQ và STEP 6 (Bỏ qua step 1,2,3,4,5)

Các file _test là để test một sample nhỏ trong lúc coding trước khi batch và run, có thể bỏ qua k cần chạy nếu k phát sinh lỗi

---
## Các bước chạy (theo thứ tự, Windows PowerShell)

1) Cài đặt dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
# Nếu thiếu: python -m pip install sentence-transformers spacy
```

2) (Tùy chọn) Kiểm tra parser nhanh (sample & counts)

```powershell
python scripts/check_parsers.py
```

3) Chạy ETL: tạo DuckDB + CSVs

```powershell
python src/etl/build_database.py --raw_dir data/raw --out data/processed/open_umls_duck.db --out_dir data/processed --overwrite
```

Ghi chú:
- `--mesh <path>` : chỉ định file MeSH nếu không đặt tên chuẩn `desc2026.xml`.
- `--no_csv` : thêm flag để không sinh CSV.

4) Chuyển CSV → SQLite (lightweight DB được Engine dùng)

```powershell
python src/etl/csv_to_sqlite.py --processed_dir data/processed --out data/processed/open_umls.db
```

5) Build dense vector index

```powershell
python src/linker/build_vector_index.py --db data/processed/open_umls.db --index_dir data/processed/vector_index --batch_size 128 --overwrite
```

- Thêm `--use_faiss` nếu đã cài `faiss` và muốn tạo FAISS index.
- `--batch_size` giảm -> dùng ít RAM nhưng lâu hơn.

6) Chạy API dev server

```powershell
uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

7) Kiểm tra nhanh các file sinh ra

```powershell
dir data\processed
Test-Path data\processed\concepts.csv
Test-Path data\processed\vector_index\meta.csv
```
## Cách Test Web:
vào POST -> TRY IT OUT -> Dán vào ô test theo định dạng { text: "string", top-k: } (Suggested 3)

String được đưa vào text phải được làm phẳng (không có kí tự xuống dòng enter)

