import pandas as pd
import datetime
import psycopg2
import os
import streamlit as st
import random

# Mock Data Generator (Internal Helper)
def _get_mock_data():
    """Generates mock data for testing purposes."""
    rows = 50
    command_types = ['1', 'addphone', 'addtv', '1', 'addphone']
    statuses = ['Success', 'Error', 'Pending']
    errors = [
        'Connection timeout to switch',
        'Invalid parameters provided',
        'User already exists',
        'Provisioning gateway unreachable',
        None
    ]
    
    data = []
    base_time = datetime.datetime.now()
    
    for i in range(rows):
        status = random.choice(statuses)
        error_msg = None
        if status == 'Error':
            error_msg = random.choice(errors)
            
        record = {
            'id': i + 1,
            'created_at': base_time - datetime.timedelta(minutes=random.randint(0, 300)),
            'command_type': random.choice(command_types),
            'status': status,
            'raw_error': error_msg,
            'json': f'{{"serial": "GPON{i:04d}", "pon": {random.randint(1,8)}}}',
            'olt_ip': random.choice(['192.168.1.10', '10.0.0.1'])
        }
        data.append(record)
        
    return pd.DataFrame(data)

def get_connection():
    """Establishes connection to the PostgreSQL database using secrets."""
    try:
        # Check if secrets are configured
        if "postgres" not in st.secrets:
            return None
            
        db_config = st.secrets["postgres"]
        
        # Avoid connecting if password is default placeholder
        if db_config.get("password") == "sua_senha_secreta":
            return None
        
        conn = psycopg2.connect(
            host=db_config["host"],
            database=db_config["dbname"],
            user=db_config["user"],
            password=db_config["password"],
            port=db_config["port"]
        )
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

def get_olts():
    """Fetches the list of available OLTs (endpoints) for the dropdown."""
    conn = get_connection()
    
    if not conn:
        # Fallback Mock
        return ["OLT Mock 1 (192.168.1.10)", "OLT Mock 2 (10.0.0.1)"]

    query = """
    SELECT DISTINCT endereco 
    FROM public.configuracaoprofile
    WHERE endereco IS NOT NULL
    ORDER BY endereco
    """
    
    try:
        df = pd.read_sql(query, conn)
        conn.close()
        return df['endereco'].tolist()
    except Exception as e:
        print(f"Error fetching OLTs: {e}")
        if conn: conn.close()
        return ["Erro ao buscar OLTs"]

def get_data(use_mock=False, start_date=None, end_date=None, olt_ip=None):
    """
    Fetches data from the database with filtering.
    """
    # Decide strategy
    if use_mock:
        return _get_mock_data()
        
    conn = get_connection()
    if not conn:
        print("Database connection unavailable, using mock data.")
        return _get_mock_data()

    # Real Query
    query = """
    SELECT
        fp.id,
        fp.retornoexecucao as raw_error,
        fp.sucesso as status_bool,
        fp.json,
        fp.identificacao as command_type,
        fp.datainicio as created_at,
        c.endereco as olt_ip
    FROM public.filaprovisionamento fp 
    JOIN public.configuracaoprofile c ON c.id = fp.configuracaoid
    WHERE 1=1
    """
    
    params = []
    
    # Date Filtering
    if start_date:
        query += " AND fp.datainicio >= %s"
        params.append(start_date)
    
    if end_date:
        # Add filtering for end of day? Or simple comparison
        query += " AND fp.datainicio <= %s"
        params.append(end_date)
        
    # OLT Filtering
    if olt_ip:
        query += " AND c.endereco = %s"
        params.append(olt_ip)
        
    # Limit for safety
    query += " ORDER BY fp.datainicio DESC LIMIT 5000"

    try:
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        
        # Post-processing: Map boolean status to strings
        def map_status(val):
            if val is True: return 'Success'
            if val is False: return 'Error'
            return 'Pending' # None/Null
            
        if not df.empty and 'status_bool' in df.columns:
            df['status'] = df['status_bool'].apply(map_status)
            df.drop(columns=['status_bool'], inplace=True)
            
        return df
        
    except Exception as e:
        print(f"Error executing query: {e}")
        if conn: conn.close()
        return pd.DataFrame()
