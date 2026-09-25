# K4-L3B RAG Pipeline — Account Safety

Chatbot hỏi đáp RAG về **an toàn tài khoản**: mật khẩu, MFA, phishing và đăng nhập liên kết. Pipeline giữ nguồn từ corpus đến câu trả lời, kết hợp dense retrieval với BM25/RRF, có fallback PageIndex tùy chọn, citation kiểm chứng được và báo cáo A/B giữa dense-only và hybrid.

## Trạng thái hiện tại

- Corpus: 3 tài liệu NIST dạng PDF và 5 bài viết công khai, tổng 8 document.
- Index: 2.079 chunk, recursive chunking 500/50, BAAI/bge-m3 local, vector 1024 chiều.
- Retrieval: Chroma cosine + BM25 + RRF `k=60`, `top_k=5`, threshold production `0.60`.
- Generation: OpenAI Responses, Gemini hoặc Anthropic qua cùng một adapter; citation map về `SearchResult` và safe refusal khi thiếu evidence.
- UI: Streamlit chat có lịch sử, nguồn, URL, retrieval method, score và evidence quote.
- Evaluation: 17 golden cases; A/B và bốn metric được ghi trong `group_project/evaluation/RESULT.md`.
- Kiểm thử cuối: `86 passed`.

## Cài đặt

Yêu cầu Python 3.10–3.13, Git và trình duyệt Chromium. Trên Windows PowerShell:

```powershell
git clone https://github.com/Neon310304/K4-L3B-RAG-Pipeline.git
cd K4-L3B-RAG-Pipeline
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
```

`.env.example` mô tả các biến cấu hình provider/model. `.env` là cấu hình cục bộ và đã được ignore bởi Git; chọn một provider trước khi chạy generation thật. Corpus, embedding local, retrieval, evaluation offline và test không phụ thuộc vào việc ghi secret vào repository.

## Chạy pipeline

### Thu thập và chuẩn hóa corpus

```powershell
.\.venv\Scripts\python.exe -m src.task1_collect_legal_docs
.\.venv\Scripts\python.exe -m src.task2_crawl_news
.\.venv\Scripts\python.exe -m src.task3_convert_markdown
```

Nguồn được lưu ở `data/landing/`, bản Markdown chuẩn hóa ở `data/standardized/`. Xem manifest và provenance trong [`docs/CORPUS.md`](docs/CORPUS.md) và [`reports/CORPUS_REPORT.md`](reports/CORPUS_REPORT.md).

### Chunk, index và retrieval

```powershell
.\.venv\Scripts\python.exe -m src.task4_chunking_indexing
.\.venv\Scripts\python.exe -m src.task5_semantic_search
.\.venv\Scripts\python.exe -m src.task6_lexical_search
.\.venv\Scripts\python.exe -m src.task7_reranking
.\.venv\Scripts\python.exe -m src.verify_retrieval
.\.venv\Scripts\python.exe -m src.calibrate_retrieval --threshold 0.60
.\.venv\Scripts\python.exe -m src.verify_hybrid
```

Task 4 ghi snapshot chunk vào `data/index/` và index vector vào `chroma_db/`. Hai đường search dùng cùng chunk ID và metadata. Task 7 chỉ fusion một lần; Task 9 quyết định fallback bằng cosine score gốc của dense, không dùng RRF score.

### Generation và UI

```powershell
.\.venv\Scripts\python.exe -m src.task10_generation
streamlit run app.py
```

Trong UI, nhập câu hỏi thuộc chủ đề để xem câu trả lời cùng citation `[n]`, source, URL, method, score và quote. Với câu hỏi ngoài corpus hoặc thiếu evidence, hệ thống giữ an toàn bằng fallback/refusal thay vì tự tạo nguồn.

### Evaluation A/B

```powershell
.\.venv\Scripts\python.exe -m src.evaluate_ab
```

Lệnh chạy cùng 17 golden cases cho:

- **Config A:** dense-only.
- **Config B:** dense + BM25 + một lượt RRF.

Generator, evaluator, prompt, corpus snapshot và `top_k=5` được giữ nguyên. Kết quả chi tiết nằm trong [`group_project/evaluation/RESULT.md`](group_project/evaluation/RESULT.md), dữ liệu máy đọc trong [`reports/AB_RESULTS.json`](reports/AB_RESULTS.json).

## Kiến trúc

```text
Corpus sources
    │ task1–3
    ▼
Standardized Markdown ──► chunk + embedding ──► Chroma dense search
                                      └───────► BM25 lexical search
                                                     │
                                      dense score ────┤ threshold
                                                     ▼
                                              RRF fusion once
                                                     │
                                  low confidence ─► PageIndex (optional)
                                                     │
                                                     ▼
                                  context + verifier + citations
                                                     │
                                                     ▼
                                              Streamlit chat UI
```

## Cấu trúc chính

| Đường dẫn | Vai trò |
| --- | --- |
| `src/task1_collect_legal_docs.py` – `task3_convert_markdown.py` | Thu thập và chuẩn hóa corpus |
| `src/task4_chunking_indexing.py` – `task6_lexical_search.py` | Chunk, embedding, Chroma và BM25 |
| `src/task7_reranking.py` – `task9_retrieval_pipeline.py` | RRF, PageIndex adapter và fallback |
| `src/task10_generation.py` | Context, provider dispatch, verifier và citation |
| `app.py` | Streamlit UI |
| `group_project/evaluation/` | Golden dataset và báo cáo A/B |
| `docs/` | Contract, hướng dẫn và quyết định kỹ thuật |
| `reports/` | Checkpoint, manifest và kết quả tái lập |

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_acceptance.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Acceptance hiện đạt **5 passed**; toàn bộ suite đạt **86 passed**. Test provider/PageIndex dùng mock hoặc adapter offline để kiểm tra contract, timeout, citation, refusal và lỗi provider mà không làm UI crash.

## Tài liệu và bằng chứng

- [Corpus và provenance](docs/CORPUS.md) · [checkpoint corpus](reports/CORPUS_REPORT.md)
- [Module contracts](docs/MODULE_CONTRACTS.md) · [retrieval design](docs/RETRIEVAL.md) · [retrieval checkpoint](reports/RETRIEVAL_REPORT.md)
- [Hybrid, RRF và fallback](docs/HYBRID_RETRIEVAL.md) · [hybrid checkpoint](reports/HYBRID_REPORT.md)
- [Generation và UI checkpoint](reports/GENERATION_REPORT.md)
- [Golden dataset](group_project/evaluation/golden_dataset.json) · [A/B report](group_project/evaluation/RESULT.md)
- [Rubric](docs/GRADING_RUBRIC.md) · [phân công](TEAMMATES.md) · [báo cáo đóng góp](reports/K4-L3B-2A202602522-Tran-Quoc-Vuong.md)

## Trước khi push

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
```

Không đưa `.env`, API key, `chroma_db/`, `data/index/` hoặc cache PageIndex vào commit. Nhánh làm việc hiện tại là `work/rag-pipeline`; sau khi review diff và test, có thể commit rồi push nhánh này lên remote.

## Nộp trên VLearn

Nộp URL repository của nhánh/commit cuối theo cấu trúc root hiện có. Báo cáo cá nhân dùng tên `reports/K4-L3B-MSSV-Name.md`; báo cáo của thành viên hiện tại là [`K4-L3B-2A202602522-Tran-Quoc-Vuong.md`](reports/K4-L3B-2A202602522-Tran-Quoc-Vuong.md).

Trước khi nộp, chạy đúng ba checkpoint:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_contracts.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_acceptance.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Demo cần có một câu hỏi trong chủ đề, một câu hỏi ngoài corpus và màn hình A/B trong [`group_project/evaluation/RESULT.md`](group_project/evaluation/RESULT.md). Citation trên UI phải mở được source thuộc chính `sources` của câu trả lời.
