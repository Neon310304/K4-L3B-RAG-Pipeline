# Checkpoint Task 4–6

Tôi phụ trách load/chunk, embedding, index ChromaDB, dense retrieval, BM25 và kiểm tra nguồn qua từng bước. Corpus là an toàn tài khoản: mật khẩu, MFA, phishing; 3 PDF NIST và 5 page công khai đã chuẩn hóa.

## Kết quả trên index thật

- 8 document → **2.079 chunk**, dense và BM25 dùng cùng snapshot.
- Recursive chunking **500 ký tự / overlap 50**, tách theo trang PDF; giữ baseline để định vị nguồn dễ kiểm tra. Đây là cấu hình thực dùng trong golden evaluation, không phải cấu hình tối ưu cho mọi corpus.
- Embedding local **BAAI/bge-m3**, revision `5617a9f61b028005a4858fdac845db406aefb181`, **1.024 chiều**, normalized, CPU, không cần API key.
- Chroma persistent cosine; score dense là `1 - distance`. BM25 positive IDF, `k1=1.5`, `b=0.75`, truy vấn tiêu đề + nội dung.
- Lần reindex có bằng chứng JSON: vẫn **2.079 record**, tái sử dụng 2.079 vector, embed mới **0**, thời gian **7,783 giây**. ID/content/metadata giữ nguyên; chênh lệch vector lớn nhất **1,49e-8**, dưới tolerance **1e-6** cho float32.
- Độ dài chunk: min 3, median 444, p95 495, max 500 ký tự. Chunk rất ngắn còn tồn tại ở biên trang/heading; chưa lọc tùy tiện để tránh thay corpus trong evaluation.

Chi tiết máy đo, từng truy vấn, metadata và kết quả: [RETRIEVAL_CHECKPOINT.json](RETRIEVAL_CHECKPOINT.json). Script tái lập: `python -m src.verify_retrieval`.

## Đối chiếu nguồn

Câu “How long must a password be when used as the only authentication factor?” trả dense top-1 `nist-sp800-63b-4::chunk-114`, cosine **0,704705**, PDF page **25**, có yêu cầu tối thiểu 15 ký tự. Metadata chỉ về `data/standardized/legal/nist_sp_800_63b_4.md`, `data/landing/legal/nist_sp_800_63b_4.pdf` và URL công khai NIST. Bản hỏi tiếng Việt tìm được cùng vùng trang 25, top-1 cosine **0,660668**.

Query “What are the three types of authentication factors?” có cùng top-1 ở dense và BM25: `nist-sp800-63b-4::chunk-615`, PDF page **114**. Với query tiếng Việt thuần về độ dài mật khẩu, BM25 trả rỗng vì corpus tiếng Anh; dense vẫn có kết quả. Vì vậy không coi hai đường tương đương và không cộng trực tiếp score.

Các query probe chỉ kiểm tra khả năng truy xuất/contract; chưa phải đo Recall@k, MRR hay bằng chứng hybrid tốt hơn dense-only. Xem [cấu hình và cách chạy](../docs/RETRIEVAL.md), [báo cáo fusion/fallback](HYBRID_REPORT.md) cho pha tiếp theo.

## Snapshot

Corpus SHA-256: `c2f27eecf7515d01cfcd659154788810f38b6f7a8c7851b4fc6eb1b4171d47fa`.

Chunk SHA-256: `bbd6720bc526a569c5c2c8790feddbaca37e0fd23601f4feb60d7051364146ec`.

Khi thay corpus, model, preprocessing hoặc chunking cần reindex, hiệu chỉnh lại threshold và chạy lại evaluation. Giới hạn hiện tại: chunk theo ký tự có thể tách quy tắc/bảng; overlap không vượt trang; dense HNSW là tìm kiếm gần đúng; BM25 chưa dịch query.
