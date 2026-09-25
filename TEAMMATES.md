# Phân công thực hiện — Lab 08: RAG Pipeline

- Lớp: K4-L3B
- Repository: https://github.com/Neon310304/K4-L3B-RAG-Pipeline
- Nhánh làm việc: `work/rag-pipeline`

## Thông tin thành viên

| Họ và tên | Mã học viên | GitHub | Vai trò | Nhánh / phần việc |
|---|---|---|---|---|
| Trần Quốc Vượng | 2A202602522 | Neon310304 | Data, Retrieval, Generation/UI, Evaluation/Integration | `work/rag-pipeline` — dữ liệu, pipeline truy xuất, giao diện và đánh giá |

## Phạm vi phụ trách

| Hạng mục | Công việc phụ trách | File / đầu ra liên quan |
|---|---|---|
| Data | Tôi phụ trách lựa chọn nguồn công khai, thu thập tài liệu chính sách và bài viết, chuẩn hóa nội dung và giữ thông tin nguồn. | `src/task1_collect_legal_docs.py`, `src/task2_crawl_news.py`, `src/task3_convert_markdown.py`, `data/` |
| Retrieval | Tôi phụ trách chia đoạn, tạo embedding và index; triển khai dense search, BM25, RRF và cơ chế fallback. | `src/task4_chunking_indexing.py` đến `src/task9_retrieval_pipeline.py` |
| Generation/UI | Tôi phụ trách sinh câu trả lời có citation, xử lý khi thiếu bằng chứng và tích hợp giao diện chat Streamlit. | `src/task10_generation.py`, `app.py` |
| Evaluation/Integration | Tôi phụ trách tích hợp các module, xây dựng bộ câu hỏi, kiểm thử, so sánh dense-only với hybrid + RRF và tổng hợp báo cáo. | `tests/`, `group_project/evaluation/`, `reports/` |

## Cách theo dõi công việc

- Triển khai theo thứ tự: dữ liệu → truy xuất → generation và giao diện → đánh giá.
- Ghi nhận phần việc bằng file, commit và kết quả chạy thực tế.
- Cập nhật báo cáo khi có kết quả kiểm chứng; bảng trên mô tả trách nhiệm được phân công.
- Cấu hình provider và API key trong `.env` cục bộ; không đưa thông tin bí mật vào repository.
- Báo cáo đóng góp: [`reports/K4-L3B-2A202602522-Tran-Quoc-Vuong.md`](reports/K4-L3B-2A202602522-Tran-Quoc-Vuong.md).
