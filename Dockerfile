FROM python:3.12-slim

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

EXPOSE 10000
CMD ["python", "bot/main.py"]
