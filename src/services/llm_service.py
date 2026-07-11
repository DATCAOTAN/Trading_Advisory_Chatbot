"""
LLM Service — Nâng cấp toàn diện với:
1. Streaming response (stream=True → generator)
2. Query Rewriting: mở rộng câu hỏi tiếng lóng → chuẩn tài chính
3. Multi-Hop Generation: ép LLM suy luận theo chuỗi logic tài chính
4. Self-Correction: vòng kiểm tra hallucination (tùy chọn)
"""

import unicodedata
from typing import Iterator, List, Dict, Optional
from src.config import Config
from src.core.llm_client import LLMClient
from src.services.knowledge.answer_mode import AnswerModeClassifier, EvidenceSchemaRegistry
from src.services.knowledge.query_decomposer import QueryDecomposer
from src.services.knowledge.query_intent import QueryIntentRouter


class LLMService:
    """
    Tầng giao tiếp với Cloud LLM (OpenRouter) và Local Fallback.
    Tất cả response đều hỗ trợ streaming để hiển thị chữ chạy từng token trên UI.
    """

    SYSTEM_BASE = (
        "Bạn là một Trợ lý Cố vấn Tài chính Cao cấp chuyên sâu về thị trường Vàng (XAUUSD) và Ngoại hối (Forex), "
        "hoạt động tại Việt Nam năm 2026.\n\n"

        "QUY TẮC CỐT LÕI:\n"
        "1. KHÓA NGÔN NGỮ (LANGUAGE LOCK - BẮT BUỘC): Bất kể tài liệu ngữ cảnh trích xuất chứa ngôn ngữ gì (Tiếng Anh, Tiếng Trung...), BẠN PHẢI DỊCH và TỔNG HỢP toàn bộ thành TIẾNG VIỆT 100% chuẩn ngữ pháp. TUYỆT ĐỐI KHÔNG để lọt bất kỳ ký tự tiếng nước ngoài nào chưa được dịch vào câu trả lời (trừ mã tài sản viết tắt như XAUUSD, DXY, SMC, FVG).\n"
        "2. DỰA VÀO BỐI CẢNH TÀI LIỆU để trả lời các phân tích vĩ mô, tín hiệu giao dịch. TUYỆT ĐỐI không bịa số liệu (giá cả, mốc thời gian, tin tức). Tuy nhiên, nếu người dùng hỏi về kiến thức tài chính cơ bản (ví dụ: định nghĩa SMC, mối tương quan giữa DXY và Vàng, lý thuyết trading), BẠN ĐƯỢC PHÉP dùng kiến thức chuyên gia sẵn có của mình để giải thích cặn kẽ, kết hợp với tài liệu trích xuất.\n"
        "3. TRÍ NHỚ DÀI HẠN: Nếu trong bối cảnh có chứa mục 【KÝ ỨC LỊCH SỬ DÀI HẠN】, đó CHÍNH LÀ những gì bạn và người dùng đã nói với nhau trước đây. Hãy đọc nó để trả lời! TUYỆT ĐỐI KHÔNG được từ chối bằng các câu như 'Là một AI, tôi không lưu lịch sử' - vì hệ thống đã trang bị bộ nhớ Vector cho bạn rồi.\n"
        "4. Văn phong: Tiếng Việt chuyên ngành tài chính — nghiêm túc, gãy gọn, lập luận logic.\n"
        "5. TỪ CHỐI mọi câu hỏi ngoài phạm vi tài chính, kinh tế, trading.\n\n"

        "CÔ LẬP KẾT QUẢ ĐẦU RA (OUTPUT ISOLATION - RẤT QUAN TRỌNG):\n"
        "- TUYỆT ĐỐI KHÔNG in ra quá trình suy nghĩ, phân tích ý định, hay các tiêu đề nội bộ (như 'Phân tích mục đích...', 'Trả lời dựa trên tài liệu...', 'Định dạng phù hợp...').\n"
        "- TUYỆT ĐỐI KHÔNG lặp lại câu hỏi thô hoặc câu hỏi đã được làm sạch của người dùng trong bài làm.\n"
        "- Trả về kết quả SẠCH SẼ, đi THẲNG VÀO TRỌNG TÂM câu hỏi. Bắt đầu ngay bằng nội dung phân tích.\n\n"

        "NGUYÊN TẮC PHẢN HỒI — NƯƠNG THEO CÂU HỎI (Context-Aware Formatting):\n"
        "Hãy chọn định dạng PHÙ HỢP NHẤT dựa trên mục đích câu hỏi:\n\n"

        "• Nếu người dùng hỏi về KHÁI NIỆM / ĐỊNH NGHĨA (vd: 'Order Block là gì?', 'FVG hoạt động thế nào?'):\n"
        "  → Tập trung giải thích bản chất lý thuyết, cơ chế hoạt động, kèm ví dụ minh họa từ tài liệu.\n"
        "  → KHÔNG ép vào khuôn phân tích vĩ mô hay đưa Entry/SL/TP.\n\n"

        "• Nếu người dùng yêu cầu PHÂN TÍCH XU HƯỚNG / CHIẾN LƯỢC giao dịch cụ thể (vd: 'vàng nên mua hay bán?', 'xu hướng XAUUSD tuần này?'):\n"
        "  → Tổng hợp dữ liệu từ vĩ mô (Fed, DXY, lạm phát) đến kỹ thuật (SMC, Price Action) trong tài liệu.\n"
        "  → Đưa ra mốc Entry / SL / TP rõ ràng nếu tài liệu có đủ dữ liệu.\n\n"

        "• Nếu người dùng hỏi về NĂNG LỰC / CHỨC NĂNG của hệ thống (vd: 'bạn có thể giúp gì?', 'bot biết những gì?'):\n"
        "  → Liệt kê ngắn gọn các phạm vi kiến thức (SMC, Price Action, Vĩ mô, Dòng tiền) bằng gạch đầu dòng.\n\n"

        "• Với MỌI loại câu hỏi khác: Tự do chọn định dạng tối ưu nhất (bảng biểu, gạch đầu dòng, đoạn văn ngắn).\n"
        "  TUYỆT ĐỐI KHÔNG áp dụng một khuôn mẫu cố định cho mọi lượt chat."
    )

    FINANCE_ANSWER_CONTRACT = (
        "FINANCE/TRADING ANSWER CONTRACT:\n"
        "- Answer the user's question directly first, then explain using the retrieved context.\n"
        "- Treat book/PDF/vector knowledge as static educational context, not live market data.\n"
        "- If live price/candle/news data is not present in the context, say so before making market-timing claims.\n"
        "- Use friendly source fields in the context (title, organization/author, period, page) when describing where an idea comes from.\n"
        "- Never expose raw technical IDs in the final answer, including doc_id, chunk_id, parent_chunk_id, or values like report_*_v1/book_*_v1.\n"
        "- For official report questions, start with a source sentence like: Theo <report title> cua <organization> giai doan <period>...\n"
        "- For FINANCIAL_RAG answers, follow the answer-scope instruction in the user prompt: report summary, concept explanation, or market/trading implication.\n"
        "- When discussing market impact, connect the context to USD/DXY, yields, risk sentiment, and XAUUSD/gold only if the user explicitly asks about market/trading/gold impact.\n"
        "- If the user only asks what a report says, summarize the report and do not add XAUUSD/trading-decision commentary.\n"
        "- Mention that ingested reports/books are historical Knowledge V3 documents, not realtime market data.\n"
        "- For Entry/SL/TP or real trade decisions, state that realtime price, forecast/consensus, prior revision, DXY, yields, and current news must be checked.\n"
        "- Do not invent citations, page numbers, prices, dates, or source names that are not in the context.\n"
        "- Do not use certainty language such as guaranteed profit, sure win, must buy now, or must sell now.\n"
        "- Prefer risk-aware wording: educational explanation, practical interpretation, limitations, and risk notes.\n"
        "- Keep the answer concise by default and write in Vietnamese unless the user explicitly asks otherwise.\n"
        "- If context is insufficient, say what is missing and answer only the supported part."
    )

    def __init__(self):
        self.llm_client = LLMClient(provider_override="google")
        self.query_intent_router = QueryIntentRouter()
        self.answer_mode_classifier = AnswerModeClassifier(self.query_intent_router)
        self.query_decomposer = QueryDecomposer(self.query_intent_router)

    def _call(
        self,
        messages: List[Dict],
        stream: bool = False,
        temperature: float = 0.2,
    ):
        """Gọi LLM Router (OpenRouter/Ollama) hỗ trợ cả stream và non-stream."""
        return self.llm_client.chat(
            messages=messages,
            stream=stream,
            temperature=temperature,
        )

    # =========================================================================
    # 1. QUERY REWRITING
    # =========================================================================
    def rewrite_query(self, query: str, chat_history: List[Dict] = None) -> str:
        """
        Mở rộng và làm rõ câu hỏi ngắn/tiếng lóng của Trader thành
        câu truy vấn chuẩn khoa học để tối ưu Hybrid Search.

        Ví dụ:
          "vàng lên hay xuống?" → "Xu hướng giá XAUUSD trong bối cảnh DXY và lãi suất Fed hiện tại?"
        """
        if not Config.ENABLE_QUERY_REWRITING:
            return query
            
        print(f"\n✏️ [QueryRewrite] Đầu vào gốc nhận được: '{query}'")

        history_summary = ""
        if chat_history:
            recent = chat_history[-Config.MEMORY_WINDOW:]
            history_lines = [
                f"  [{m['role'].upper()}]: {m['content'][:200]}"
                for m in recent
                if m["role"] in ("user", "assistant")
            ]
            if history_lines:
                history_summary = "Lịch sử hội thoại gần đây:\n" + "\n".join(history_lines) + "\n\n"

        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là một Kỹ sư Cấu trúc Dữ liệu chuyên trách tối ưu hóa câu lệnh tìm kiếm (Query Expansion Expert) "
                    "cho Vector Database (Qdrant) trong hệ thống RAG tài chính chuyên sâu về Vàng (XAUUSD) và Forex.\n"
                    "Nhiệm vụ của bạn: Đọc câu hỏi hoặc câu thoại của người dùng, phân tích ý định ngầm (Intent) của họ. "
                    "Sau đó, hãy tạo ra một chuỗi các từ khóa mở rộng mang tính chất định hướng tri thức (Semantic Search Terms) "
                    "để hệ thống đi quét các tài liệu kỹ thuật liên quan.\n\n"

                    "HƯỚNG DẪN TƯ DUY EXPANSION:\n"
                    "- Nếu người dùng hỏi chung chung về thị trường, hãy tự động bổ sung các cụm từ khóa nền tảng: "
                    "'Cấu trúc thị trường (Market Structure), Mô hình nến, Xu hướng giá vĩ mô, Quản lý vốn, Tâm lý giao dịch Forex, Phân tích kỹ thuật XAUUSD'.\n"
                    "- Nếu người dùng hỏi về chiến lược cụ thể, hãy bổ sung các từ khóa chuyên sâu: "
                    "'Phương pháp SMC (Smart Money Concept), Vùng thanh khoản (Liquidity Pool), Khối lệnh (Order Block), "
                    "Vùng mất cân bằng cung cầu (Fair Value Gap - FVG), Quét thanh khoản (Liquidity Sweep)'.\n\n"

                    "QUY TẮC ĐẦU RA BẮT BUỘC:\n"
                    "- KHÔNG giải thích dòng vo, KHÔNG chào hỏi, KHÔNG bọc thẻ mã code block (```).\n"
                    "- Chỉ trả về DUY NHẤT chuỗi văn bản chứa các từ khóa ngữ nghĩa đã được mở rộng.\n"
                    "- Chuỗi trả về bắt buộc phải có nghĩa, độ dài tối thiểu trên 10 ký tự, tuyệt đối không trả về ký tự đơn rác rưởi hoặc chỉ chứa dấu câu."
                )
            },
            {
                "role": "user",
                "content": (
                    f"{history_summary}"
                    f"Câu hỏi gốc: \"{query}\"\n\n"
                    "Tạo chuỗi từ khóa Semantic Search:"
                )
            }
        ]

        try:
            # Thực hiện gọi đồng bộ (Sync) lên OpenRouter
            response = self.llm_client.openrouter_client.chat.completions.create(
                model=self.llm_client.openrouter_model,
                messages=messages,
                temperature=0.5,
                stream=False
            )
            raw_rewritten = response.choices[0].message.content.strip()
            rewritten = raw_rewritten.strip('"').strip("'")
            
            # --- VALIDATION CHECK (FALLBACK TO ORIGINAL QUERY) ---
            # 1. Chống Rỗng & Ngắn
            if len(rewritten) < 5 or not any(c.isalnum() for c in rewritten):
                print(f"⚠️ [QueryRewrite] VALIDATION FAILED!")
                print(f"   -> Câu hỏi gốc của User: '{query}'")
                print(f"   -> Chuỗi LLM viết lại lỗi: '{rewritten}'")
                print(f"   -> Quyết định: HỦY BỎ chuỗi lỗi, tự động bốc câu gốc chuyển sang Qdrant.")
                return query
                
            # 2. Chống Mất Thực Thể (Entity Validation Guardrail)
            query_lower = query.lower()
            rewritten_lower = rewritten.lower()
            core_entities = ["vàng", "gold", "xauusd", "dxy", "forex", "smc", "fvg", "lãi suất", "fed"]
            
            # Xác định các thực thể trọng tâm có trong câu hỏi gốc
            found_entities = [ent for ent in core_entities if ent in query_lower]
            if found_entities:
                # Nếu câu rewrite KHÔNG bảo toàn được ít nhất một thực thể liên quan -> Hủy bỏ
                # (Vì bộ não LLM gọt quá tay)
                if not any(ent in rewritten_lower for ent in found_entities):
                    print(f"⚠️ [QueryRewrite] VALIDATION FAILED! (Mất từ khóa {found_entities})")
                    print(f"   -> Câu hỏi gốc của User: '{query}'")
                    print(f"   -> Chuỗi LLM viết lại lỗi: '{rewritten}'")
                    print(f"   -> Quyết định: HỦY BỎ chuỗi lỗi, tự động bốc câu gốc chuyển sang Qdrant.")
                    return query

            print(f"✏️ [QueryRewrite] Viết lại thành công: '{rewritten}'")
            return rewritten

        except Exception as e:
            print(f"⚠️ [QueryRewrite] Lỗi: {e}")
            return query

    # =========================================================================
    # 2. MULTI-HOP GENERATION (STREAMING)
    # =========================================================================
    def generate_multihop_stream(
        self,
        query: str,
        context: str,
        chat_history: List[Dict] = None,
        defense_preamble: str = "",
    ) -> Iterator[str]:
        """
        Sinh câu trả lời linh hoạt dựa trên mục đích câu hỏi.
        LLM tự phân tích intent rồi chọn định dạng phù hợp nhất.

        Yields: Từng token/chunk text để streaming lên Streamlit.
        """
        # Xây dựng lịch sử chat gần nhất
        history_messages = []
        if chat_history:
            recent = chat_history[-(Config.MEMORY_WINDOW):]
            for m in recent:
                if m["role"] in ("user", "assistant"):
                    history_messages.append({
                        "role": m["role"],
                        "content": m["content"][:1500]  # Truncate để tiết kiệm token
                    })

        scope_instruction = self._answer_scope_instruction(query)
        user_content = (
            f"BỐI CẢNH TÀI LIỆU TRÍCH XUẤT TỪ QDRANT DB:\n{context}\n\n"
            "─" * 40 + "\n\n"
            f"CÂU HỎI CỦA TRADER: {query}\n\n"
            "Hãy trả lời trực tiếp trước, rồi giải thích dựa trên các khối [SOURCE]/[CONTENT] phía trên.\n"
            "Nếu nguồn có Title/Organization/Author/Period/Page, hãy dùng chúng để diễn đạt kiểu: Theo <title> của <organization/author> giai đoạn <period>...\n"
            "Không được in Doc ID/doc_id/chunk_id/parent_chunk_id hay các mã thô như report_*_v1, book_*_v1 trong câu trả lời.\n"
            f"{scope_instruction}\n"
            "Luôn kết thúc bằng mục 'Kết luận ngắn:' gồm 1-2 câu tổng hợp trực tiếp từ ngữ cảnh.\n"
            "Nếu bối cảnh chỉ là kiến thức sách/PDF, không được trình bày như dữ liệu thị trường live.\n"
            "Nếu thiếu dữ liệu để kết luận giao dịch thực chiến, hãy nói rõ giới hạn đó.\n"
            "LƯU Ý: BẮT BUỘC TRẢ LỜI 100% BẰNG TIẾNG VIỆT, BẤT KỂ TÀI LIỆU LÀ TIẾNG GÌ.\n"
            "KHÔNG nhắc lại câu hỏi, KHÔNG giải thích quá trình suy nghĩ, KHÔNG hứa lợi nhuận chắc chắn. BẮT ĐẦU TRẢ LỜI NGAY:\n"
        )

        messages = [
            {"role": "system", "content": f"{self.SYSTEM_BASE}\n\n{self.FINANCE_ANSWER_CONTRACT}"},
            *history_messages,
            {"role": "user", "content": user_content},
        ]

        try:
            stream = self._call(messages, stream=True, temperature=0.2)
            if defense_preamble:
                yield defense_preamble
            for chunk in stream:
                if chunk:
                    yield chunk
        except Exception as e:
            yield f"\n\n❌ Lỗi kết nối AI: {e}"

    def generate_evidence_contract_stream(
        self,
        query: str,
        structured_prompt: str,
        chat_history: List[Dict] = None,
        defense_preamble: str = "",
    ) -> Iterator[str]:
        """Generate from structured evidence instead of an unlabeled context blob."""
        history_messages = []
        if chat_history:
            recent = chat_history[-(Config.MEMORY_WINDOW):]
            for message in recent:
                if message["role"] in ("user", "assistant"):
                    history_messages.append({
                        "role": message["role"],
                        "content": message["content"][:1500],
                    })

        user_content = (
            f"{structured_prompt}\n\n"
            f"CÂU HỎI CỦA TRADER: {query}\n\n"
            "Hãy trả lời bằng tiếng Việt. Chỉ dùng evidence được gắn nhãn ở trên cho các claim có nguồn. "
            "Không suy luận quan điểm tác giả từ tiêu đề hoặc metadata. "
            "Nếu evidence thiếu hoặc yếu, nói rõ giới hạn thay vì tự bịa. "
            "Không hứa lợi nhuận chắc chắn."
        )
        messages = [
            {"role": "system", "content": f"{self.SYSTEM_BASE}\n\n{self.FINANCE_ANSWER_CONTRACT}"},
            *history_messages,
            {"role": "user", "content": user_content},
        ]

        try:
            stream = self._call(messages, stream=True, temperature=0.2)
            if defense_preamble:
                yield defense_preamble
            for chunk in stream:
                if chunk:
                    yield chunk
        except Exception as e:
            yield f"\n\n❌ Lỗi kết nối AI: {e}"

    def _answer_scope_instruction(self, query: str) -> str:
        """Return deterministic final-answer scope rules; no LLM call."""
        if not hasattr(self, "query_intent_router"):
            self.query_intent_router = QueryIntentRouter()
        if not hasattr(self, "answer_mode_classifier"):
            self.answer_mode_classifier = AnswerModeClassifier(self.query_intent_router)
        if not hasattr(self, "query_decomposer"):
            self.query_decomposer = QueryDecomposer(self.query_intent_router)
        decomposition = self.query_decomposer.decompose(query)
        if decomposition.is_multi_intent:
            return (
                "ANSWER_MODE: MULTI_INTENT. Người dùng hỏi nhiều ý độc lập. "
                "Hãy trả lời theo từng mục tương ứng với từng [SUBQUESTION], mỗi mục nêu rõ nguồn chính đã dùng. "
                "Không được dùng nguồn của mục này để kết luận thay cho mục khác. "
                "Nếu một subquestion thiếu evidence thì chỉ báo thiếu cho đúng subquestion đó."
            )
        intent = self.query_intent_router.route(query)
        answer_mode = self.answer_mode_classifier.classify(query, intent)
        schema = EvidenceSchemaRegistry.first_for_intent(intent)
        hints = ", ".join(schema.format_hints[:6]) if schema else ""

        if answer_mode.mode == "MARKET_IMPACT":
            return (
                "ANSWER_MODE: MARKET_IMPACT. Người dùng đang hỏi về tác động thị trường/giao dịch. "
                "Hãy dùng cấu trúc: nguồn đã dùng, dữ liệu/ý chính từ tài liệu, cơ chế tác động tới USD/DXY/lợi suất/risk sentiment/XAUUSD nếu liên quan, "
                "rồi kết luận ngắn và nêu dữ liệu realtime cần kiểm tra trước quyết định giao dịch. Không đưa lệnh Buy/Sell chắc chắn."
            )
        if answer_mode.mode == "REPORT_METHODOLOGY":
            return (
                "ANSWER_MODE: REPORT_METHODOLOGY. Người dùng hỏi cách tính/phương pháp/định nghĩa trong báo cáo. "
                "Ưu tiên giải thích phương pháp, survey/definition/seasonal adjustment nếu có trong context. "
                "Không tự thêm tác động thị trường hay XAUUSD nếu người dùng không hỏi."
            )
        if answer_mode.mode == "REPORT_NUMBERS":
            suffix = f" Schema cần ưu tiên: {hints}." if hints else ""
            return (
                "ANSWER_MODE: REPORT_NUMBERS. Người dùng cần số liệu/tín hiệu chính từ báo cáo. "
                "Ưu tiên các số liệu, biến động theo kỳ, thành phần đóng góp và revision nếu context có. "
                "Không tự thêm trading impact nếu người dùng không hỏi."
                f"{suffix}"
            )
        if answer_mode.mode == "REPORT_SUMMARY":
            suffix = f" Schema cần ưu tiên: {hints}." if hints else ""
            return (
                "ANSWER_MODE: REPORT_SUMMARY. Người dùng chỉ hỏi tài liệu/báo cáo nói gì. "
                "Chỉ tóm tắt nội dung báo cáo theo nguồn đã truy xuất: nguồn đã dùng, 2-5 ý chính liên quan trực tiếp, rồi Kết luận ngắn. "
                "Không tự thêm XAUUSD, gold, trading decision, Entry/SL/TP, realtime price, DXY hoặc lợi suất trái phiếu nếu câu hỏi không yêu cầu."
                f"{suffix}"
            )
        if answer_mode.mode == "BOOK_CONCEPT_EXPLANATION":
            return (
                "ANSWER_MODE: BOOK_CONCEPT_EXPLANATION. Người dùng hỏi khái niệm/khung tư duy từ sách hoặc knowledge base. "
                "Ưu tiên định nghĩa, nguyên lý, ví dụ thực hành và giới hạn của khái niệm. Không tự biến thành market call."
            )
        if answer_mode.mode == "INSUFFICIENT_EVIDENCE":
            return (
                "ANSWER_MODE: INSUFFICIENT_EVIDENCE. Không được khẳng định chắc chắn lợi nhuận/hướng giá. "
                "Hãy nói rõ Knowledge V3 không đủ bằng chứng cho cam kết đó và chỉ trả lời phần được context hỗ trợ."
            )
        return (
            "ANSWER_MODE: UNKNOWN. Trả lời đúng phạm vi câu hỏi bằng nguồn đã truy xuất, tránh mở rộng sang XAUUSD/giao dịch nếu người dùng không hỏi. "
            "Kết thúc bằng Kết luận ngắn."
        )

    @staticmethod
    def _normalize_query(query: str) -> str:
        text = str(query or "").lower()
        normalized = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    @staticmethod
    def _asks_market_or_trade_scope(normalized_query: str) -> bool:
        """Detect explicit market/trading-impact scope without matching report domains like labor market."""
        text = f" {normalized_query} "
        explicit_terms = (
            "xauusd",
            " vang ",
            " gold ",
            "giao dich",
            "trading",
            " trade ",
            "thi truong",
            "market reaction",
            "market impact",
            "tac dong thi truong",
            "anh huong thi truong",
            "anh huong vang",
            "anh huong gold",
            "anh huong xauusd",
            "impact on gold",
            "impact on xauusd",
            "impact market",
            " dxy ",
            " usd ",
            "yield",
            "loi suat trai phieu",
            "entry",
            " sl ",
            " tp ",
            " buy ",
            " sell ",
            "mua hay ban",
            "nen mua",
            "nen ban",
            "gia vang",
            "gold price",
        )
        return any(term in text for term in explicit_terms)

    # =========================================================================
    # 3. SELF-CORRECTION (NON-STREAMING — Vòng kiểm tra ẩn)
    # =========================================================================
    def self_correct(self, answer: str, context: str) -> str:
        """
        Vòng kiểm tra hallucination: Gửi câu trả lời + context gốc,
        yêu cầu LLM xác nhận hoặc hiệu chỉnh số liệu không có trong PDF.

        Chạy 1 lần non-stream sau khi đã có full answer.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là kiểm duyệt viên tài chính. Nhiệm vụ: "
                    "So sánh CÂU TRẢ LỜI với TÀI LIỆU GỐC. "
                    "Nếu có số liệu, tỷ lệ % hoặc điểm giá trong câu trả lời KHÔNG xuất hiện trong tài liệu gốc, "
                    "hãy trả về CHỈ MỘT DÒNG DUY NHẤT: '\n\n⚠️ **Đính chính tự động:** Số liệu [X] không có trong tài liệu.' "
                    "Nếu tất cả đều đúng, trả về chính xác chữ: '[OK]'."
                )
            },
            {
                "role": "user",
                "content": (
                    f"TÀI LIỆU GỐC:\n{context[:3000]}\n\n"
                    f"CÂU TRẢ LỜI CẦN KIỂM TRA:\n{answer}\n\n"
                    "Hãy kiểm tra và trả về câu trả lời đã xác nhận:"
                )
            }
        ]

        try:
            resp = self._call(messages, stream=False, temperature=0.0)
            corrected = resp["message"]["content"].strip()
            return corrected if corrected else answer
        except Exception as e:
            print(f"⚠️ [SelfCorrect] Lỗi: {e}")
            return answer

    # =========================================================================
    # 4. BACKWARD COMPAT — Non-streaming cho test scripts cũ
    # =========================================================================
    def generate_response(self, query: str, context: str) -> str:
        """Non-streaming: Gom toàn bộ stream thành 1 string."""
        tokens = list(self.generate_multihop_stream(query, context))
        return "".join(tokens)


if __name__ == "__main__":
    print("=== SMOKE TEST: LLM SERVICE ===")
    svc = LLMService()

    test_query = "Lạm phát cao ảnh hưởng đến XAUUSD như thế nào?"
    test_ctx   = "[Nguồn: test_doc.pdf]\nKhi lạm phát tăng, Fed thường tăng lãi suất..."

    print("✏️ Test Query Rewriting...")
    rewritten = svc.rewrite_query(test_query)
    print(f"   → {rewritten}")

    print("\n🌊 Test Streaming Generation...")
    for token in svc.generate_multihop_stream(rewritten, test_ctx):
        print(token, end="", flush=True)
    print("\n✅ Done!")
