from datetime import datetime,timedelta
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.models import Variable
from airflow.utils.task_group import TaskGroup
import pandas as pd
import requests
from funtions import get_data, transform_data, data_cleansing, insert_data_postgrees

default_args = {
    'depends_on_past': False,
    "start_date": datetime(2024,7,24),
    "retries":   1,
    "retry_delay":timedelta(minutes=1),

}

dag = DAG (
    dag_id="Pipeline",
    description="Pipeline and ETL to extract data from an API, transform and load into a database.",
    catchup = False,
    schedule_interval = "*/1 * * * *",
    max_active_runs = 1,
    dagrun_timeout = timedelta(hours=1),
    default_args = default_args,
    tags = ["Pipeline and ETL"]
)

with dag as dag:
    #   creo mi bandera de iniciar proceso
    start_task = EmptyOperator(
        task_id = "Inicia_proceso"
    )
    #   creo mi bandera de finalizar proceso
    end_task = EmptyOperator(
        task_id = "Finalizar_proceso"
    )

    #   Creo mi primer proceso de ejecucion 
    first_task = PythonOperator(
        task_id = "Get_data",
        python_callable = get_data,
        #retries = retries,
        #retry_delay = retry_delay
        provide_context=True,
        dag=dag,
    )
    Second_task = PythonOperator(
        task_id = "transforms_data",
        python_callable = transform_data,
        provide_context=True,
        dag=dag,
    )
    third_task = PythonOperator(
        task_id = "data_cleansing",
        python_callable=data_cleansing,
        dag=dag,
    )
    task_insert_data_postgree = PythonOperator(
         task_id='insert_data_postgrees',
         python_callable=insert_data_postgrees,
         dag=dag,
    )
start_task >> first_task >> Second_task >> third_task >> task_insert_data_postgree >> end_task
