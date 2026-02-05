import streamlit as st
import pandas as pd
import plotly.express as px
import os
import sys
import io
import time
import datetime

# Ensure the current directory is in the python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database import get_data, get_olts
from src.processing import process_data, filter_data

# ... (Config and CSS remain headers) ...

# --- Sidebar Navigation ---
# Logo Check
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)

# Initialize Session State
if 'selected_view' not in st.session_state:
    st.session_state['selected_view'] = 'Visão Geral'
if 'data_fetched' not in st.session_state:
    st.session_state['data_fetched'] = False
if 'df_cache' not in st.session_state:
    st.session_state['df_cache'] = pd.DataFrame()

# Navigation Buttons
def set_view(view):
    st.session_state['selected_view'] = view

view_options = {
    'Visão Geral': 'Visão Geral', 
    'Dados (Internet)': 'Dados (Internet)', 
    'TV': 'TV', 
    'Telefonia': 'Telefonia', 
    'Base Completa': 'Base Completa', 
    'Relatórios': 'Relatórios'
}

for option, label in view_options.items():
    if st.sidebar.button(label, use_container_width=True, type="primary" if st.session_state['selected_view'] == option else "secondary"):
        set_view(option)
        st.rerun()

selected_view = st.session_state['selected_view']

st.sidebar.markdown("---")
st.sidebar.header("Filtros Globais")

# Auto-Refresh Toggle
auto_refresh = st.sidebar.toggle("🔁 Atualização Automática (30s)", value=False)

# form for filters to prevent auto-reload on every change
with st.sidebar.form("filter_form"):
    st.write("Configuração da Busca")
    
    # OLT Selector
    available_olts = get_olts()
    if not available_olts:
        available_olts = ["Nenhuma OLT encontrada/Mock"]
        
    selected_olt = st.selectbox("Selecione a OLT", available_olts)
    
    # Date Range
    today = datetime.date.today()
    date_range = st.date_input(
        "Período de Análise",
        value=(today, today),
        max_value=today
    )
    
    submit_button = st.form_submit_button("🔍 Buscar Dados")

# --- Data Loading Logic ---
if submit_button or auto_refresh:
    # Handle Date Range
    start_date = None
    end_date = None
    if isinstance(date_range, tuple):
        if len(date_range) >= 1: start_date = date_range[0]
        if len(date_range) == 2: end_date = date_range[1]
        
    # Extract IP from selection if format is "Name (IP)" or just use selection
    # Assuming get_olts returns just strings of IPs or addresses for now based on query
    olt_ip_query = selected_olt
    
    with st.spinner("Buscando dados no banco..."):
        # Call database with filters
        raw_df = get_data(
            use_mock=False, # Try real DB first, falls back to mock inside function if fails
            start_date=start_date,
            end_date=end_date,
            olt_ip=olt_ip_query
        )
        
        if not raw_df.empty:
            processed_df = process_data(raw_df)
            st.session_state['df_cache'] = processed_df
            st.session_state['data_fetched'] = True
        else:
            st.warning("Nenhum dado encontrado para os filtros selecionados.")
            st.session_state['df_cache'] = pd.DataFrame()

df_full = st.session_state['df_cache']

# Apply client-side filters if needed, but mostly we rely on DB now.
# We still set df_filtered_date for compatibility with views
df_filtered_date = df_full

# --- Views Implementation ---
if not st.session_state['data_fetched'] and not submit_button:
    st.info("👈 Utilize os filtros na barra lateral e clique em 'Buscar Dados' para começar.")
elif df_filtered_date.empty:
    st.warning("Sem dados para exibir.")
else:
    # ... views render logic continues ...
    pass 


# --- Helper Functions ---

def render_metrics(df):
    total_commands = len(df)
    success_count = len(df[df['status'] == 'Success'])
    error_count = len(df[df['status'] == 'Error'])
    success_rate = (success_count / total_commands * 100) if total_commands > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total de Comandos", total_commands)
    with col2:
        st.metric("Sucesso", success_count, delta=f"{success_rate:.1f}%")
    with col3:
        st.metric("Erros", error_count, delta_color="inverse")
    with col4:
        st.metric("Tipos Únicos", df['command_type'].nunique())

def render_charts(df):
    if df.empty:
        st.info("Sem dados para gerar gráficos.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.caption("Distribuição de Status")
        fig_status = px.pie(
            df,
            names='status',
            color='status',
            color_discrete_map={"Success": "green", "Error": "red", "Pending": "orange"},
            hole=0.5
        )
        fig_status.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=True)
        st.plotly_chart(fig_status, use_container_width=True)

    with col2:
        st.caption("Top Motivos de Erro")
        error_df = df[df['status'] == 'Error']
        if not error_df.empty:
            df_errors = error_df['treated_error'].value_counts().reset_index()
            df_errors.columns = ['Motivo do Erro', 'Contagem']
            
            fig_error = px.bar(
                df_errors, 
                x="Contagem", 
                y="Motivo do Erro", 
                orientation='h',
                color="Contagem",
                color_continuous_scale="Reds",
                text="Contagem"
            )
            fig_error.update_layout(margin=dict(t=10, b=10, l=10, r=10), yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_error, use_container_width=True)
        else:
            div_success = """
            <div style="display: flex; justify-content: center; align-items: center; height: 300px; color: green; font-weight: bold;">
                ✓ Operação 100% Sucesso
            </div>
            """
            st.markdown(div_success, unsafe_allow_html=True)

def render_data_table(df):
    st.subheader("Detalhamento da Fila")
    if not df.empty:
        # Prepare Data for Display
        display_df = df.copy()
        
        # Select columns
        cols = ['id', 'created_at', 'command_type', 'status', 'treated_error']
        display_df = display_df[cols]

        # Use Column Config for "Rich" display
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": st.column_config.TextColumn("ID", width="small", help="Identificador único"),
                "created_at": st.column_config.DatetimeColumn(
                    "Data de Criação",
                    format="D/M/YYYY HH:mm:ss",
                    width="medium"
                ),
                "command_type": st.column_config.TextColumn("Tipo Comando", width="medium"),
                "status": st.column_config.TextColumn(
                    "Status",
                    width="small",
                    help="Estado atual do provisionamento"
                ),
                "treated_error": st.column_config.TextColumn(
                    "Diagnóstico / Erro",
                    width="large",
                    help="Descrição traduzida do erro, se houver"
                )
            },
            # Keep the color highlight for rows based on status logic if possible?
            # Streamlit dataframes don't support row-based styling AND column_config easily mixed without pandas Styler.
            # We will use pandas styler for colors.
        )
        # Note: If we passed a Styler object to st.dataframe, column_config is ignored or partially applied in earlier versions.
        # But in recent versions it composes. Let's try passing the raw DF with config to prioritize layout/names.
        # Color verification: The user liked the colors. We might lose row coloring if we don't use Styler.
        # Let's re-add Styler coloring but mapped to the new column names if we renamed them? 
        # Column config changes DISPLAY name, not underlying data name. So Styler works on original names.
        # We can apply Styler AND column_config.
        
        def highlight_status(val):
            color = ''
            if val == 'Error':
                color = 'background-color: #590000; color: #ffcccc' # Dark red bg
            elif val == 'Success':
                color = 'background-color: #004400; color: #ccffcc' # Dark green bg
            return color

        styler = display_df.style.map(highlight_status, subset=['status'])
        
        st.dataframe(
            styler,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": "ID",
                "created_at": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY HH:mm"),
                "command_type": "Comando",
                "status": "Status",
                "treated_error": "Diagnóstico do Erro"
            }
        )

    else:
        st.write("Sem dados para exibir.")

# --- Views Implementation ---

if selected_view == 'Visão Geral':
    st.title("Visão Geral - Todos os Serviços")
    render_metrics(df_filtered_date)
    st.markdown("---")
    render_charts(df_filtered_date)
    st.markdown("---")
    render_data_table(df_filtered_date)

elif selected_view == 'Dados (Internet)':
    st.title("Monitoramento - Internet (Dados)")
    target_types = ['1'] 
    df_view = df_filtered_date[df_filtered_date['command_type'].isin(target_types)]
    
    if df_view.empty:
        st.warning("Nenhum comando de Internet encontrado.")
    else:
        render_metrics(df_view)
        st.markdown("---")
        render_charts(df_view)
        st.markdown("---")
        render_data_table(df_view)

elif selected_view == 'TV':
    st.title("Monitoramento - TV")
    df_view = df_filtered_date[df_filtered_date['command_type'] == 'addtv']
    
    if df_view.empty:
        st.warning("Nenhum comando de TV encontrado.")
    else:
        render_metrics(df_view)
        st.markdown("---")
        render_charts(df_view)
        st.markdown("---")
        render_data_table(df_view)

elif selected_view == 'Telefonia':
    st.title("Monitoramento - Telefonia")
    df_view = df_filtered_date[df_filtered_date['command_type'] == 'addphone']
    
    if df_view.empty:
        st.warning("Nenhum comando de Telefonia encontrado.")
    else:
        render_metrics(df_view)
        st.markdown("---")
        render_charts(df_view)
        st.markdown("---")
        render_data_table(df_view)

elif selected_view == 'Base Completa':
    st.title("Base Completa (Raw Data)")
    st.write(f"Total: {len(df_filtered_date)}")
    st.dataframe(df_filtered_date, use_container_width=True)

elif selected_view == 'Relatórios':
    st.title("📑 Exportação de Relatórios")
    st.markdown("Selecione os dados e colunas para gerar seu relatório em Excel.")
    
    col_filt1, col_filt2 = st.columns(2)
    
    with col_filt1:
        all_status = sorted(df_filtered_date['status'].unique())
        selected_status_rep = st.multiselect("Filtrar por Status", all_status, default=all_status)
        
    with col_filt2:
        all_types = sorted(df_filtered_date['command_type'].unique())
        selected_types_rep = st.multiselect("Filtrar por Tipo de Comando", all_types, default=all_types)
        
    df_rep = df_filtered_date.copy()
    if selected_status_rep:
        df_rep = df_rep[df_rep['status'].isin(selected_status_rep)]
    if selected_types_rep:
        df_rep = df_rep[df_rep['command_type'].isin(selected_types_rep)]
        
    st.markdown("---")
    
    all_columns = df_rep.columns.tolist()
    selected_cols_rep = st.multiselect("Selecionar Colunas", all_columns, default=all_columns)
    
    if not selected_cols_rep:
        st.error("Selecione pelo menos uma coluna.")
    else:
        df_export = df_rep[selected_cols_rep]
        
        st.subheader("Pré-visualização")
        st.dataframe(df_export.head(), use_container_width=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Relatório')
            
        st.download_button(
            label="📥 Baixar Excel",
            data=buffer.getvalue(),
            file_name="relatorio_provisionamento.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

# --- Auto Refresh Logic ---
if auto_refresh:
    time.sleep(30)
    st.rerun()
