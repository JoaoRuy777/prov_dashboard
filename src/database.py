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

def get_olt_to_db_mapping():
    """Builds a mapping of OLT IP -> Database Secrets Key."""
    mapping = {}
    if not hasattr(st, "secrets"):
        return mapping
        
    for key in set(st.secrets.keys()):
        if key == "migration_db":
            continue
        try:
            config = st.secrets[key]
            # Assumes any config with 'dbname' is an OLT DB
            if hasattr(config, "keys") and "dbname" in config:
                conn = psycopg2.connect(
                    host=config["host"],
                    database=config["dbname"],
                    user=config["user"],
                    password=config["password"],
                    port=config.get("port", 5432),
                    connect_timeout=5
                )
                query = "SELECT DISTINCT endereco FROM public.configuracaoprofile WHERE endereco IS NOT NULL"
                df = pd.read_sql(query, conn)
                for ip in df['endereco'].tolist():
                    mapping[str(ip).strip()] = key
                conn.close()
        except Exception as e:
            print(f"Error mapping OLTs for DB {key}: {e}")
            
    return mapping

def get_cached_mapping():
    """Used to avoid spamming the database on every rerun."""
    if 'db_mapping_cache' not in st.session_state or 'db_mapping_cache_time' not in st.session_state:
        st.session_state['db_mapping_cache'] = get_olt_to_db_mapping()
        st.session_state['db_mapping_cache_time'] = datetime.datetime.now()
    else:
        # Cache for 10 minutes
        if (datetime.datetime.now() - st.session_state['db_mapping_cache_time']).total_seconds() > 600:
            st.session_state['db_mapping_cache'] = get_olt_to_db_mapping()
            st.session_state['db_mapping_cache_time'] = datetime.datetime.now()
    
    return st.session_state['db_mapping_cache']

def get_db_for_olt(olt_ip):
    """Establishes connection to the correct database for a given OLT."""
    try:
        clean_ip = str(olt_ip).strip() if olt_ip else ""
        mapping = get_cached_mapping()
        db_key = mapping.get(clean_ip)
        
        if not db_key:
            # Fallback to 'postgres' if present
            if hasattr(st, "secrets") and "postgres" in st.secrets:
                db_key = "postgres"
            else:
                return None
                
        db_config = st.secrets[db_key]
        if db_config.get("password") == "sua_senha_secreta":
            return None
            
        conn = psycopg2.connect(
            host=db_config["host"],
            database=db_config["dbname"],
            user=db_config["user"],
            password=db_config["password"],
            port=db_config.get("port", 5432),
            connect_timeout=10
        )
        return conn
    except Exception as e:
        print(f"Error connecting to database for OLT {olt_ip}: {e}")
        return None

def get_migration_connection():
    """Establishes connection to the migration database."""
    try:
        if "migration_db" not in st.secrets:
            print("Migration DB secrets not found.")
            return None
            
        db_config = st.secrets["migration_db"]
        conn = psycopg2.connect(
            host=db_config["host"],
            database=db_config["dbname"],
            user=db_config["user"],
            password=db_config["password"],
            port=db_config["port"]
        )
        return conn
    except Exception as e:
        print(f"Error connecting to migration database: {e}")
        return None

def get_olts():
    """Fetches the list of available OLTs from cached DB mapping."""
    mapping = get_cached_mapping()
    olts = list(mapping.keys())
    return sorted(olts) if olts else ["Nenhuma OLT encontrada/Mock"]

def get_data(use_mock=False, start_date=None, end_date=None, olt_ip=None):
    """
    Fetches data from the database with filtering.
    """
    # Decide strategy 
    if use_mock:
        return _get_mock_data()
        
    conn = get_db_for_olt(olt_ip)
    if not conn:
        print("Database connection unavailable, using mock data.")
        return _get_mock_data()

    # Real Query
    # Real Query
    # Real Query
    # Updated to user's model with parameterized filters
    query = """
    SELECT
        fp.id,
        fp.mensagemerro AS raw_error,
        fp.sucesso AS status_bool,
        fp.json,
        fp.json::jsonb ->> 'script' AS command_type,
        fp.datainicio AS created_at,
        c.endereco AS olt_ip
    FROM public.filaprovisionamento fp
    JOIN public.configuracaoprofile c ON c.configuracaoid = fp.configuracaoid
    WHERE 1=1
    """
    
    params = []
    
    # Date Filtering (Assuming user wants >= start and < end+1day like previous logic often implies)
    # The user example was: fp.datainicio >= TIMESTAMP '2026-02-10 00:00:00' AND < '2026-02-11 ...'
    if start_date:
        query += " AND fp.datainicio >= %s"
        params.append(start_date)
    
    if end_date:
        # To match the user's logic (< next day), we should probably use <= end_date 23:59:59 
        # or < end_date + 1 day.
        # However, the previous code was likely datainicio <= end_date (date object).
        # Let's stick with simple comparison to avoid timezone mess for now, or add +1 day logic if requested.
        # User logic: < TIMESTAMP '2026-02-11' (assuming end_date was 2026-02-10)
        # We will use <= for now to be safe with existing input type (date object).
        query += " AND fp.datainicio <= %s"
        params.append(end_date + datetime.timedelta(days=1)) # Make it inclusive of end_date fully? No, usually <= end_date is fine if it's date.
        # Wait, if end_date is a date object '2026-02-10', comparison with timestamp often acts as 00:00:00.
        # So <= '2026-02-10' only gets midnight.
        # User's query used < '2026-02-11'. This catches everything on the 10th.
        # Let's adjust to < end_date + 1 day
    
    # OLT Filtering (Address to ID join)
    # OLT Filtering (Address to ID join)
    if olt_ip:
        query += " AND c.endereco = %s"
        # Ensure we don't have leading/trailing whitespace which might kill the match
        clean_ip = olt_ip.strip() if isinstance(olt_ip, str) else olt_ip
        params.append(clean_ip)
        
    # Limit for safety
    query += " ORDER BY fp.datainicio DESC LIMIT 5000"

    try:
        # Debugging: Print query and params to see what's actually running
        print(f"\n[DEBUG] Running Query with OLT: '{olt_ip}', Start: '{start_date}', End: '{end_date}'")
        # print(query) # Uncomment if you want full query text
        print(f"[DEBUG] Params: {params}")
        
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        
        print(f"DEBUG: Dataframe columns: {df.columns.tolist()}")
        print(f"DEBUG: First row: {df.iloc[0].to_dict() if not df.empty else 'Empty'}")

        
        # Post-processing: Map boolean status to strings
        # Optimization: Map status efficiently
        if not df.empty:
            # Check if status_bool was actually returned
            if 'status_bool' in df.columns:
                # Vectorized mapping is faster than apply
                df['status'] = 'Pending' # Default
                df.loc[df['status_bool'] == True, 'status'] = 'Success'
                df.loc[df['status_bool'] == False, 'status'] = 'Error'
                # Drop existing but don't error if missing (though we checked)
                df.drop(columns=['status_bool'], inplace=True)
            else:
                # Fallback if column is missing from DB
                print("WARNING: 'status_bool' column missing from query result. using 'Unknown'.")
                df['status'] = 'Unknown'

            # Ensure all other expected columns exist to prevent downstream KeyErrors
            expected_cols = ['raw_error', 'json', 'command_type', 'created_at', 'olt_ip']
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = None

        return df

    except Exception as e:
        print(f"Error executing query: {e}")
        if conn: conn.close()
        return pd.DataFrame(columns=['id', 'raw_error', 'status', 'json', 'command_type', 'created_at', 'olt_ip'])

def insert_migration_data(data):
    """
    Inserts migration data into temporarias.olt_depara_insulina_interfocus
    """
    conn = get_migration_connection()
    if not conn:
        print("Database connection unavailable for migration.")
        return False

    query = """
    INSERT INTO temporarias.olt_depara_insulina_interfocus (
        ipatual, ip_para, vlan_dados_para, vlan_tv_para, vlan_voz_para, 
        ipclusterprovisionamento_para, idpool_ipoe_default, idplano_ipoe_default, 
        marca_olt_ins, urlapiintegracao, secretapidiscovery, codigo
    ) VALUES (
        %(ipatual)s, %(ip_para)s, %(vlan_dados_para)s, %(vlan_tv_para)s, %(vlan_voz_para)s,
        %(ipclusterprovisionamento_para)s, %(idpool_ipoe_default)s, %(idplano_ipoe_default)s,
        %(marca_olt_ins)s, %(urlapiintegracao)s, %(secretapidiscovery)s, %(codigo)s
    )
    """

    try:
        cursor = conn.cursor()
        cursor.execute(query, data)
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error inserting migration data: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

