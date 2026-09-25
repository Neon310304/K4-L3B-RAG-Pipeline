# Báo cáo đóng góp — Trần Quốc Vượng

## Thông tin

- Họ và tên: Trần Quốc Vượng
- Mã học viên: 2A202602522
- Lớp: K4-L3B
- Repository: `Neon310304/K4-L3B-RAG-Pipeline`
- Nhánh: `work/rag-pipeline`

## Phần việc đã thực hiện

| Hạng mục | Đóng góp trực tiếp | Bằng chứng | Trạng thái |
| --- | --- | --- | --- |
| Data | Chọn chủ đề an toàn tài khoản, thu thập 3 PDF NIST và 5 bài viết, chuẩn hóa Markdown và provenance/checksum. | `src/task1_collect_legal_docs.py` – `src/task3_convert_markdown.py`, `data/`, `reports/CORPUS_REPORT.md` | Hoàn thành |
| Retrieval | Xây chunk 500/50, embedding BGE-M3, Chroma dense search, BM25, RRF, threshold và fallback adapter. | `src/task4_chunking_indexing.py` – `src/task9_retrieval_pipeline.py`, `reports/HYBRID_REPORT.md` | Hoàn thành |
| Generation/UI | Nối context với provider dispatch, verifier, citation có quote và safe refusal; hoàn thiện Streamlit chat. | `src/task10_generation.py`, `app.py`, `reports/GENERATION_REPORT.md` | Hoàn thành |
| Evaluation/Integration | Tạo 17 golden cases, chạy A/B dense-only và hybrid + RRF, kiểm thử end-to-end và tổng hợp failure analysis. | `src/evaluate_ab.py`, `group_project/evaluation/`, `tests/`, `reports/RESULT.md` | Hoàn thành |

## Quyết định kỹ thuật

1. **Giữ chunk recursive 500/50 và embedding local BAAI/bge-m3.** Cấu hình giữ được ngữ cảnh quanh điểm cắt, hỗ trợ câu hỏi tiếng Anh và tiếng Việt, đồng thời không phụ thuộc dịch vụ embedding ngoài. Snapshot cuối có 2.079 chunk và hash được ghi trong các checkpoint retrieval.

2. **Dùng RRF theo rank và đặt threshold trên dense cosine gốc.** Dense/BM25 có thang điểm khác nhau nên RRF dùng `1/(60+rank)` một lần; fallback chỉ dựa trên best dense score. Probe trong/ngoài chủ đề tách được quanh threshold `0.60`, còn A/B đặt `-1.0` để cô lập retrieval strategy.

## Kiểm thử và kết quả

- `pytest -q`: **86 passed**.
- `pytest tests/test_acceptance.py -q`: **5 passed**.
- Streamlit health endpoint: HTTP 200; AppTest không exception cho query trong và ngoài chủ đề.
- Evaluation có đủ faithfulness, answer relevance, context recall, context precision, delta B−A, latency và ba worst performers.

## Hạn chế và bước tiếp theo

- Điểm evaluation hiện dùng generator extractive và evaluator token overlap deterministic; cần chạy thêm controlled smoke test với provider/model được chọn nếu muốn đo generation thật.
- PageIndex cloud có adapter và test lỗi/timeout offline; smoke test dịch vụ thật là bước tùy chọn, không ảnh hưởng đường hybrid local.
- Context precision còn thấp ở một số case; bước tiếp theo là thử candidate/top-k khác trên cùng golden dataset và giữ nguyên generator để kiểm chứng tác động retrieval.

