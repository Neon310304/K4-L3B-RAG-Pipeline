# Corpus: an toàn tài khoản

Chủ đề: mật khẩu, xác thực đa yếu tố (MFA), chống phishing và đăng nhập liên kết. Corpus giữ nguyên tiếng Anh của nguồn; không dùng LLM để viết lại hoặc bổ sung nội dung. Câu hỏi tiếng Việt có thể được dùng ở giai đoạn retrieval với embedding đa ngôn ngữ.

## Nguồn đã chọn

| ID / tên file | Nội dung | Nguồn công khai |
|---|---|---|
| `nist_sp_800_63_4` | Khung định danh số và lựa chọn mức bảo đảm | [NIST SP 800-63-4, final July 2025](https://csrc.nist.gov/pubs/sp/800/63/4/final) |
| `nist_sp_800_63b_4` | Mật khẩu, các loại authenticator, MFA, quản lý authenticator và session | [NIST SP 800-63B-4, final July 2025](https://csrc.nist.gov/pubs/sp/800/63/b/4/final) |
| `nist_sp_800_63c_4` | Federation, assertions và yêu cầu an toàn của đăng nhập liên kết | [NIST SP 800-63C-4, final July 2025](https://csrc.nist.gov/pubs/sp/800/63/c/4/final) |
| `nist_good_password` | Mật khẩu, password manager, passkey và MFA | [How Do I Create a Good Password?](https://www.nist.gov/cybersecurity-and-privacy/how-do-i-create-good-password) |
| `nist_mfa` | Ý nghĩa, lựa chọn và áp dụng MFA | [Multi-Factor Authentication](https://www.nist.gov/itl/smallbusinesscyber/guidance-topic/multi-factor-authentication) |
| `nist_phishing` | Nhận biết phishing và xử lý khi bị lừa | [Phishing](https://www.nist.gov/itl/smallbusinesscyber/guidance-topic/phishing) |
| `nist_phishing_resistance` | Vì sao cần MFA có khả năng chống phishing | [Phishing Resistance – Protecting the Keys to Your Kingdom](https://www.nist.gov/blogs/cybersecurity-insights/phishing-resistance-protecting-keys-your-kingdom) |
| `nist_identity_revision4` | Giải thích những thay đổi của Revision 4 | [Updated Digital Identity Guidelines are Here](https://www.nist.gov/blogs/cybersecurity-insights/lets-get-digital-updated-digital-identity-guidelines-are-here) |

Ba PDF được phân loại `legal` theo cấu trúc starter: đây là hướng dẫn kỹ thuật có các yêu cầu chuẩn tắc của NIST, không phải luật áp dụng chung tại Việt Nam. SP 800-63B-4 là tài liệu chính cho câu hỏi về mật khẩu/MFA; hai tập còn lại cung cấp ngữ cảnh định danh và federation. Với câu hỏi ngoài phạm vi này, chatbot cần nhận biết thiếu bằng chứng ở giai đoạn generation.

Bài phishing resistance được xuất bản năm 2023: dùng để giải thích cơ chế, không dùng các lời mời góp ý hoặc mốc lịch sử trong bài như thông báo hiện hành. Khi có khác biệt về yêu cầu kỹ thuật, ưu tiên ba bản final Revision 4 đã cố định trong corpus. Các trang CISA thử ban đầu trả 403 nên được thay bằng trang NIST; không vượt cơ chế chặn crawler.

## Quyền sử dụng và phạm vi thu thập

- [Chính sách NIST](https://www.nist.gov/copyrights-disclaimers) cho phép sao chép/phân phối thông tin công khai, ngoại trừ nội dung được đánh dấu bản quyền. [NIST Library FAQ](https://www.nist.gov/nist-research-library/library-faqs) giải thích quyền sao chép các ấn phẩm của NIST và yêu cầu ghi nguồn. Ba PDF cũng có thông báo quyền sử dụng trong phần đầu.
- Ghi nguồn NIST và URL gốc trong mọi Markdown/JSON; giữ PDF nguyên bản.
- Bài HTML chỉ lấy phần văn bản chính. Loại ảnh, credit ảnh, video, menu, bình luận, form và tiểu sử tác giả. Không tải ảnh Shutterstock hoặc sao chép nội dung ở các liên kết bên ngoài.
- Không thu thập tài khoản, mật khẩu thật, thông tin người dùng hoặc hồ sơ cá nhân. PDF nguyên bản vẫn giữ tên tác giả và trích dẫn thư mục công khai để bảo toàn nguồn.

## Cấu trúc và truy vết

```text
data/
  landing/legal/       # PDF nguyên bản + *.metadata.json
  landing/news/        # 5 JSON bài viết
  standardized/legal/ # Markdown theo trang PDF
  standardized/news/  # Markdown bài viết
  corpus_manifest.json
```

Mỗi Markdown có YAML front matter: `id`, `title`, `doc_type`, `url`, `source`, `landing_file`, `landing_sha256`, `date_crawled`, thông tin quyền sử dụng và phiên bản/ngày bài viết. Dùng `landing_file` tính từ root repo để mở bản gốc, `url` để mở nguồn công khai. PDF có mốc `## PDF page N` theo số trang vật lý, bắt đầu từ 1; số trang in trên tài liệu có thể khác.

`corpus_manifest.json` liệt kê từng cặp landing/Markdown và SHA-256 tương ứng. `corpus_sha256` nhận diện toàn bộ snapshot dùng cho index và A/B. Không đưa timestamp chạy convert vào nội dung để tránh đổi hash khi chạy lại.

## Chạy trên Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -m src.task1_collect_legal_docs
.\.venv\Scripts\python.exe -m src.task2_crawl_news
.\.venv\Scripts\python.exe -m src.task3_convert_markdown
.\.venv\Scripts\python.exe -m pytest tests/test_acceptance.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_corpus.py -q
```

Chỉ kiểm tra checkpoint dữ liệu bằng ba test có sẵn:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_acceptance.py -q -k "corpus or standardized"
```

Hai acceptance test còn lại kiểm tra golden dataset và báo cáo evaluation, thuộc giai đoạn sau. Không sửa hoặc bỏ qua các test đó để tạo kết quả đạt giả.

## Chạy lại và cập nhật nguồn

Mặc định task 1/2 kiểm tra và tái sử dụng snapshot đã lưu, không cần mạng khi đủ file. Task 3 ghi lại đúng tên file và giữ nguyên byte nếu nội dung không đổi. Dữ liệu lỗi, PDF giả HTML, hash không khớp hoặc body quá ngắn sẽ làm lệnh báo lỗi thay vì âm thầm tạo tài liệu rỗng.

Khi muốn lấy phiên bản nguồn mới, chủ động chạy task 1/2 với `--refresh`, sau đó chạy task 3 và kiểm tra diff/hash. Nếu thay danh sách nguồn, cần rà soát file cũ trước khi loại khỏi corpus; pipeline không tự xóa file. Sau mọi thay đổi corpus, chạy lại index và evaluation, đồng thời ghi hash snapshot vào kết quả A/B.

## Giới hạn chuyển đổi cần kiểm tra

PDF dùng `pdfplumber` để lấy text theo từng trang; bảng có đường kẻ được tách khỏi text và chuyển sang bảng Markdown để giữ cột. Dòng trong ô được giữ bằng `<br>`. Markdown không tái tạo ảnh/biểu đồ; bảng không có đường kẻ hoặc có ô gộp phức tạp vẫn cần đối chiếu trang PDF trước khi đưa câu hỏi phụ thuộc bảng vào golden dataset. File landing là bản gốc để kiểm chứng. DOCX có thể dùng MarkItDown khi cung cấp sidecar tương tự; DOC cũ cần đổi sang DOCX trước.

`.gitattributes` cố định LF cho mã, JSON và Markdown, đồng thời giữ PDF/DOCX ở dạng binary; việc checkout trên Windows không làm thay đổi byte của snapshot và các checksum.
