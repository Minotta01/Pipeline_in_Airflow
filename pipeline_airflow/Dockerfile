FROM apache/airflow:2.9.3-python3.8


USER root

RUN apt-get update && apt-get install -y postgresql-client

COPY requirements.txt /requirements.txt

USER airflow

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r /requirements.txt

#RUN pip install ydata_profiling
