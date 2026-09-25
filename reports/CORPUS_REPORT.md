# Báo cáo checkpoint dữ liệu — Lab 08

- Người phụ trách: Trần Quốc Vượng — 2A202602522.
- Nhánh: `work/rag-pipeline`.
- Ngày thu thập/kiểm chứng: 25/09/2026.
- Chủ đề: an toàn tài khoản — mật khẩu, MFA, phishing và đăng nhập liên kết.
- Trạng thái: hoàn thành checkpoint thu thập và chuẩn hóa corpus.

## Dữ liệu đầu ra

| Hạng mục | Kết quả |
|---|---|
| PDF gốc | 3 file NIST bản final Revision 4: 96, 129 và 150 trang; tổng 375 trang |
| Metadata PDF | 3 sidecar `.metadata.json` có URL, tên, phiên bản, ngày tải, quyền sử dụng và SHA-256 |
| Bài viết | 5 JSON; mỗi file có `url`, `title`, `date_crawled`, `content_markdown` |
| Độ dài body bài viết | 3.782–11.098 ký tự; không dùng metadata để đạt ngưỡng tối thiểu |
| Markdown | 3 file trong `standardized/legal`, 5 file trong `standardized/news`; tổng 891.356 byte |
| Truy vết | 8/8 Markdown có đường dẫn landing, URL và checksum; PDF giữ mốc trang vật lý |
| Cấu hình | Thu thập/chuyển đổi chạy cục bộ, không cần API key |

Danh sách đầy đủ và phạm vi sử dụng: [CORPUS.md](../docs/CORPUS.md).
Snapshot máy đọc được: [corpus_manifest.json](../data/corpus_manifest.json).

SHA-256 của corpus:

```text
c2f27eecf7515d01cfcd659154788810f38b6f7a8c7851b4fc6eb1b4171d47fa
```

## Đối chiếu nội dung mẫu

Đã xem trang PDF gốc và so với đoạn Markdown tương ứng. Với bài HTML, đối chiếu đoạn trong body trang NIST lấy trực tiếp với JSON thu thập; nội dung JSON tiếp tục được giữ trong Markdown.

| Nguồn | Vị trí / nội dung đã kiểm tra | Kết quả |
|---|---|---|
| [SP 800-63-4](../data/landing/legal/nist_sp_800_63_4.pdf#page=46) | Trang PDF 46 (trang in 36): AAL2 dùng hai yếu tố riêng biệt; bảng AAL Summary | Đoạn văn khớp; bảng đã chuyển thành 3 cột Markdown, không trộn Control Objectives và User Profile |
| [SP 800-63B-4](../data/landing/legal/nist_sp_800_63b_4.pdf#page=25) | Trang PDF 25 (trang in 14), mục 3.1.1.2: 15 ký tự khi mật khẩu là yếu tố duy nhất, tối thiểu 8 khi nằm trong MFA; quy tắc thay mật khẩu | Giữ đúng điều kiện, số và các từ chuẩn tắc, gồm SHALL NOT |
| [SP 800-63C-4](../data/landing/legal/nist_sp_800_63c_4.pdf#page=56) | Trang PDF 56 (trang in 43), mục 3.13.4 Audience Restriction | Giữ yêu cầu RP kiểm tra audience và giới hạn một audience ở FAL2 trở lên |
| [Good Password](../data/standardized/news/nist_good_password.md) | Đoạn khuyến nghị mật khẩu ít nhất 15 ký tự | Có trong trang nguồn, JSON và Markdown |
| [MFA](../data/standardized/news/nist_mfa.md) | Ba nhóm yếu tố: biết, có, thuộc về đặc điểm người dùng | Danh sách và điều kiện kết hợp từ hai yếu tố được giữ |
| [Phishing](../data/standardized/news/nist_phishing.md) | Mục xử lý sau khi bị phishing, thay mật khẩu bị ảnh hưởng | Đoạn và điều kiện trong danh sách được giữ |
| [Phishing Resistance](../data/standardized/news/nist_phishing_resistance.md) | Đoạn FIDO kết hợp Web Authentication API | Khớp nguồn; ghi nhận bài giải thích được xuất bản năm 2023 |
| [Revision 4](../data/standardized/news/nist_identity_revision4.md) | Danh sách thay đổi có syncable authenticators / synced passkeys | Khớp nguồn |

Đây là kiểm chứng mẫu, không phải tuyên bố đã duyệt thủ công từng dòng của 375 trang. Biểu đồ/ảnh không có trong Markdown; bảng không có đường kẻ hoặc có ô gộp cần đối chiếu PDF khi chọn câu hỏi đánh giá. Quyền sử dụng, nguồn lịch sử và việc loại ảnh bên thứ ba được mô tả trong `docs/CORPUS.md`.

## Kiểm thử

| Lệnh | Kết quả |
|---|---|
| `python -m pytest tests/test_corpus.py -q` | **7 passed** |
| `python -m pytest tests/test_acceptance.py -q` | **5 passed** |
| `python -m pip check` | Không phát hiện dependency bị thiếu/xung đột |

Acceptance đã bao gồm golden dataset và báo cáo A/B hoàn chỉnh ở `group_project/evaluation/RESULT.md`. Toàn bộ suite hiện đạt **86 passed**. Bảy test corpus bổ sung kiểm tra loại nội dung ngoài bài, từ chối HTML giả PDF và HTTP lỗi, hash truy vết, chạy lại ổn định, bảo toàn file tốt khi dữ liệu mới lỗi, và bảo toàn mẫu nội dung chuẩn tắc/bảng.

## Tái lập

Đã chạy lại task 1 → 2 → 3 trên bản cuối: giữ nguyên 24 file trong `data/` (bao gồm 4 `.gitkeep`), mọi đường dẫn và SHA-256 đều không đổi. Không phát sinh bản sao và các mốc ngày thu thập không bị thay bằng ngày chạy lại.

`.gitattributes` giữ LF cho JSON/Markdown và binary cho PDF. Dùng `--refresh` khi chủ động cập nhật nguồn; sau đó cần kiểm chứng lại, chạy lại index/evaluation và ghi hash corpus mới.

Môi trường chuyển đổi: Python 3.12.6; pdfplumber 0.11.10; BeautifulSoup 4.15.0; Markdownify 1.2.3; PyYAML 6.0.3.
