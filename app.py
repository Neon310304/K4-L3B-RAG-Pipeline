"""Streamlit UI for the grounded account-security RAG assistant."""

import streamlit as st
from dotenv import load_dotenv

from src.task10_generation import generate_with_citation, llm_configuration_status

load_dotenv()

st.set_page_config(page_title="Account Safety RAG", page_icon="", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []


def render_sources(result: dict) -> None:
    sources = result.get("sources", [])
    route = result.get("retrieval_source", "none")
    if not sources:
        st.caption(f"Nguồn truy xuất: {route} · Không có chunk được dùng.")
        return
    st.caption(f"Nguồn truy xuất: **{route}** · {len(sources)} nguồn đã dùng trong câu trả lời")
    for index, source in enumerate(sources, 1):
        metadata = source["metadata"]
        title = metadata.get("title", metadata.get("source", "Unknown source"))
        page = metadata.get("pdf_page")
        location = f" · PDF page {page}" if page else ""
        label = f"[{index}] {title} · {metadata.get('source', 'unknown')}{location}"
        with st.expander(label):
            st.caption(f"ID: `{source['id']}` · method: `{source['retrieval_method']}` · score: `{source['score']:.6f}`")
            if metadata.get("url"):
                st.markdown(f"[Mở nguồn công khai]({metadata['url']})")
            st.markdown(source["content"])
            quotes = source.get("evidence_quotes", [])
            if quotes:
                st.markdown("**Đoạn evidence dùng:**")
                for quote in quotes:
                    st.info(quote)


with st.sidebar:
    st.title("Account Safety RAG")
    st.caption("Mật khẩu · MFA · phishing")
    top_k = st.slider("Số chunks truy xuất", min_value=1, max_value=10, value=5)
    status = llm_configuration_status()
    if status["ready"]:
        st.success(f"LLM: {status['provider']} / {status['model']}")
    else:
        st.warning("Chưa cấu hình LLM_API key/model; hệ thống sẽ safe refusal.")
    if st.button("Xóa lịch sử"):
        st.session_state.messages = []
        st.rerun()

st.title("Trợ lý an toàn tài khoản")
st.caption("Câu trả lời chỉ dùng tài liệu NIST đã thu thập; mỗi nguồn hiển thị bên dưới map trực tiếp về chunk đã dùng.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            render_sources(message.get("result", {"sources": [], "retrieval_source": "none"}))

query = st.chat_input("Ví dụ: Mật khẩu dùng làm yếu tố duy nhất cần dài bao nhiêu ký tự?")
if query:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)
    with st.chat_message("assistant"):
        with st.spinner("Đang tìm evidence và kiểm tra citation..."):
            result = generate_with_citation(query, top_k=top_k)
        st.markdown(result["answer"])
        render_sources(result)
    st.session_state.messages.append({"role": "assistant", "content": result["answer"], "result": result})
