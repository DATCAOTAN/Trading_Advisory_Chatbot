FROM python:3.10-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Khắc phục lỗi build liên quan đến C++ compiler cho một số thư viện
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn
COPY . .

# Expose port Streamlit
EXPOSE 8501

# Healthcheck để Docker biết app đã chạy hay chưa
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Khởi chạy hệ thống (Bỏ qua launcher.py vốn chỉ dành cho Windows)
CMD ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
