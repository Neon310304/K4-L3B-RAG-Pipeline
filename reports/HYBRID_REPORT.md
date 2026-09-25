# Checkpoint RRF và fallback

Tôi phụ trách hợp nhất dense/BM25 bằng RRF, nối nhánh fallback, kiểm thử lỗi provider và hiệu chỉnh threshold trên corpus an toàn tài khoản. Phần này tiếp nối [checkpoint Task 4–6](RETRIEVAL_REPORT.md).

## Cấu hình thực dùng

| Thành phần | Giá trị |
|---|---|
| Corpus | 3 PDF NIST + 5 page, 8 document, 2.079 chunk |
| Chunking | Recursive, 500/50 ký tự, giữ trang PDF |
| Embedding | BAAI/bge-m3, revision `5617a9f61b028005a4858fdac845db406aefb181`, 1024 chiều |
| Dense | Chroma HNSW cosine, `score = 1 - distance` |
| BM25 | `k1=1.5`, `b=0.75`, positive IDF |
| Candidates / output | 10 mỗi đường / top-5 |
| RRF | `k=60`, rank từ 1, một lần trong pipeline |
| SCORE_THRESHOLD | **0.60**, thấp hơn mới thử fallback |
| Fallback | PageIndex tùy chọn; adapter upload/cache/timeout/parse và kiểm thử offline đã hoàn tất |

Corpus hash `c2f27eecf7515d01cfcd659154788810f38b6f7a8c7851b4fc6eb1b4171d47fa`; chunk hash `bbd6720bc526a569c5c2c8790feddbaca37e0fd23601f4feb60d7051364146ec`.

## Hiệu chỉnh threshold

Bộ probe được khai báo trong `src/calibrate_retrieval.py`: 6 câu trong chủ đề, 6 câu ngoài chủ đề và 3 câu gần chủ đề nhưng không có câu trả lời trong corpus. Không dùng golden dataset để chọn threshold và chưa coi đây là evaluation độc lập.

Cosine thấp nhất của 6 query trong chủ đề là **0.641948**, cao nhất của 6 query ngoài chủ đề là **0.527470**. Chọn **0.60** nằm trong khoảng tách được hai tập nhỏ này `(0.527470, 0.641948]`, thay cho mặc định starter 0.3. Không tuyên bố 0.60 đúng cho corpus hoặc embedding khác.

| Nhãn | Query | Best cosine | Nhánh dự kiến |
|---|---|---:|---|
| Trong chủ đề | How long must a password be when used as the only authentication factor? | 0.704705 | Hybrid |
| Trong chủ đề | Mật khẩu dùng làm yếu tố xác thực duy nhất cần dài tối thiểu bao nhiêu ký tự? | 0.660668 | Hybrid |
| Trong chủ đề | What are the three types of authentication factors? | 0.804356 | Hybrid |
| Trong chủ đề | NIST SP 800-63B-4 phishing resistance | 0.715893 | Hybrid |
| Trong chủ đề | Tôi cần làm gì sau khi bị lừa đảo phishing? | 0.878705 | Hybrid |
| Trong chủ đề | audience restriction FAL2 assertions | 0.641948 | Hybrid |
| Ngoài chủ đề | How do I bake a chocolate cake? | 0.392158 | Thử fallback |
| Ngoài chủ đề | Cách nấu phở bò tại nhà như thế nào? | 0.357850 | Thử fallback |
| Ngoài chủ đề | What is the capital of Australia? | 0.372721 | Thử fallback |
| Ngoài chủ đề | Explain photosynthesis in plants. | 0.527470 | Thử fallback |
| Ngoài chủ đề | Giải phương trình bậc hai x^2 - 5x + 6 = 0. | 0.411916 | Thử fallback |
| Ngoài chủ đề | How do I replace a bicycle tire? | 0.456342 | Thử fallback |
| Gần chủ đề, thiếu bằng chứng | What is the password of my personal email account? | 0.634218 | Hybrid — không thể trả lời bằng corpus |
| Gần chủ đề, thiếu bằng chứng | What exact buttons should I press to enable MFA in the current Instagram app? | 0.589041 | Thử fallback |
| Gần chủ đề, thiếu bằng chứng | Which password manager has the cheapest family subscription today? | 0.508699 | Thử fallback |

Query về quang hợp có top cosine tương đối cao dù ngoài chủ đề, cho thấy similarity không phải xác suất đúng. Đặc biệt, query mật khẩu tài khoản cá nhân vượt threshold nhưng không thể có đáp án từ tài liệu NIST. **Generation phải kiểm tra nội dung evidence và từ chối khi thiếu; không coi việc đi nhánh hybrid là đủ điều kiện trả lời.**

Toàn bộ score chưa làm tròn, top-3 chunk và nguồn: [THRESHOLD_CALIBRATION.json](THRESHOLD_CALIBRATION.json). Tái lập bằng `python -m src.calibrate_retrieval --threshold 0.60`.

## Kiểm chứng pipeline thật

`python -m src.verify_hybrid` dùng index thật, không giả lập response provider:

1. Câu hỏi độ dài mật khẩu: cosine **0.704705**, RRF **1 lần**, không gọi fallback, trả 5 hybrid result đúng nguồn.
2. Câu hỏi làm bánh: cosine **0.392158**, RRF **1 lần**, thử fallback; thiếu key gây `PageIndexNotConfigured`, pipeline **giữ 5 hybrid result và không crash**. Các đoạn đó không phải bằng chứng trả lời câu hỏi làm bánh.
3. Câu hỏi mật khẩu email cá nhân: cosine **0.634218**, RRF **1 lần**, không gọi fallback. Đây là quan sát hạn chế của threshold, không phải ví dụ trả lời thành công.

Bằng chứng: [HYBRID_CHECKPOINT.json](HYBRID_CHECKPOINT.json). Metadata/content của hybrid được so chính xác với các chunk nguồn; output không trùng ID và không quá top-5.

## Kiểm thử ngày 2026-09-25

| Lệnh / phạm vi | Kết quả |
|---|---|
| `python -m src.task7_reranking` | Demo ID b nhận `1/62 + 1/61 = 0.03252247488101534` |
| `pytest tests/test_hybrid.py tests/test_pageindex.py tests/test_contracts.py tests/test_generation.py -q` | **78 passed** |
| `pytest -q` | **86 passed** |

Test mới xác nhận công thức/rank, deep copy metadata, hòa điểm ổn định, từ chối ID trùng upstream và score không hữu hạn; routing dùng cosine gốc, đúng boundary, RRF một lần; fallback thành công/rỗng/timeout/sai schema; dense-only không gọi BM25/fallback. Adapter test kiểm tra upload cache/hash/tài khoản, yêu cầu upload trước, timeout/polling và đối chiếu page với nội dung local. Tất cả test này chạy offline, không gọi API thật.

Golden dataset và `group_project/evaluation/RESULT.md` hiện đã hoàn thiện ở pha evaluation; các invariant được kiểm tra thêm trong `tests/test_evaluation.py`.

## Phạm vi PageIndex và việc còn lại

Đã viết adapter upload/cache/timeout/parse cho API của starter `pageindex==0.2.8`; contract test chạy offline, còn smoke test dịch vụ cloud là bước tùy chọn khi provider được cấu hình. Fallback chỉ chọn trang của 3 PDF legal và trả nội dung từ bản chuẩn hóa local; hybrid dùng đủ 8 tài liệu. Chi tiết cache, giới hạn timeout, score trang và lệnh kích hoạt có trong [hướng dẫn](../docs/HYBRID_RETRIEVAL.md).

Generation/citation/UI đã được nối ở Task 10; báo cáo riêng ở [GENERATION_REPORT.md](GENERATION_REPORT.md). A/B dense-only so với hybrid + RRF đã chạy và được ghi trong báo cáo evaluation; kết quả lần chạy hiện tại không cho thấy hybrid vượt dense-only trên average. Smoke test PageIndex cloud vẫn là bước tùy chọn riêng, cần ghi nhận lại nếu được chạy.
