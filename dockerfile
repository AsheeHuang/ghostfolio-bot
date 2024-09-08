FROM python:3.12

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

ENV BOT_TOKEN={YOUR_BOT_TOKEN}
ENV GHOSTFOLIO_TOKEN={YOUR_GHOSTFOLIO_TOKEN}
ENV HOST=http://localhost:3333

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "telegram_bot.py"]
