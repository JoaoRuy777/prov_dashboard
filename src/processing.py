import pandas as pd

def treat_error_message(raw_msg):
    """
    Translates technical error messages into user-friendly explanations.
    """
    if pd.isna(raw_msg) or raw_msg == 'None':
        return "N/A"
        
    # Dictionary of known errors and their treatments
    # This can be expanded based on real logs
    error_map = {
        'Connection timeout to switch': 'Falha de Conexão (Timeout) - Verificar Rede',
        'Invalid parameters provided': 'Parâmetros Inválidos - Verificar Payload',
        'User already exists': 'Usuário Duplicado - Já Provisionado',
        'Provisioning gateway unreachable': 'Gateway Indisponível - Contatar Infra'
    }
    
    # Simple lookup
    if raw_msg in error_map:
        return error_map[raw_msg]
        
    # Fallback for unknown errors
    return f"Erro Desconhecido: {raw_msg}"

def process_data(df):
    """
    Applies treatments to the dataframe.
    """
    if df.empty:
        return df
        
    # Add 'treated_error' column
    df['treated_error'] = df['raw_error'].apply(treat_error_message)
    
    # Ensure date is datetime
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'])
        
    return df

def filter_data(df, status_filter, type_filter, date_range):
    """
    Filters the dataframe based on UI inputs.
    """
    if df.empty:
        return df
        
    filtered_df = df.copy()
    
    # Status Filter
    if status_filter:
        filtered_df = filtered_df[filtered_df['status'].isin(status_filter)]
        
    # Type Filter
    if type_filter:
        filtered_df = filtered_df[filtered_df['command_type'].isin(type_filter)]
        
    # Date Range Filter
    if date_range and len(date_range) == 2:
        start_date, end_date = date_range
        # Ensure comparison across timestamps
        mask = (filtered_df['created_at'].dt.date >= start_date) & (filtered_df['created_at'].dt.date <= end_date)
        filtered_df = filtered_df[mask]
        
    return filtered_df
