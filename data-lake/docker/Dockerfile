FROM apache/airflow:2.11.2-python3.11

ARG AIRFLOW_VERSION=2.11.2
ARG PYTHON_VERSION=3.11

RUN pip install --no-cache-dir \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt" \
    "apache-airflow==${AIRFLOW_VERSION}" \
    boto3 lxml pandas pyarrow \
    && pip check
