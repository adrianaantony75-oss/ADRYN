FROM python:3.13-slim
WORKDIR /bot
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY adryn_bot ./adryn_bot
ENV BOT_STATE_FILE=/bot/data/bot_state.json
RUN mkdir -p /bot/data
EXPOSE 8080
CMD ["python", "-m", "adryn_bot", "--port", "8080"]
