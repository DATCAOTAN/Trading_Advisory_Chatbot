import os
import re
import time
from typing import List, Dict, Any, Iterator
import ollama

from src.config import Config


class LLMStream:
    """Iterator wrapper that carries provider stream metadata."""

    def __init__(self, iterator: Iterator[str], metadata: Dict[str, Any]):
        self._iterator = iter(iterator)
        self.metadata = metadata

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iterator)

    @property
    def finish_reason(self) -> str:
        return self.metadata.get("finish_reason", "UNKNOWN")


class LLMClient:
    """
    Dynamic LLM Router (Phân luồng thông minh).
    Chịu trách nhiệm:
    - Điều phối yêu cầu sang Groq Cloud hoặc Ollama Local tùy cấu hình.
    - Tự động Fallback: Nếu Groq lỗi (mạng, API, Rate Limit), tự động nhảy về Ollama.
    - Chuẩn hóa chuỗi Streaming: Đảm bảo output dạng Generator (yield token) đồng nhất cho UI.
    """

    def __init__(self, provider_override: str = None):
        self.provider = provider_override if provider_override else Config.LLM_PROVIDER
        provider = str(self.provider or "").strip().lower()
        offline = os.getenv("TRADING_OFFLINE_ACCEPTANCE", "").strip().lower() in {
            "1", "true", "yes", "y", "on"
        }
        hermetic = os.getenv("TRADING_TEST_HERMETIC", "").strip().lower() in {
            "1", "true", "yes", "y", "on"
        }
        if offline or (
            hermetic
            and provider in {"groq", "google", "gemini", "openrouter"}
        ):
            raise RuntimeError("OFFLINE_EXTERNAL_PROVIDER_FORBIDDEN")
        
        self.openrouter_api_key = Config.OPENROUTER_API_KEY
        self.openrouter_model = Config.OPENROUTER_MODEL_NAME
        
        self.groq_api_key = Config.GROQ_API_KEY
        self.groq_model = Config.GROQ_MODEL_NAME
        
        self.google_api_key = Config.GOOGLE_API_KEY
        self.google_model = Config.GOOGLE_MODEL_NAME
        self.google_fallback_model = getattr(Config, "GOOGLE_FALLBACK_MODEL_NAME", "")
        
        self.ollama_model = Config.LLM_MODEL_NAME
        self.last_finish_reason = "UNKNOWN"

        # Khởi tạo OpenRouter Client nếu cần
        self.openrouter_client = None
        if self.provider == "openrouter" or provider_override == "openrouter":
            try:
                from openai import OpenAI
                if not self.openrouter_api_key:
                    print("⚠️ [LLM_Client] OPENROUTER_API_KEY trống! Fallback về Ollama.")
                    self.provider = "ollama"
                else:
                    self.openrouter_client = OpenAI(
                        base_url="https://openrouter.ai/api/v1",
                        api_key=self.openrouter_api_key,
                    )
            except ImportError:
                print("⚠️ [LLM_Client] Chưa cài thư viện `openai`. Chạy `pip install openai` để dùng OpenRouter. Fallback về Ollama.")
                self.provider = "ollama"

        # Khởi tạo Groq Client nếu cần
        self.groq_client = None
        if self.provider == "groq" or provider_override == "groq":
            try:
                from groq import Groq
                if not self.groq_api_key:
                    print("⚠️ [LLM_Client] GROQ_API_KEY trống! Fallback về Ollama.")
                    self.provider = "ollama"
                else:
                    self.groq_client = Groq(api_key=self.groq_api_key)
            except ImportError:
                print("⚠️ [LLM_Client] Chưa cài thư viện `groq`. Chạy `pip install groq` để dùng. Fallback về Ollama.")
                self.provider = "ollama"

        # Khởi tạo Google Client (OpenAI-compatible) nếu cần
        self.google_client = None
        if self.provider == "google" or provider_override == "google":
            try:
                from openai import OpenAI
                if not self.google_api_key:
                    print("⚠️ [LLM_Client] GOOGLE_API_KEY trống! Fallback về Ollama.")
                    self.provider = "ollama"
                else:
                    self.google_client = OpenAI(
                        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                        api_key=self.google_api_key,
                    )
            except ImportError:
                print("⚠️ [LLM_Client] Chưa cài thư viện `openai`. Chạy `pip install openai` để dùng Google. Fallback về Ollama.")
                self.provider = "ollama"

    def chat(
        self,
        messages: List[Dict],
        stream: bool = False,
        temperature: float = 0.2,
        response_format: Dict[str, str] | None = None,
        max_tokens: int | None = None,
        allow_fallback: bool = True,
    ) -> Any:
        """
        Giao diện gọi chung cho tất cả các request.
        Nếu stream=True, trả về Iterator[str] yielding từng chunk (đã lọc thẻ <think>).
        Nếu stream=False, trả về Dict (đã lọc thẻ <think>).
        """
        # Hãm tốc độ 15 giây nếu xài Google Free Tier để tránh lỗi 429
        if response_format is not None and (
            response_format != {"type": "json_object"}
            or stream
            or self.provider != "groq"
        ):
            raise RuntimeError("STRUCTURED_RESPONSE_FORMAT_UNSUPPORTED")

        if self.provider == "google":
            print("⏳ [LLM_Client] Nghỉ 15s để tránh dính Rate Limit của Google...")

        if self.provider == "openrouter" and self.openrouter_client:
            if stream:
                return self._filter_think_tags(self._chat_openrouter_stream(messages, temperature))
            else:
                try:
                    resp = self._chat_openrouter_sync(messages, temperature)
                    resp["message"]["content"] = self._strip_think_sync(resp["message"]["content"])
                    return resp
                except Exception as e:
                    print(f"❌ [LLM_Client] OPENROUTER API Lỗi: {e}")
                    print(f"🔄 [LLM_Client] TỰ ĐỘNG FALLBACK: Đang gọi Ollama ({self.ollama_model})...")
                    pass # Rơi xuống khối gọi Ollama hoặc khối tiếp theo

        elif self.provider == "groq" and self.groq_client:
            if stream:
                return self._filter_think_tags(self._chat_groq_stream(messages, temperature))
            else:
                try:
                    resp = self._chat_groq_sync(
                        messages, temperature, response_format, max_tokens
                    )
                    resp["message"]["content"] = self._strip_think_sync(resp["message"]["content"])
                    return resp
                except Exception as e:
                    if not allow_fallback:
                        raise
                    print(f"❌ [LLM_Client] GROQ API Lỗi: {e}")
                    print(f"🔄 [LLM_Client] TỰ ĐỘNG FALLBACK: Đang gọi Ollama ({self.ollama_model})...")
                    pass # Rơi xuống khối gọi Ollama bên dưới

        elif self.provider == "google" and self.google_client:
            if stream:
                return self._filter_think_tags(self._chat_google_stream(messages, temperature))
            else:
                try:
                    resp = self._chat_google_sync(messages, temperature)
                    resp["message"]["content"] = self._strip_think_sync(resp["message"]["content"])
                    return resp
                except Exception as e:
                    print(f"❌ [LLM_Client] GOOGLE API Lỗi: {e}")
                    print(f"🔄 [LLM_Client] TỰ ĐỘNG FALLBACK: Đang gọi Ollama ({self.ollama_model})...")
                    pass # Rơi xuống khối gọi Ollama bên dưới

        # Gọi Ollama (Chính hoặc Fallback)
        if stream:
            return self._filter_think_tags(self._chat_ollama_stream(messages, temperature))
        else:
            resp = self._chat_ollama_sync(messages, temperature)
            resp["message"]["content"] = self._strip_think_sync(resp["message"]["content"])
            return resp

    # =========================================================================
    # FILTER LOGIC
    # =========================================================================
    def _strip_think_sync(self, text: str) -> str:
        """Lọc bỏ thẻ <think>...</think> cho non-streaming."""
        return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    def _filter_think_tags(self, stream: Iterator[str]) -> Iterator[str]:
        """
        Bộ lọc thời gian thực (On-the-fly Filter):
        Nhận diện và loại bỏ tất cả nội dung nằm giữa <think> và </think> 
        ngay trong lúc đang stream từng chunk nhỏ, tránh làm gãy luồng UI.
        """
        metadata = getattr(stream, "metadata", {"finish_reason": "UNKNOWN"})

        def filtered():
            in_think = False
            buffer = ""
            for chunk in stream:
                buffer += chunk
                while buffer:
                    if not in_think:
                        think_idx = buffer.find("<think>")
                        if think_idx != -1:
                            if think_idx > 0:
                                yield buffer[:think_idx]
                            in_think = True
                            buffer = buffer[think_idx + 7:]
                        else:
                            possible_partial = False
                            for i in range(max(0, len(buffer) - 6), len(buffer)):
                                if buffer[i] == "<" and "<think>".startswith(buffer[i:]):
                                    if i > 0:
                                        yield buffer[:i]
                                    buffer = buffer[i:]
                                    possible_partial = True
                                    break
                            if possible_partial:
                                break
                            else:
                                yield buffer
                                buffer = ""
                    else:
                        end_idx = buffer.find("</think>")
                        if end_idx != -1:
                            in_think = False
                            buffer = buffer[end_idx + 8:]
                        else:
                            possible_partial = False
                            for i in range(max(0, len(buffer) - 7), len(buffer)):
                                if buffer[i] == "<" and "</think>".startswith(buffer[i:]):
                                    buffer = buffer[i:]
                                    possible_partial = True
                                    break
                            if possible_partial:
                                break
                            else:
                                buffer = ""
                                break

            if buffer and not in_think:
                yield buffer

        return LLMStream(filtered(), metadata)

    def _stream_metadata(self, provider: str, model: str) -> Dict[str, Any]:
        return {"provider": provider, "model": model, "finish_reason": "UNKNOWN"}

    def _normalize_finish_reason(self, reason: Any) -> str:
        if reason is None:
            return "UNKNOWN"
        normalized = str(reason).strip().upper()
        mapping = {
            "STOP": "STOP",
            "FINISH_REASON_STOP": "STOP",
            "LENGTH": "MAX_TOKENS",
            "MAX_TOKEN": "MAX_TOKENS",
            "MAX_TOKENS": "MAX_TOKENS",
            "TOKEN_LIMIT": "MAX_TOKENS",
            "SAFETY": "SAFETY",
            "CONTENT_FILTER": "SAFETY",
            "RECITATION": "RECITATION",
            "LANGUAGE": "LANGUAGE",
            "ERROR": "ERROR",
        }
        return mapping.get(normalized, normalized if normalized in mapping.values() else "OTHER")

    def _extract_finish_reason(self, chunk: Any) -> str:
        if isinstance(chunk, dict):
            choices = chunk.get("choices") or []
            if choices:
                choice = choices[0]
                if isinstance(choice, dict):
                    reason = choice.get("finish_reason") or choice.get("finishReason")
                    if reason is not None:
                        return self._normalize_finish_reason(reason)
            candidates = chunk.get("candidates") or []
            if candidates:
                candidate = candidates[0]
                if isinstance(candidate, dict):
                    reason = candidate.get("finishReason") or candidate.get("finish_reason")
                    if reason is not None:
                        return self._normalize_finish_reason(reason)
            return "UNKNOWN"

        choices = getattr(chunk, "choices", None) or []
        if choices:
            choice = choices[0]
            reason = getattr(choice, "finish_reason", None) or getattr(choice, "finishReason", None)
            if reason is not None:
                return self._normalize_finish_reason(reason)

        candidates = getattr(chunk, "candidates", None) or []
        if candidates:
            candidate = candidates[0]
            reason = getattr(candidate, "finishReason", None) or getattr(candidate, "finish_reason", None)
            if reason is not None:
                return self._normalize_finish_reason(reason)

        return "UNKNOWN"

    # =========================================================================
    # OPENROUTER IMPLEMENTATION
    # =========================================================================
    def _chat_openrouter_stream(self, messages: List[Dict], temperature: float) -> Iterator[str]:
        print(f"🚀 [LLM_Client] Routing to OPENROUTER (model: {self.openrouter_model}) - Streaming")
        try:
            self.last_finish_reason = "UNKNOWN"
            response = self.openrouter_client.chat.completions.create(
                model=self.openrouter_model,
                messages=messages,
                temperature=temperature,
                stream=True,
                timeout=20.0,
                extra_headers={
                    "HTTP-Referer": "http://localhost:8501",
                    "X-Title": "Trading_Bot_RAG",
                    "Accept": "text/event-stream",  # Ép OpenRouter truyền dữ liệu dạng chuỗi sự kiện liên tục
                    "Cache-Control": "no-cache"     # Phá bỏ hoàn toàn bộ nhớ đệm trên đường truyền để nhả chữ lập tức
                },
                extra_body={
                    "provider": {
                        "order": ["Lepton", "DeepInfra", "Together"], # Chỉ định các cụm Server tối ưu tốc độ mạng
                        "allow_fallbacks": True
                    },
                    "transforms": [] # Ngăn chặn các bộ lọc trung gian làm hoãn tiến trình trả token
                }
            )
            for chunk in response:
                reason = self._extract_finish_reason(chunk)
                if reason != "UNKNOWN":
                    self.last_finish_reason = reason
                content = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
                if content:
                    yield content
        except Exception as e:
            print(f"❌ [LLM_Client] OPENROUTER API Lỗi khi Stream: {e}")
            print(f"🔄 [LLM_Client] TỰ ĐỘNG FALLBACK: Chuyển hướng sang Ollama ({self.ollama_model})...")
            self.last_finish_reason = "ERROR"
            fallback_stream = self._chat_ollama_stream(messages, temperature)
            for fallback_chunk in fallback_stream:
                yield fallback_chunk

    def _chat_openrouter_sync(self, messages: List[Dict], temperature: float) -> Dict:
        print(f"🚀 [LLM_Client] Routing to OPENROUTER (model: {self.openrouter_model}) - Sync")
        response = self.openrouter_client.chat.completions.create(
            model=self.openrouter_model,
            messages=messages,
            temperature=temperature,
            stream=False,
            timeout=30.0
        )
        return {
            "message": {
                "content": response.choices[0].message.content or ""
            }
        }

    # =========================================================================
    # GOOGLE IMPLEMENTATION (OpenAI Compatible)
    # =========================================================================
    def _chat_google_stream(self, messages: List[Dict], temperature: float) -> Iterator[str]:
        print(f"🚀 [LLM_Client] Routing to GOOGLE AI STUDIO (model: {self.google_model}) - Streaming")
        try:
            self.last_finish_reason = "UNKNOWN"
            response = self.google_client.chat.completions.create(
                model=self.google_model,
                messages=messages,
                temperature=temperature,
                stream=True,
                timeout=20.0
            )
            for chunk in response:
                reason = self._extract_finish_reason(chunk)
                if reason != "UNKNOWN":
                    self.last_finish_reason = reason
                content = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
                if content:
                    yield content
        except Exception as e:
            print(f"❌ [LLM_Client] GOOGLE API Lỗi khi Stream: {e}")
            print(f"🔄 [LLM_Client] TỰ ĐỘNG FALLBACK: Chuyển hướng sang Ollama ({self.ollama_model})...")
            self.last_finish_reason = "ERROR"
            fallback_stream = self._chat_ollama_stream(messages, temperature)
            for fallback_chunk in fallback_stream:
                yield fallback_chunk

    def _chat_google_sync(self, messages: List[Dict], temperature: float) -> Dict:
        print(f"🚀 [LLM_Client] Routing to GOOGLE AI STUDIO (model: {self.google_model}) - Sync")
        response = self.google_client.chat.completions.create(
            model=self.google_model,
            messages=messages,
            temperature=temperature,
            stream=False,
            timeout=30.0
        )
        return {
            "message": {
                "content": response.choices[0].message.content or ""
            }
        }

    def _chat_google_stream(self, messages: List[Dict], temperature: float) -> Iterator[str]:
        """Google stream with one Google model fallback before local Ollama."""
        attempts = self._google_model_attempts()
        for index, model in enumerate(attempts):
            print(f"[LLM_Client] Routing to GOOGLE AI STUDIO (model: {model}) - Streaming")
            try:
                self.last_finish_reason = "UNKNOWN"
                response = self.google_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    stream=True,
                    timeout=20.0,
                )
                for chunk in response:
                    reason = self._extract_finish_reason(chunk)
                    if reason != "UNKNOWN":
                        self.last_finish_reason = reason
                    content = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
                    if content:
                        yield content
                return
            except Exception as exc:
                print(f"[LLM_Client] GOOGLE API stream error: {exc}")
                if index + 1 < len(attempts) and self._is_transient_google_error(exc):
                    print(f"[LLM_Client] GOOGLE MODEL FALLBACK: trying {attempts[index + 1]}...")
                    continue
                print(f"[LLM_Client] FALLBACK: routing to Ollama ({self.ollama_model})...")
                self.last_finish_reason = "ERROR"
                fallback_stream = self._chat_ollama_stream(messages, temperature)
                for fallback_chunk in fallback_stream:
                    yield fallback_chunk
                return

    def _chat_google_sync(self, messages: List[Dict], temperature: float) -> Dict:
        """Google sync with one Google model fallback before caller-level fallback."""
        attempts = self._google_model_attempts()
        for index, model in enumerate(attempts):
            print(f"[LLM_Client] Routing to GOOGLE AI STUDIO (model: {model}) - Sync")
            try:
                response = self.google_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    stream=False,
                    timeout=30.0,
                )
                return {"message": {"content": response.choices[0].message.content or ""}}
            except Exception as exc:
                if index + 1 < len(attempts) and self._is_transient_google_error(exc):
                    print(f"[LLM_Client] GOOGLE API sync error: {exc}")
                    print(f"[LLM_Client] GOOGLE MODEL FALLBACK: trying {attempts[index + 1]}...")
                    continue
                raise
        return {"message": {"content": ""}}

    def _google_model_attempts(self) -> List[str]:
        models = []
        for model in [self.google_model, self.google_fallback_model]:
            model = str(model or "").strip()
            if model and model not in models:
                models.append(model)
        return models or [self.google_model]

    def _is_transient_google_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return any(marker in text for marker in ["503", "unavailable", "high demand", "rate limit", "429", "timeout", "timed out"])

    # =========================================================================
    # GROQ IMPLEMENTATION
    # =========================================================================
    def _chat_groq_stream(self, messages: List[Dict], temperature: float) -> Iterator[str]:
        print(f"🚀 [LLM_Client] Routing to GROQ (model: {self.groq_model}) - Streaming")
        try:
            self.last_finish_reason = "UNKNOWN"
            response = self.groq_client.chat.completions.create(
                model=self.groq_model,
                messages=messages,
                temperature=temperature,
                stream=True
            )
            for chunk in response:
                reason = self._extract_finish_reason(chunk)
                if reason != "UNKNOWN":
                    self.last_finish_reason = reason
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            print(f"❌ [LLM_Client] GROQ API Lỗi khi Stream: {e}")
            print(f"🔄 [LLM_Client] TỰ ĐỘNG FALLBACK: Chuyển hướng sang Ollama ({self.ollama_model})...")
            self.last_finish_reason = "ERROR"
            fallback_stream = self._chat_ollama_stream(messages, temperature)
            for fallback_chunk in fallback_stream:
                yield fallback_chunk

    def _chat_groq_sync(
        self,
        messages: List[Dict],
        temperature: float,
        response_format: Dict[str, str] | None = None,
        max_tokens: int | None = None,
    ) -> Dict:
        print(f"🚀 [LLM_Client] Routing to GROQ (model: {self.groq_model}) - Sync")
        options = {}
        if response_format is not None:
            options["response_format"] = response_format
        if max_tokens is not None:
            options["max_tokens"] = max_tokens
        response = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=messages,
            temperature=temperature,
            stream=False,
            **options,
        )
        # Giả lập format trả về của Ollama để các tầng trên không bị gãy (backward compatibility)
        content = response.choices[0].message.content if response.choices else ""
        return {"message": {"content": content}}

    # =========================================================================
    # OLLAMA IMPLEMENTATION
    # =========================================================================
    def _chat_ollama_stream(self, messages: List[Dict], temperature: float) -> Iterator[str]:
        print(f"🐢 [LLM_Client] Routing to OLLAMA LOCAL (model: {self.ollama_model}) - Streaming")
        self.last_finish_reason = "UNKNOWN"
        response = ollama.chat(
            model=self.ollama_model,
            messages=messages,
            stream=True,
            options={"temperature": temperature},
        )
        for chunk in response:
            if chunk.get("done"):
                self.last_finish_reason = self._normalize_finish_reason(chunk.get("done_reason") or "STOP")
            if "message" in chunk and "content" in chunk["message"]:
                yield chunk["message"]["content"]

    def _chat_ollama_sync(self, messages: List[Dict], temperature: float) -> Dict:
        print(f"🐢 [LLM_Client] Routing to OLLAMA LOCAL (model: {self.ollama_model}) - Sync")
        return ollama.chat(
            model=self.ollama_model,
            messages=messages,
            stream=False,
            options={"temperature": temperature},
        )
