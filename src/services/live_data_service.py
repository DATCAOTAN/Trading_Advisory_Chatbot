"""
Live Data Service — Stub API cho dữ liệu thời gian thực.

Thiết kế sẵn sàng kết nối:
  - Oanda API: Giá XAUUSD real-time
  - ForexFactory: Lịch kinh tế
  - SSI/WGC: Báo cáo vĩ mô

Hiện tại tất cả hàm trả về thông báo "Đang phát triển".
Khi có API key, chỉ cần điền vào OANDA_API_KEY và bỏ comment phần implement.
"""

from datetime import datetime
from typing import Dict, Optional
from src.config import Config


class LiveDataService:
    """
    Dịch vụ dữ liệu thời gian thực — Hiện tại là stub, sẵn sàng tích hợp API.
    """

    # =========================================================================
    # CONFIG (Điền API key khi sẵn sàng)
    # =========================================================================
    OANDA_API_KEY      = None   # os.getenv("OANDA_API_KEY")
    OANDA_ACCOUNT_ID   = None   # os.getenv("OANDA_ACCOUNT_ID")
    FOREX_FACTORY_URL  = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def __init__(self):
        self._price_cache: Dict = {}
        self._calendar_cache: Dict = {}

    # =========================================================================
    # GIÁ LIVE (OANDA)
    # =========================================================================
    def get_live_price(self, symbol: str = "XAU_USD") -> str:
        """
        Lấy giá XAUUSD real-time từ Oanda API.
        
        TODO: Uncomment và điền API key để kích hoạt.
        """
        # ── PLACEHOLDER ──────────────────────────────────────────────────────
        # import requests
        # headers = {"Authorization": f"Bearer {self.OANDA_API_KEY}"}
        # url = f"https://api-fxtrade.oanda.com/v3/instruments/{symbol}/candles"
        # params = {"count": 1, "granularity": "S5", "price": "M"}
        # resp = requests.get(url, headers=headers, params=params)
        # data = resp.json()
        # price = float(data["candles"][-1]["mid"]["c"])
        # return f"💰 **{symbol}**: ${price:,.2f} USD/oz (cập nhật lúc {datetime.now().strftime('%H:%M:%S')})"
        # ─────────────────────────────────────────────────────────────────────

        return (
            "📡 **Tính năng Giá Live đang được phát triển.**\n\n"
            "Để kích hoạt, bạn cần cung cấp **OANDA API Key** và cấu hình "
            "trong `src/services/live_data_service.py`.\n\n"
            f"*Thời điểm truy vấn: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}*"
        )

    # =========================================================================
    # LỊCH KINH TẾ (FOREX FACTORY)
    # =========================================================================
    def get_economic_calendar(self, impact: str = "High") -> str:
        """
        Lấy lịch kinh tế tuần này từ ForexFactory.
        Lọc sự kiện tác động HIGH để tập trung vào tin quan trọng.

        TODO: Kích hoạt bằng cách uncomment phần requests.
        """
        # ── PLACEHOLDER ──────────────────────────────────────────────────────
        # import requests
        # try:
        #     resp = requests.get(self.FOREX_FACTORY_URL, timeout=10)
        #     events = resp.json()
        #     high_impact = [e for e in events if e.get("impact") == impact]
        #     lines = [f"📅 {e['date']} | {e['currency']} | {e['title']}" for e in high_impact[:10]]
        #     return "**Sự kiện kinh tế tác động cao tuần này:**\n\n" + "\n".join(lines)
        # except Exception as e:
        #     return f"❌ Lỗi lấy lịch kinh tế: {e}"
        # ─────────────────────────────────────────────────────────────────────

        return (
            "📅 **Lịch Kinh tế Tự động đang được phát triển.**\n\n"
            "Tính năng sẽ hiển thị sự kiện tác động cao từ ForexFactory theo thời gian thực. "
            "Trong thời gian chờ, bạn có thể tham khảo tại: https://www.forexfactory.com/calendar"
        )

    # =========================================================================
    # BÁO CÁO VĨ MÔ (SSI/WGC)
    # =========================================================================
    def get_latest_macro_report(self) -> str:
        """
        Tải báo cáo vĩ mô mới nhất từ SSI Research hoặc World Gold Council.
        TODO: Implement scraping hoặc API call.
        """
        return (
            "📊 **Báo cáo Vĩ mô Tự động đang được phát triển.**\n\n"
            "Tính năng sẽ tự động tải và index báo cáo từ SSI Research, WGC vào kho Dynamic PDF. "
            "Tham khảo thủ công:\n"
            "- WGC: https://www.gold.org/research\n"
            "- SSI: https://www.ssi.com.vn/en/research"
        )

    # =========================================================================
    # QUÉT VÀ DỌN DẸP KHO ĐỘNG
    # =========================================================================
    def refresh_dynamic_knowledge(self) -> str:
        """
        Dọn dẹp tài liệu cũ trong kho dynamic và thông báo trạng thái.
        TODO: Thêm logic xóa PDF quá 30 ngày.
        """
        return (
            "🔄 **Quản lý Kho Tri thức Động:**\n\n"
            f"Thư mục: `{Config.DYNAMIC_PDF_DIR}`\n"
            "Chức năng tự động dọn dẹp file cũ sẽ được triển khai trong phiên bản tiếp theo."
        )


# Singleton instance
_live_service_instance = None

def get_live_service() -> LiveDataService:
    global _live_service_instance
    if _live_service_instance is None:
        _live_service_instance = LiveDataService()
    return _live_service_instance
