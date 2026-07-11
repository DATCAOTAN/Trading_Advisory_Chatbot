FROM python:3.10-slim

ARG INSTALL_MINERU=false
ARG MINERU_PACKAGE="mineru[core]"

# Thiết lập thư mục làm việc
WORKDIR /app

# Khắc phục lỗi build liên quan đến C++ compiler cho một số thư viện
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN if [ "$INSTALL_MINERU" = "true" ]; then \
      python -m venv /opt/mineru_venv && \
      /opt/mineru_venv/bin/python -m pip install --no-cache-dir -U pip && \
      /opt/mineru_venv/bin/python -m pip install --no-cache-dir -U "$MINERU_PACKAGE"; \
    fi

ENV MINERU_COMMAND=/opt/mineru_venv/bin/mineru

# Copy toàn bộ mã nguồn
COPY . .

# Expose port Streamlit
EXPOSE 8501

# Healthcheck để Docker biết app đã chạy hay chưa
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Khởi chạy hệ thống (Bỏ qua launcher.py vốn chỉ dành cho Windows)
CMD ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
