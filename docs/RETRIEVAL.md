# Chunk, embedding và hai đường tìm kiếm

Task 4–6 dùng chung corpus đã chuẩn hóa, là đầu vào của [RRF và fallback](HYBRID_RETRIEVAL.md) ở Task 7–9. Cấu hình dưới đây là baseline kiểm chứng được, chưa được tuyên bố tối ưu qua evaluation.

## Cấu hình và lựa chọn

| Thành phần | Giá trị |
|---|---|
| Chunking | RecursiveCharacterTextSplitter, `len` theo ký tự |
| Chunk size / overlap | 500 / 50 ký tự |
| Phân tách | Đoạn văn → dòng → câu → khoảng trắng → ký tự |
| PDF | Chia riêng từng trang, giữ `pdf_page` theo trang vật lý |
| Embedding | `BAAI/bge-m3`, local Sentence Transformers, CPU |
| Model revision | `5617a9f61b028005a4858fdac845db406aefb181` |
| Dimension / normalization | 1024 / L2-normalized |
| Batch / giới hạn encoder | 16 / 512 tokens; từ chối đầu vào quá dài, không cắt ngầm |
| Chroma | Persistent `chroma_db/`, collection `rag_documents`, HNSW cosine |
| Dense score | `1 - cosine_distance`, chặn sai số vào [-1, 1] |
| BM25 | Okapi TF/length, `k1=1.5`, `b=0.75`, positive IDF kiểu Lucene |
| BM25 tokenizer | NFKC, casefold, Unicode words; giữ mã ghép `800-63b-4` và các thành phần |
| BM25 fields | Tiêu đề tài liệu + nội dung chunk; trả nguyên chunk gốc |

Giữ 500/50 để có baseline gọn, dễ chỉ về một đoạn/trang nguồn và bám starter. Overlap giảm mất nội dung tại điểm cắt nhưng làm tăng số đoạn; overlap thực tế tùy separator và không vượt ranh giới trang. Quy tắc dài hoặc bảng có thể trải nhiều chunk, nên khi xây dựng generation/evaluation cần kiểm tra việc lấy các đoạn liên quan. Đây là cấu hình được dùng trong A/B evaluation; các tham số chưa được tuyên bố tối ưu cho corpus khác.

[BGE-M3 model card](https://huggingface.co/BAAI/bge-m3) mô tả model đa ngôn ngữ, vector 1024 chiều và không cần thêm instruction vào query. Vì corpus tiếng Anh và có câu hỏi tiếng Việt, dùng model này theo cấu hình `.env` hiện có. Task 4 và Task 5 gọi đúng cùng `embed_texts()`; không dùng encoder mặc định của Chroma. Local model được nạp một lần mỗi tiến trình và không cần API key.

Hàm IDF dùng `log(1 + (N - df + 0.5)/(df + 0.5))`, theo [Lucene BM25Similarity](https://lucene.apache.org/core/9_12_1/core/org/apache/lucene/search/similarities/BM25Similarity.html). Cách này giữ trọng số dương cả trong corpus rất nhỏ, tránh trường hợp IDF bằng 0 cho mọi từ trong fixture hai tài liệu. BM25 không dịch tiếng Việt sang tiếng Anh; hai đường có điểm mạnh khác nhau. Score BM25 không phải xác suất và không so sánh trực tiếp với cosine.

## Identity và metadata

`load_documents()` kiểm tra danh sách file/checksum theo corpus manifest, đọc YAML front matter, lấy `id` nguồn ổn định, giữ URL và đường dẫn landing/standardized trong metadata. YAML, hash và dòng tiêu đề lặp không được nhúng vào nội dung embedding. Các running header NIST/footer số trang được bỏ ở bước chunk, không sửa corpus gốc.

ID chunk: `<document_id>::chunk-<chunk_index>`. Metadata luôn có `source`, `title`, `doc_type`, `url`, `chunk_index`; bổ sung `document_id`, `standardized_file`, `standardized_sha256`, `landing_file`, `landing_sha256`, `pdf_page` khi có. Với metadata URL `None`, Chroma bỏ giá trị null khi ghi và khôi phục khi đọc để giữ contract.

BM25 đọc trực tiếp các record từ Chroma sau khi index sẵn sàng, kiểm tra hash toàn bộ snapshot và cache theo hash. Khi index thay đổi, BM25 xây lại. Hai đường trả cùng ID/content/metadata từ tập chunk đã index; sort giảm dần theo score, tie theo ID, không quá `top_k`. Query trống hoặc `top_k <= 0` trả `[]`; BM25 không có từ khớp cũng trả `[]`.

## Chạy và kiểm tra

```powershell
.\.venv\Scripts\python.exe -m src.task4_chunking_indexing
.\.venv\Scripts\python.exe -m src.task5_semantic_search
.\.venv\Scripts\python.exe -m src.task6_lexical_search
.\.venv\Scripts\python.exe -m src.task5_semantic_search "Mật khẩu cần dài tối thiểu bao nhiêu ký tự?" --top-k 3
.\.venv\Scripts\python.exe -m src.task6_lexical_search "NIST SP 800-63B-4 phishing resistance" --top-k 3
.\.venv\Scripts\python.exe -m pytest tests/test_contracts.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_retrieval.py -q
.\.venv\Scripts\python.exe -m src.verify_retrieval
```

`verify_retrieval` chạy trên index thật, so toàn bộ ID/content/metadata chính xác và vector với sai số float32 tối đa `1e-6` trước/sau khi index lại. Chroma có thể chuẩn hóa lại vector khi upsert với cosine; vì vậy không đòi hỏi vector float32 giống từng bit. Lệnh cũng xác nhận tập chunk BM25 bằng tập dense, kiểm tra schema cho 6 query tiếng Anh/Việt và ghi `reports/RETRIEVAL_CHECKPOINT.json`. Đây là checkpoint tích hợp, không phải A/B benchmark.

Task 4 ghi `data/index/chunks.json` và `data/index/index_summary.json` để mở kiểm tra. Các file sinh lại được và database không commit; corpus và báo cáo bằng chứng được lưu trong Git.

## Chạy lại và thay đổi cấu hình

Task 4 tái sử dụng embedding nếu ID và nội dung chưa đổi, nhưng vẫn upsert metadata hiện tại. `index_to_vectorstore()` nhận **toàn bộ snapshot**, upsert theo ID, rồi xóa các ID không còn trong snapshot để tránh chunk cũ. Không dùng hàm này để thêm riêng một phần corpus. Snapshot rỗng, ID trùng, vector không hữu hạn/sai dimension bị từ chối trước khi ghi.

Trong khi ghi, collection có trạng thái `building`; khi hoàn thành mới chuyển sang `ready`. Nếu lỗi giữa chừng, search báo index chưa hoàn tất thay vì dùng dữ liệu trộn. Chạy lại Task 4 để phục hồi. Chạy index tuần tự, không chạy nhiều tiến trình ghi cùng collection đồng thời.

Provider/model/revision/dimension/normalization/token limit được ghi cùng collection. Nếu cấu hình embedding khác, chương trình yêu cầu dùng collection mới bằng `CHROMA_COLLECTION` rồi reindex; ngay cả đổi model có cùng dimension cũng bị phát hiện. Bản này triển khai provider local `sentence_transformers`; provider khác được báo rõ là chưa hỗ trợ thay vì tự gọi dịch vụ trả phí. Khi chọn local model khác, cần cung cấp `EMBEDDING_REVISION`, `EMBEDDING_DIM` và chọn giới hạn token phù hợp trong mã.

Tham khảo API: [Chroma collection configuration](https://docs.trychroma.com/docs/collections/configure), [query/get](https://docs.trychroma.com/docs/querying-collections/query-and-get), [SentenceTransformer](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html).
