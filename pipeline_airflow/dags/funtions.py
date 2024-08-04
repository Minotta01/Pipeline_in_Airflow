import os
import ast # Para evaluar expresiones de manera segura.
import requests
import pandas as pd
from airflow import DAG
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from airflow.models import Variable
from ydata_profiling import ProfileReport
from sqlalchemy import create_engine
from airflow.providers.postgres.hooks.postgres import PostgresHook



def get_data(**context):
    
    try:

        #   get url the API
        api_url=Variable.get('api_url')
        response=requests.get(api_url, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print('Obtained data\n')
            df = pd.DataFrame(data)

            # Guardar el DataFrame como un archivo Parquet temporal
            temp_file = "/tmp/temp_data.parquet"
            df.to_parquet(temp_file)

            # Compruebo si se creo la ruta del archivo temporal y si los
            # los archivo se guardaro en esa ruta
            
            if os.path.exists(temp_file):
                    print(f"Parquet file created at: {temp_file}\n")
                    
                    # Pasar el nombre del archivo temporal al siguiente task
                    context['ti'].xcom_push(key='temp_file_path', value=temp_file)
                    return temp_file 
            else:
                print("Failed to create Parquet file.")
        else:
            raise Exception(f"API request failed with status code {response.status_code}")
    except Exception as e:
        print(f"Error in get_data: {str(e)}")
        raise


def transform_data(**context):
# Obtengo los datos a travez del DAG 
    try:
        ti = context['ti']
        #Obtengo los datos y lo guardo en la variable temp_file_path
        temp_file_path = ti.xcom_pull(key='temp_file_path', task_ids='Get_data')

        temp_file=temp_file_path

        # imprimo los datos para saber que obtuve 
        print(f"Received temp_file path from XCom: {temp_file}\n")

        # creo condicion para asegurarme que que tipo de dato estoy resiviendo
        if temp_file is None or not os.path.exists(temp_file):
            raise FileNotFoundError(f"The Parquet file does not exist at {temp_file}. Please check the previous task.\n")
        
        # Creo un data frame con los datos obtenidos 
        data_df=pd.read_parquet(temp_file)
        print('\nDatos convertido en DataFrame:\n', data_df.head(1))

        # Creo el archivo para generar el reporte de los datos
        profile=ProfileReport(data_df, title='Data Quality Report')

        # Definir la ruta para guardar el archivo
        dag_folder = context['dag'].folder
        data_folder = os.path.join(dag_folder, 'data')
        
        # Crear la carpeta 'data' si no existe
        Path(data_folder).mkdir(parents=True, exist_ok=True)
        
        # Generar un nombre de archivo único basado en la fecha de ejecución

        execution_date = context['execution_date'] # => Para obtener la fecha y hora de ejecucion del dag
        file_name = f'profile_report_{execution_date.strftime("%Y%m%d_%H%M%S")}.html' # => Generar un nombre de archivo único basado en la fecha de ejecución
        file_path = os.path.join(data_folder, file_name) #  Crear la ruta y guarda el archivo de nombre unico en esa ruta creada 
        
        # Guardar el informe
        profile.to_file(file_path)
        
        print(f"Informe de perfil guardado en: {file_path}")

    except Exception as e:
            print(f"Error in transform_data: {str(e)}")
            raise   
            
         

def data_cleansing(**context):
    # En esta funcion realizo limpieza de los datos que considero inecesarios y organizo los datos de una forma optima

    # Obtengo los datos de la funcion Get_data
    temp_file = context['ti'].xcom_pull(key='temp_file_path', task_ids='Get_data')

    # Transformo eso datos en un data frame
    data_df=pd.read_parquet(temp_file)

    # Elimino la columna con el nombre orden ya que cuya informacion no me parece relevante 
    data_df = data_df.drop(columns=['orden'])
    
    # Me aseguro que la columna hora, tenga el formato adecuado
    data_df['hora'] = pd.to_datetime(data_df['hora'], format='%H:%M:%S').dt.time

    
    #for i in range(len(df)):
    #    hora=df.loc[i,'hora']
    #    if hora >= pd.to_datetime('00:00', format='%H:%M').time() and hora < pd.to_datetime('06:00', format='%H:%M').time():
    #        df.loc[i, 'franja horaria'] = 'Madrugada'
    #    elif hora >= pd.to_datetime('06:00', format='%H:%M').time() and hora < pd.to_datetime('12:00', format='%H:%M').time():
    #        df.loc[i, 'franja horaria'] = 'Mañana'
    #    elif hora >= pd.to_datetime('12:00', format='%H:%M').time() and hora < pd.to_datetime('18:00', format='%H:%M').time():
    #        df.loc[i, 'franja horaria'] = 'Tarde'
    #    else:
    #        df.loc[i, 'franja horaria'] = 'Noche'

    # Me aseguro de crear una columna donde me permita clasificar la franja horaria donde ocurrieron los hechos 
    # basado en llos intervalos de tiempo

    bins = [pd.to_datetime(t).time() for t in ['00:00', '06:00', '12:00', '18:00', '23:59:59']]
    labels = ['Madrugada', 'Mañana', 'Tarde', 'Noche']
    data_df['franja horaria'] = pd.cut(data_df['hora'].apply(lambda x: x.hour * 3600 + x.minute * 60 + x.second),
                                       bins=[t.hour * 3600 + t.minute * 60 + t.second for t in bins],
                                       labels=labels,
                                       include_lowest=True)
    
    # Guardo los cambios realizado al dataframe en nuestro archivo temporal creado 
    data_df.to_parquet(temp_file)

    # Verifico si s eguardo de forma correcta 
    verified_df = pd.read_parquet(temp_file)
    print("Contenido verificado del Parquet file:")
    print(verified_df.head())

    # Me aseguro de enviar de nuevo la informacion con sus cambio para poder ser usado en otro DAG
    context['ti'].xcom_push(key='temp_file_path',value=temp_file)


def insert_data_postgrees(**context):

    # EN esta funcion me permitira guarda la informacion a una base de dato PostgreSQL

    # Recibo la informacion       
    data = context['ti'].xcom_pull(key='temp_file_path',task_ids='data_cleansing')
    # La tranformo en dataframe
    data_df = pd.read_parquet(data)

    # Creo la conexion a la base de datos para ingresar los datos obtenidos
    pg_hook = PostgresHook(postgres_conn_id='connect_db') 

    try:
        conn_uri = pg_hook.get_uri()
        engine = create_engine(conn_uri)

        #  le asigno un nombre
        table_name = 'Taza_de_accidentes_2021_2022'

        #Creo la tabla, si la tabla ya existe me asgeuro que cree una y la remplace y he inserte los dato del dataframe
        data_df.to_sql(table_name, engine, if_exists='replace', index=False, method='multi', chunksize=1000)

        print(f"Se insertaron {len(data_df)} filas en la tabla '{table_name}'.")

    except Exception as e:
        print(f"Error al conectar a PostgreSQL: {str(e)}")
    
    finally:
        # Cierro la conexion a la base de datos
        engine.dispose()
        print("Conexión a la base de datos cerrada.")
    # Elimino el archivo temporal 
    os.remove("/tmp/temp_data.parquet")
    