# Step-by-step — trạng thái và lệnh tái lập

Tài liệu này ghi lại đường chạy đã dùng cho corpus an toàn tài khoản, retrieval hybrid, generation có citation và evaluation A/B. Các lệnh PowerShell dùng Python trong `.venv`; trên Linux/macOS thay đường dẫn interpreter bằng `.venv/bin/python`.

## 1. Cài môi trường

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
```

Provider/model được đọc từ `.env` cục bộ. Không commit file này.

## 2. Thu thập và chuẩn hóa corpus

Chủ đề đã chọn là mật khẩu, MFA, phishing và federation trong tài liệu NIST. Corpus cuối có 3 PDF và 5 bài viết NIST, mỗi nguồn có provenance và checksum.

```powershell
.\.venv\Scripts\python.exe -m src.task1_collect_legal_docs
.\.venv\Scripts\python.exe -m src.task2_crawl_news
.\.venv\Scripts\python.exe -m src.task3_convert_markdown
.\.venv\Scripts\python.exe -m pytest tests/test_corpus.py tests/test_acceptance.py -q
```

Output nằm ở `data/landing/` và `data/standardized/`; chi tiết ở [`CORPUS.md`](CORPUS.md) và [`../reports/CORPUS_REPORT.md`](../reports/CORPUS_REPORT.md).

## 3. Chunk, embedding và hai đường search

Đã dùng recursive chunking 500 ký tự, overlap 50, BAAI/bge-m3 revision cố định và Chroma cosine. BM25 đọc đúng snapshot chunk của Chroma.

```powershell
.\.venv\Scripts\python.exe -m src.task4_chunking_indexing
.\.venv\Scripts\python.exe -m src.task5_semantic_search
.\.venv\Scripts\python.exe -m src.task6_lexical_search
.\.venv\Scripts\python.exe -m src.verify_retrieval
.\.venv\Scripts\python.exe -m pytest tests/test_contracts.py tests/test_retrieval.py -q
```

Index cuối có 2.079 chunk. `data/index/` và `chroma_db/` là artifact sinh lại, không cần đưa vào commit.

## 4. RRF và fallback

Task 7 gộp dense/BM25 bằng `1 / (60 + rank)`, rank bắt đầu từ 1, copy kết quả trước khi đổi score và chạy RRF đúng một lần trong Task 9. Fallback PageIndex được bọc timeout/cache/parse; lỗi provider giữ hybrid result và không làm UI crash.

```powershell
.\.venv\Scripts\python.exe -m src.task7_reranking
.\.venv\Scripts\python.exe -m src.calibrate_retrieval --threshold 0.60
.\.venv\Scripts\python.exe -m src.verify_hybrid
.\.venv\Scripts\python.exe -m pytest tests/test_hybrid.py tests/test_pageindex.py -q
```

Threshold production là `0.60`, được chọn từ probe trong chủ đề và ngoài chủ đề. A/B evaluation đặt threshold `-1.0` để không gọi fallback và chỉ đo khác biệt retrieval.

## 5. Generation và Streamlit

`src/task10_generation.py` format context có title/source/page, kiểm tra quote trong chunk, verifier claim và tự gắn citation từ `sources`. Không có evidence thì trả safe refusal với `sources=[]` và `retrieval_source="none"`.

```powershell
.\.venv\Scripts\python.exe -m src.task10_generation
streamlit run app.py
```

Kiểm tra một câu hỏi trong chủ đề và một câu hỏi ngoài corpus. UI phải hiển thị answer, citation, URL, method, score và evidence quote; lịch sử chat phải render lại được nguồn.

## 6. Evaluation A/B

Golden dataset có 17 case được tạo từ chunk thực tế. Hai cấu hình giữ nguyên corpus, generator, evaluator, prompt và `top_k=5`:

- Config A: dense-only.
- Config B: dense + BM25 + RRF.

```powershell
.\.venv\Scripts\python.exe -m src.evaluate_ab
.\.venv\Scripts\python.exe -m pytest tests/test_evaluation.py -q
```

Kết quả, delta B−A, latency, ba case kém nhất và recommendation nằm trong [`../group_project/evaluation/RESULT.md`](../group_project/evaluation/RESULT.md).

## 7. Kiểm tra trước khi nộp

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_contracts.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_acceptance.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
git diff --check
git status --short
```

Suite hiện đạt 86 test; acceptance đạt 5 test. Báo cáo cá nhân dùng tên `reports/K4-L3B-MSSV-Name.md`. Trước khi commit, kiểm tra `.env`, cache PageIndex và artifact local vẫn được Git ignore. Nhánh làm việc là `work/rag-pipeline`.
