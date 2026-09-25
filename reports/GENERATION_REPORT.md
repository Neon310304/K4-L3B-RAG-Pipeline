# Checkpoint generation có citation và Streamlit UI

Tôi phụ trách nối retrieval với generation, kiểm tra evidence trước khi hiển thị, và triển khai Streamlit với lịch sử chat có nguồn. Provider dispatch, safe refusal và các nhánh lỗi được kiểm thử offline; provider thật được chọn qua `.env` khi chạy triển khai.

## Luồng đã triển khai

1. `retrieve_with_trace()` trả hybrid hoặc PageIndex cùng trạng thái confidence. Query rỗng, index lỗi, không có kết quả, hoặc hybrid dưới threshold khi fallback không cung cấp nguồn sẽ đi safe refusal.
2. `reorder_for_llm()` deep-copy chunk và dùng thứ tự `[0, 2, 4, 3, 1]` cho 5 kết quả. ID, content và metadata không bị đổi hay mất.
3. `format_context()` tạo JSON context có ID ổn định, title, source, URL, page và content. Model không được tự tạo URL/citation.
4. `call_llm(system_prompt, user_message)` dispatch OpenAI Responses, Gemini `generate_content` hoặc Anthropic Messages theo `.env`. Nhánh OpenAI đọc `response.output_text` theo [tài liệu chính thức](https://developers.openai.com/api/docs/guides/text); mỗi client dùng model tường minh, timeout 40 giây, không retry tự động; hàm trả text thuần. Provider chưa cấu hình không gọi network.
5. Model phải trả JSON claim/evidence. Chương trình kiểm tra ID có trong context, quote (tối thiểu 20 ký tự) xuất hiện trong đúng content, số claim/evidence và không có link/HTML tự sinh. Một lượt verifier thứ hai kiểm tra toàn bộ claim có được nguồn hỗ trợ trực tiếp không.
6. Citation được chương trình gắn theo nguồn đã dùng: `[1]`, `[2]` map đúng thứ tự `sources`; mỗi source giữ `id`, method, score, title, source, URL và `evidence_quotes`. `GenerationResult.retrieval_source` lấy từ chính route `hybrid` hoặc `pageindex`.
7. Safe refusal luôn có `sources=[]`, `retrieval_source="none"`; lỗi provider không làm UI crash và không đưa exception body/API key vào giao diện.

## UI

`app.py` dùng `st.chat_input`, slider `top_k` 1–10, gọi `generate_with_citation(query, top_k)`, hiển thị answer, route, method, score, ID, đoạn content, evidence quote và link URL trong expander. `st.session_state.messages` lưu cả `content` và `result` đầy đủ để render lại nguồn sau mỗi rerun. Nút xóa lịch sử không xóa corpus/index.

Sidebar báo trạng thái provider/model mà không hiển thị key. Khi thiếu key/model, UI vẫn khởi động và trả refusal có lý do cấu hình; không tự dùng model khác.

## Kiểm chứng offline

- `pytest tests/test_contracts.py tests/test_generation.py tests/test_hybrid.py tests/test_pageindex.py tests/test_retrieval.py tests/test_corpus.py -q`: **78 passed**; the full repository suite is now **86 passed** after adding the golden dataset and A/B evaluation artifact.
- Test generation kiểm tra deep-copy/reorder, context có ID/title/source/page, OpenAI dispatch mock, thiếu cấu hình, refusal không có evidence, quote giả, verifier từ chối và route PageIndex.
- Streamlit AppTest render được app không exception trong môi trường headless; server thật trả `/_stcore/health` HTTP 200. Một lượt query trong chủ đề và một query làm bánh đều không crash; các nhánh provider/refusal được kiểm tra trong môi trường offline. Dòng cảnh báo `missing ScriptRunContext` chỉ xuất hiện khi AppTest chạy ngoài runtime Streamlit, không phải lỗi app.

Các test provider dùng mock, không gửi dữ liệu ra ngoài. Có thể chạy smoke test với provider/model được chọn bằng `.env`: thử một câu hỏi trong chủ đề và một câu hỏi ngoài chủ đề, kiểm tra answer có citation `[n]` và expander source tương ứng; không commit `.env`.

## Giới hạn an toàn

Citation là bằng chứng cho các claim được model trả về sau khi quote/verifier pass; nó không biến similarity thành sự thật. Query “mật khẩu email cá nhân” có thể vượt threshold nhưng corpus không chứa bí mật tài khoản, nên system prompt/verifier phải từ chối. Với tài liệu có mâu thuẫn hoặc thiếu điều kiện, câu trả lời bị từ chối thay vì tự hòa giải.

Provider SDK và model output có thể thay đổi; nếu đổi SDK, cần cập nhật adapter và mock test. Không gọi PageIndex/LLM thật trong test contract.
