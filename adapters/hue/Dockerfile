FROM python:3.13-slim
ENV PYTHONBUFFERED=1 

WORKDIR /app 

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN useradd --create-home appuser
CMD ["python","main.py"]