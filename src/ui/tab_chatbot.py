"""
Tab Chatbot — Isolated Component: Giao diện hội thoại AI Cố Vấn XAUUSD.

Component-Based Architecture:
  - File này chỉ chứa logic HIỂN THỊ chatbot (UI layer).
  - Giao tiếp với business logic qua dependency injection (tham số orchestrator).
  - KHÔNG import trực tiếp orchestrator — nhận qua hàm render().
  - Có thể thêm/rút component mà không ảnh hưởng tab khác (Loosely Coupled).
"""

import re
import streamlit as st

# Plotly là optional
try:
    import plotly.graph_objects as go
    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False

from src.config import Config


# =============================================================================
# PUBLIC API — Được gọi từ app.py Main Shell
# =============================================================================
def render(orchestrator, feature_flags: dict):
    """
    Render toàn bộ giao diện Chatbot trong tab hiện tại.

    Args:
        orchestrator: RAGOrchestrator instance (dependency injection)
        feature_flags: Dict {self_correction, reranker, query_rewriting}
    """
    # ── Hiển thị lịch sử chat ────────────────────────────────────────────
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and "intent" in msg:
                st.markdown(_render_badge(msg["intent"]), unsafe_allow_html=True)
            st.markdown(msg["content"])

            if msg["role"] == "assistant":
                _render_sources(msg.get("sources", []))
                metrics = _extract_metrics(msg["content"])
                if metrics:
                    _render_trade_chart(metrics)

    # ── Chat Input & Xử lý ──────────────────────────────────────────────
    if user_query := st.chat_input("Hỏi về xu hướng vàng, chiến lược SMC, dữ liệu vĩ mô..."):

        # Hiển thị tin nhắn user
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        # Xây dựng chat history
        chat_history = st.session_state.messages[-(Config.MEMORY_WINDOW * 2):]

        # Xử lý RAG pipeline
        with st.chat_message("assistant"):
            try:
                Config.ENABLE_QUERY_REWRITING = feature_flags["query_rewriting"]

                stream, sources, intent = orchestrator.query_financial_advisor(
                    user_query,
                    chat_history=chat_history,
                    enable_self_correction=feature_flags["self_correction"],
                    enable_reranker=feature_flags["reranker"],
                )

                st.markdown(_render_badge(intent), unsafe_allow_html=True)
                full_answer = st.write_stream(stream)
                _render_sources(sources)

                metrics = _extract_metrics(full_answer)
                if metrics:
                    _render_trade_chart(metrics)

            except Exception as e:
                import traceback
                full_answer = f"❌ Lỗi xử lý: {e}"
                sources = []
                intent  = "ERROR"
                st.error(full_answer)
                st.code(traceback.format_exc())

        # Lưu vào lịch sử
        st.session_state.messages.append({
            "role":    "assistant",
            "content": full_answer,
            "sources": sources,
            "intent":  intent,
        })


# =============================================================================
# HELPER FUNCTIONS (Nội bộ component — không export ra ngoài)
# =============================================================================
def _render_badge(intent: str):
    """Render badge intent (GREETING/TRASH/RAG)."""
    badge_map = {
        "FINANCIAL_RAG": ("badge-rag",   "🧠 RAG PIPELINE"),
        "TRASH":         ("badge-trash", "🚫 NGOÀI PHẠM VI"),
        "GREETING":      ("badge-greet", "👋 GREETING"),
    }
    cls, label = badge_map.get(intent, ("badge-rag", "🧠 RAG"))
    return f'<span class="badge {cls}">{label}</span>'


def _extract_metrics(text: str):
    """Trích xuất Entry/SL/TP từ câu trả lời AI để vẽ chart."""
    metrics = {}
    for label in ["Entry", "SL", "TP", "Stop Loss", "Take Profit"]:
        pattern = rf"{label}[:\s]*[\$]?([\d,]+\.?\d*)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            key = label.replace("Stop Loss", "SL").replace("Take Profit", "TP").split()[-1]
            try:
                metrics[key] = float(match.group(1).replace(",", ""))
            except ValueError:
                pass
    return metrics


def _render_trade_chart(metrics: dict):
    """Vẽ Plotly chart minh hoạ vị thế nếu có đủ Entry/SL/TP."""
    if not _HAS_PLOTLY:
        return
    if not all(k in metrics for k in ["Entry", "SL", "TP"]):
        return

    entry = metrics["Entry"]
    sl    = metrics["SL"]
    tp    = metrics["TP"]
    rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
    is_long = tp > entry

    fig = go.Figure()

    fig.add_hrect(y0=sl, y1=entry,
                  fillcolor="rgba(239,68,68,0.15)", line_width=0,
                  annotation_text="🛑 SL Zone", annotation_position="right")
    fig.add_hrect(y0=entry, y1=tp,
                  fillcolor="rgba(34,197,94,0.15)", line_width=0,
                  annotation_text="🎯 TP Zone", annotation_position="right")

    for y, color, name, dash in [
        (entry, "#60a5fa", f"📍 Entry: {entry:,.1f}", "solid"),
        (sl,    "#f87171", f"🛑 SL: {sl:,.1f}",       "dash"),
        (tp,    "#4ade80", f"🎯 TP: {tp:,.1f}",       "dash"),
    ]:
        fig.add_hline(y=y, line_color=color, line_dash=dash, line_width=2,
                      annotation_text=name, annotation_position="left",
                      annotation_font_color=color)

    direction = "LONG 📈" if is_long else "SHORT 📉"
    fig.update_layout(
        title=f"Sơ Đồ Vị Thế — {direction} | R:R = 1:{rr:.1f}",
        yaxis_title="Giá XAUUSD (USD/oz)",
        xaxis_visible=False,
        height=320,
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", family="Inter"),
        title_font_size=14,
        margin=dict(l=10, r=120, t=50, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_sources(sources):
    """Hiển thị nguồn tài liệu đối chiếu."""
    if not sources:
        return
    with st.expander(f"🔍 Tài liệu đối chiếu ({len(sources)} nguồn)"):
        for i, src in enumerate(sources, 1):
            score = src.get("rerank_score", src.get("score", 0))
            text_preview = src.get("parent_text", "")[:300]
            st.markdown(
                f'<div class="source-card">'
                f'<strong>#{i} {src["source"]}</strong> '
                f'<span style="color:#68d391">● {score:.3f}</span><br>'
                f'{text_preview}...'
                f'</div>',
                unsafe_allow_html=True,
            )
