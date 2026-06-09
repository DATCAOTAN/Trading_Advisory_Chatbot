import os
import re
from typing import List, Dict, Any, Iterator
import ollama

from src.config import Config

class LLMClient:
    """
    Dynamic LLM Router (Phân luồng thông minh).
    Chịu trách nhiệm:
    - Điều phối yêu cầu sang Groq Cloud hoặc Ollama Local tùy cấu hình.
    - Tự động Fallback: Nếu Groq lỗi (mạng, API, Rate Limit), tự động nhảy về Ollama.
    - Chuẩn hóa chuỗi Streaming: Đảm bảo output dạng Generator (yield token) đồng nhất cho UI.
    """

    def __init__(self):
        self.provider = Config.LLM_PROVIDER
        
        self.openrouter_api_key = Config.OPENROUTER_API_KEY
        self.openrouter_model = Config.OPENROUTER_MODEL_NAME
        
        self.groq_api_key = Config.GROQ_API_KEY
        self.groq_model = Config.GROQ_MODEL_NAME
        
        self.google_api_key = Config.GOOGLE_API_KEY
        self.google_model = Config.GOOGLE_MODEL_NAME
        
        self.ollama_model = Config.LLM_MODEL_NAME

        # Khởi tạo OpenRouter Client nếu cần
        self.openrouter_client = None
        if self.provider == "openrouter":
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
        if self.provider == "groq":
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
        if self.provider == "google":
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

    def chat(self, messages: List[Dict], stream: bool = False, temperature: float = 0.2) -> Any:
        """
        Giao diện gọi chung cho tất cả các request.
        Nếu stream=True, trả về Iterator[str] yielding từng chunk (đã lọc thẻ <think>).
        Nếu stream=False, trả về Dict (đã lọc thẻ <think>).
        """
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
                    resp = self._chat_groq_sync(messages, temperature)
                    resp["message"]["content"] = self._strip_think_sync(resp["message"]["content"])
                    return resp
                except Exception as e:
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

    # =========================================================================
    # OPENROUTER IMPLEMENTATION
    # =========================================================================
    def _chat_openrouter_stream(self, messages: List[Dict], temperature: float) -> Iterator[str]:
        print(f"🚀 [LLM_Client] Routing to OPENROUTER (model: {self.openrouter_model}) - Streaming")
        try:
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
                content = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
                if content:
                    yield content
        except Exception as e:
            print(f"❌ [LLM_Client] OPENROUTER API Lỗi khi Stream: {e}")
            print(f"🔄 [LLM_Client] TỰ ĐỘNG FALLBACK: Chuyển hướng sang Ollama ({self.ollama_model})...")
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
            response = self.google_client.chat.completions.create(
                model=self.google_model,
                messages=messages,
                temperature=temperature,
                stream=True,
                timeout=20.0
            )
            for chunk in response:
                content = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
                if content:
                    yield content
        except Exception as e:
            print(f"❌ [LLM_Client] GOOGLE API Lỗi khi Stream: {e}")
            print(f"🔄 [LLM_Client] TỰ ĐỘNG FALLBACK: Chuyển hướng sang Ollama ({self.ollama_model})...")
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

    # =========================================================================
    # GROQ IMPLEMENTATION
    # =========================================================================
    def _chat_groq_stream(self, messages: List[Dict], temperature: float) -> Iterator[str]:
        print(f"🚀 [LLM_Client] Routing to GROQ (model: {self.groq_model}) - Streaming")
        try:
            response = self.groq_client.chat.completions.create(
                model=self.groq_model,
                messages=messages,
                temperature=temperature,
                stream=True
            )
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            print(f"❌ [LLM_Client] GROQ API Lỗi khi Stream: {e}")
            print(f"🔄 [LLM_Client] TỰ ĐỘNG FALLBACK: Chuyển hướng sang Ollama ({self.ollama_model})...")
            fallback_stream = self._chat_ollama_stream(messages, temperature)
            for fallback_chunk in fallback_stream:
                yield fallback_chunk

    def _chat_groq_sync(self, messages: List[Dict], temperature: float) -> Dict:
        print(f"🚀 [LLM_Client] Routing to GROQ (model: {self.groq_model}) - Sync")
        response = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=messages,
            temperature=temperature,
            stream=False
        )
        # Giả lập format trả về của Ollama để các tầng trên không bị gãy (backward compatibility)
        content = response.choices[0].message.content if response.choices else ""
        return {"message": {"content": content}}

    # =========================================================================
    # OLLAMA IMPLEMENTATION
    # =========================================================================
    def _chat_ollama_stream(self, messages: List[Dict], temperature: float) -> Iterator[str]:
        print(f"🐢 [LLM_Client] Routing to OLLAMA LOCAL (model: {self.ollama_model}) - Streaming")
        response = ollama.chat(
            model=self.ollama_model,
            messages=messages,
            stream=True,
            options={"temperature": temperature},
        )
        for chunk in response:
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
