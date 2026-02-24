FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src
COPY config ./config
COPY README.md ROADMAP.md SUMMARY.md ./

RUN mkdir -p /app/outputs /app/data/samples

ENV APP_ENV=prod
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_HEADLESS=true

EXPOSE 8501

CMD ["sh", "-c", "streamlit run src/app.py --server.address=${STREAMLIT_SERVER_ADDRESS} --server.port=${STREAMLIT_SERVER_PORT} --server.headless=${STREAMLIT_SERVER_HEADLESS}"]
