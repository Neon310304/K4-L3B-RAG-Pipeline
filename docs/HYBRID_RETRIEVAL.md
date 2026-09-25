# RRF và fallback — Task 7–9

## Cách chạy

Yêu cầu index Task 4 đã ở trạng thái `ready`. Dense/BM25/RRF chạy local; không cần API key. `.env` có `SCORE_THRESHOLD=` để trống sẽ dùng baseline **0.60** đã đo trên snapshot NIST hiện tại.

```powershell
.\.venv\Scripts\python.exe -m src.task7_reranking
.\.venv\Scripts\python.exe -m src.task9_retrieval_pipeline "How long must a password be when used as the only authentication factor?"
.\.venv\Scripts\python.exe -m src.task9_retrieval_pipeline "How do I bake a chocolate cake?"
.\.venv\Scripts\python.exe -m src.calibrate_retrieval --threshold 0.60
.\.venv\Scripts\python.exe -m src.verify_hybrid
.\.venv\Scripts\python.exe -m pytest tests/test_contracts.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_hybrid.py tests/test_pageindex.py -q
```

Generation đã nối ở Task 10; xem cách kiểm tra citation và safe refusal trong [báo cáo generation/UI](../reports/GENERATION_REPORT.md).

## Fusion và confidence

`retrieve(query, top_k=5, score_threshold=0.60, use_reranking=True)` gọi dense và BM25, mỗi đường lấy `2 * top_k` ứng viên. `rerank_rrf` chạy **một lần**, `k=60`, rank bắt đầu từ **1**:

`score(d) = sum(1 / (60 + rank(d)))`

Tổng này bỏ qua độ lớn cosine/BM25. ID chung nhận một vote từ mỗi ranked list. ID lặp trong cùng một list bị từ chối; payload khác nhau cho cùng ID cũng bị từ chối để phát hiện snapshot lệch. Output deepcopy item/metadata, method `hybrid`, giảm dần theo score, hòa điểm theo ID, không vượt `top_k`.

Quyết định fallback đọc `max(item['score'] for item in dense)` từ list gốc. `best_dense_score >= threshold` giữ hybrid; score thấp hơn hoặc không có dense result thì thử PageIndex. Không lấy RRF score hay BM25 score để quyết định.

Nếu PageIndex trả kết quả hợp lệ, dùng kết quả đó, không RRF thêm lần nữa. Nếu PageIndex rỗng, timeout, thiếu key hoặc sai schema/thứ tự/ID trùng, giữ hybrid hiện có. Không có cả hybrid thì trả `[]`; Task 10 cần xử lý bằng safe refusal. Log chỉ ghi tên loại lỗi, không đưa response body/secret của provider vào UI.

`retrieve_with_trace()` là API bổ sung trả cả `results` và bằng chứng nhánh: `best_dense_score`, `dense_confident`, `rrf_calls`, `fallback_attempted`, `fallback_status`, `fallback_error_type`. `retrieve()` giữ nguyên signature và trả list theo contract starter. Trace `dense_confident` chỉ nói về ngưỡng similarity, **không chứng minh đủ bằng chứng để trả lời**.

`use_reranking=False` là baseline **dense-only thực sự**: chỉ gọi dense, không BM25/RRF/fallback. Với evaluation hybrid+RRF thuần, cần tắt/đo riêng fallback hoặc dùng threshold `-1` cho các query có dense result, đồng thời ghi cấu hình trong báo cáo A/B. Query rỗng hoặc `top_k <= 0` trả rỗng trước khi gọi search.

## PageIndex tùy chọn

Adapter bám các endpoint và field của package **`pageindex==0.2.8`** đã pin trong starter. Package này không truyền timeout cho requests; adapter gọi cùng REST endpoints bằng requests có connect/read timeout thay vì sửa global SDK. API hiện hành có thể thay đổi, cần kiểm tra tương thích khi có key; xem [tài liệu chính thức](https://docs.pageindex.ai/) và [changelog](https://docs.pageindex.ai/changelog).

Chưa upload tài liệu/chưa query PageIndex thật tại checkpoint này. Unit test dùng response giả lập; không được coi là bằng chứng dịch vụ cloud hoạt động.

Sau khi điền `PAGEINDEX_API_KEY` trong `.env`, có thể chủ động chạy:

```powershell
.\.venv\Scripts\python.exe -m src.task8_pageindex_vectorless --upload
.\.venv\Scripts\python.exe -m src.task8_pageindex_vectorless --query "Which authenticators provide phishing resistance?"
```

- Chỉ upload **3 PDF legal gốc**; không chuyển 5 bài viết thành PDF. Đây là phạm vi riêng của fallback, còn hybrid dùng đủ 8 tài liệu.
- Search không tự upload. `--upload` lưu từng `doc_id` ngay sau response bằng ghi file atomic vào `pageindex_doc_ids.json` đã gitignore. Cache theo ID tài liệu + SHA-256 landing và fingerprint tài khoản; cùng snapshot/tài khoản không upload lại. Thay key hoặc nội dung sẽ tạo binding mới. Không tự xóa tài liệu cloud cũ.
- Nếu tiến trình chết sau khi server nhận upload nhưng trước khi ghi cache, lần sau có thể phải xử lý tài liệu trùng trên dashboard; API starter không có idempotency key để bảo đảm exactly-once qua lỗi này.
- Kiểm tra `retrieval_ready` trước khi gửi query. Connect timeout tối đa 5 giây, read timeout tối đa 10 giây; polling dùng ngân sách 30 giây chung cho tìm kiếm. Đây là deadline kiểm tra giữa request/poll và timeout I/O, không cam kết hard wall-clock chính xác từng mili giây.
- Parse `retrieved_nodes[].relevant_contents[].page_index` (trang vật lý, bắt đầu 1). Mỗi trang phải tồn tại trong Markdown chuẩn hóa. Nội dung trả về là **văn bản trang từ corpus cục bộ**, không dùng lời diễn giải `relevant_content` của provider làm evidence.
- ID fallback: `<document_id>::pageindex-page-<page>`, `chunk_index=page-1`, có `pdf_page`, source, URL, landing/checksum. Đây là đơn vị trang, khác ID chunk 500 ký tự của dense/BM25.
- Score fallback là `1 / rank_trang` trong từng tài liệu, có metadata `score_kind`; chỉ dùng sắp thứ tự, không phải cosine hay độ tin cậy. Hòa điểm giữa tài liệu theo ID, chưa có reranker liên tài liệu. Provider chọn trang ngoài phạm vi hoặc trả schema lạ sẽ bị từ chối và pipeline giữ hybrid.

## Bằng chứng

- [Threshold calibration JSON](../reports/THRESHOLD_CALIBRATION.json): 6 query trong chủ đề, 6 ngoài chủ đề, 3 gần chủ đề nhưng thiếu bằng chứng, kèm dense top-3 và metadata.
- [Hybrid checkpoint JSON](../reports/HYBRID_CHECKPOINT.json): chạy pipeline thật trên 3 trường hợp, giữ nguồn và xác nhận nhánh.
- [Báo cáo diễn giải](../reports/HYBRID_REPORT.md): threshold, quan sát và giới hạn.

Khi đổi corpus/embedding/chunking, chạy lại index và calibration; bộ calibration nhỏ này không thay thế golden dataset độc lập để đánh giá A/B.
