FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md requirements.lock.txt ./
COPY src ./src
RUN pip install --no-cache-dir -c requirements.lock.txt .
COPY app ./app
COPY .streamlit ./.streamlit
RUN useradd --create-home adryn && chown -R adryn:adryn /app
USER adryn
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
