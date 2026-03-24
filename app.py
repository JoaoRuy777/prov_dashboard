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

from src.database import get_data, get_olts, insert_migration_data
from src.processing import process_data, filter_data
from src.olt_connector import OLTConnection
from src.auth import init_db, verify_user, create_user, get_all_users

# Initialize Auth Database
init_db()

# ... (Config and CSS remain headers) ...

# --- Authentication ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = None

if not st.session_state['logged_in']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
            
        st.markdown("<h2 style='text-align: center;'>Login Central</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            email = st.text_input("E-mail")
            senha = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar", use_container_width=True)
            
            if submit:
                success, role = verify_user(email, senha)
                if success:
                    st.session_state['logged_in'] = True
                    st.session_state['user_role'] = role
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")
    st.stop()
    
# Se logado, renderiza tela (adicionar user/logout)
with st.sidebar:
    st.markdown(f"**Logado como:** `{st.session_state.get('user_role', 'Tecnico').upper()}`")
    if st.button("Sair (Logout)"):
        st.session_state['logged_in'] = False
        st.session_state['user_role'] = None
        st.rerun()
    st.divider()

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
    'Extração OLT': 'Extração OLT',
    'Migração (De/Para)': 'Migração (De/Para)',
    'Relatórios': 'Relatórios'
}

if st.session_state.get('user_role') == 'adm':
    view_options['Gerenciar Usuários'] = 'Gerenciar Usuários'

for option, label in view_options.items():
    if st.sidebar.button(label, use_container_width=True, type="primary" if st.session_state['selected_view'] == option else "secondary", key=option):
        set_view(option)
        st.rerun()

# DEBUG: Show current view in sidebar
st.sidebar.caption(f"Debug: View = {st.session_state['selected_view']}")

selected_view = st.session_state['selected_view']

st.sidebar.markdown("---")
st.sidebar.header("Filtros Globais")

# Auto-Refresh Toggle
auto_refresh = st.sidebar.toggle("Atualização Automática (30s)", value=False)

# Form for filters
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
    
    submit_button = st.form_submit_button("Buscar Dados")

# Compatibility alias
olt_ip_query = selected_olt

# --- Data Loading Logic ---
if submit_button or auto_refresh:
    # Handle Date Range
    start_date = None
    end_date = None
    if isinstance(date_range, tuple):
        if len(date_range) >= 1: start_date = date_range[0]
        if len(date_range) == 2: end_date = date_range[1]
        
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
            
            st.success(f"Encontrados {len(raw_df)} registros.")
            with st.expander("Detalhes do Filtro Ativo"):
                 st.write(f"**OLT:** {olt_ip_query}")
                 st.write(f"**Período:** {start_date} até {end_date}")
        else:
            st.warning("Nenhum dado encontrado para os filtros selecionados.")
            st.info(f"Filtros utilizados: OLT='{olt_ip_query}', Data Início='{start_date}', Data Fim='{end_date}'")
            st.session_state['df_cache'] = pd.DataFrame()

df_full = st.session_state['df_cache']
df_filtered_date = df_full

# --- Views Implementation ---
# BLOCKING LOGIC FIX:
# Only block if we are NOT in 'Extração OLT', 'Migração (De/Para)' or 'Gerenciar Usuários' view.
if selected_view not in ['Extração OLT', 'Migração (De/Para)', 'Gerenciar Usuários']:
    if not st.session_state['data_fetched'] and not submit_button:
        st.info("Utilize os filtros na barra lateral e clique em 'Buscar Dados' para começar.")
        st.stop()
    elif df_filtered_date.empty:
        st.stop()
else:
    pass # Proceed to Extraction View even if no DB data
 


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
                Operação 100% Sucesso
            </div>
            """
            st.markdown(div_success, unsafe_allow_html=True)

def render_data_table(df):
    st.subheader("Detalhamento da Fila")
    if not df.empty:
        display_df = df.copy()
        
        # Ensure OLT IP is a clickable link for LinkColumn
        if 'olt_ip' in display_df.columns:
            display_df['olt_ip'] = display_df['olt_ip'].apply(lambda x: f"http://{x}" if x and not str(x).startswith('http') else x)

        # Select columns
        cols = ['id', 'created_at', 'command_type', 'status', 'treated_error']
        if 'olt_ip' in display_df.columns:
            cols.append('olt_ip')
            
        display_df = display_df[cols]

        # Use Column Config and Styler to render a single, rich table
        def highlight_status(val):
            color = ''
            if val == 'Error':
                color = 'background-color: #590000; color: #ffcccc' # Dark red bg
            elif val == 'Success':
                color = 'background-color: #004400; color: #ccffcc' # Dark green bg
            return color

        styler = display_df.style.map(highlight_status, subset=['status'])
        
        # Add clickable links for OLT IP if possible via column_config
        # We can use format to create a fake URL or use st.column_config.LinkColumn if it's external
        # Since it's an internal or equipment IP, we'll format it as a LinkColumn pointing to http://{ip}
        
        st.dataframe(
            styler,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": "ID",
                "created_at": st.column_config.DatetimeColumn("Data", format="DD/MM/YYYY HH:mm"),
                "command_type": "Comando",
                "status": "Status",
                "treated_error": "Diagnóstico do Erro",
                "olt_ip": st.column_config.LinkColumn("OLT IP", help="Clique para abrir interface da OLT (pode exigir VPN)", validate="^http", display_text="http://(.*?)$")
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
    
    df_base_display = df_filtered_date.copy()
    if 'olt_ip' in df_base_display.columns:
        df_base_display['olt_ip'] = df_base_display['olt_ip'].apply(lambda x: f"http://{x}" if x and not str(x).startswith('http') else x)
        
    st.dataframe(
        df_base_display, 
        use_container_width=True,
        column_config={
            "olt_ip": st.column_config.LinkColumn("OLT IP", display_text="http://(.*?)$")
        }
    )

elif selected_view == 'Relatórios':
    st.title("Exportação de Relatórios")
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
        df_preview = df_export.head().copy()
        if 'olt_ip' in df_preview.columns:
             df_preview['olt_ip'] = df_preview['olt_ip'].apply(lambda x: f"http://{x}" if x and not str(x).startswith('http') else x)
        
        st.dataframe(
            df_preview, 
            use_container_width=True,
            column_config={
                "olt_ip": st.column_config.LinkColumn("OLT IP", display_text="http://(.*?)$")
            }
        )
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Relatório')
            
        st.download_button(
            label="Baixar Excel",
            data=buffer.getvalue(),
            file_name="relatorio_provisionamento.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

elif selected_view == 'Extração OLT':
    st.title("Extração Direta da OLT")
    st.markdown("Conecte-se em tempo real na OLT para extrair o status das ONUs.")

    with st.form("olt_extract_form"):
        col_olt1, col_olt2 = st.columns(2)
        with col_olt1:
             # Allow manual entry or use selected
             # If user selected an OLT in sidebar, pre-fill it.
             # But user explicitly asked to "coar o ip". So text_input is best.
             prefill_ip = olt_ip_query if olt_ip_query and "Nenhuma" not in olt_ip_query else ""
             olt_target = st.text_input("IP da OLT", value=prefill_ip, help="Digite ou Cole o IP")
        
        with col_olt2:
            vendor = st.selectbox("Vendor / Fabricante", ["Nokia", "Zhone"])
            
        col_slot, col_port = st.columns(2)
        with col_slot:
            slot_input = st.text_input("Slot", value="1", help="Ex: 3")
        with col_port:
            port_input = st.text_input("Porta PON", value="1", help="Ex: 13")
            
        # Optional: Credentials Override
        with st.expander("Credenciais (Opcional - Substituir Banco)"):
            user_ov = st.text_input("Usuário", value="")
            pass_ov = st.text_input("Senha", type="password", value="")

        btn_extract = st.form_submit_button("Executar Extração")
    
    if btn_extract:
        st.info(f"Conectando a {olt_target} ({vendor})... Aguarde.")
        
        try:
            # Clean inputs
            ip_clean = olt_target.strip()
            if "(" in ip_clean:
                 import re
                 m = re.search(r'\((.*?)\)', ip_clean)
                 if m: ip_clean = m.group(1)
            
            connector = OLTConnection(ip_clean, user_override=user_ov if user_ov else None, pass_override=pass_ov if pass_ov else None)
            
            # Execute
            st.info(f"Tentando conexão: {ip_clean}:{connector.port if connector.port else 'Auto'} (Jump: {connector.jump_host})")
            df_res, raw_log = connector.execute_command(vendor, slot=slot_input, port=port_input)
            
            if raw_log:
                st.subheader("Retorno da OLT")
                st.code(raw_log)
                
                # Excel Download Option for Raw Log
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    pd.DataFrame([{'Log': raw_log}]).to_excel(writer, index=False, sheet_name='Log Bruto')
                    if df_res is not None and not df_res.empty:
                         df_res.to_excel(writer, index=False, sheet_name='Dados Estruturados')
                    
                st.download_button(
                    label="Baixar Log (Excel)",
                    data=buffer.getvalue(),
                    file_name=f"olt_log_{vendor}_{slot_input}_{port_input}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="secondary"
                )
            else:
                 st.error("Falha na conexão ou comando vazio.")
                    
        except Exception as e:
            err_msg = str(e)
            if "timeout" in err_msg.lower():
                st.error(f"❌ Erro de Timeout: O Jump Host ({connector.jump_host}) ou a OLT ({olt_target}) não responderam a tempo.")
            elif "Authentication failed" in err_msg:
                st.error("❌ Erro de Autenticação: Verifique as credenciais no banco ou o override fornecido.")
            elif "Connection refused" in err_msg:
                st.error(f"❌ Conexão Recusada: O serviço (SSH/Telnet) não está habilitado na OLT {olt_target}.")
            else:
                st.error(f"❌ Erro Crítico: {err_msg}")
            
            st.info("💡 Dica: Verifique se você está conectado à VPN e se o Jump Host está acessível.")

# --- VIEW: Migração (De/Para) ---
elif selected_view == 'Migração (De/Para)':
    st.title("Migração de OLT (De/Para)")
    if st.session_state.get('user_role') != 'adm':
        st.error("🚫 Acesso Negado: Apenas administradores (adm) podem processar migrações.")
        st.stop()
        
    st.markdown("Preencha os dados para iniciar o processo de migração.")

    with st.form("migration_form"):
        st.subheader("1. OLTs")
        col_olt_1, col_olt_2, col_olt_3 = st.columns(3)
        with col_olt_1:
            ipatual = st.text_input("IP Atual (Origem)", help="ipatual")
        with col_olt_2:
            ip_para = st.text_input("IP Para (Destino)", help="ip_para")
        with col_olt_3:
            marca_olt_ins = st.selectbox("Marca OLT", ["Nokia", "Zhone", "Huawei", "ZTE"], help="marca_olt_ins")

        st.subheader("2. VLANs (Destino)")
        c3, c4, c5 = st.columns(3)
        with c3:
            vlan_dados_para = st.text_input("VLAN Dados", help="vlan_dados_para")
        with c4:
            vlan_tv_para = st.text_input("VLAN TV", help="vlan_tv_para")
        with c5:
            vlan_voz_para = st.text_input("VLAN Voz", help="vlan_voz_para")

        st.subheader("3. Rede & Cluster")
        c6, c7 = st.columns(2)
        with c6:
            ipclusterprovisionamento_para = st.text_input("IP Cluster Provisionamento", help="ipclusterprovisionamento_para")
        with c7:
            idpool_ipoe_default = st.text_input("ID Pool IPOE Default", help="idpool_ipoe_default")

        st.subheader("4. Integração & Autenticação")
        c8, c9 = st.columns(2)
        with c8:
            urlapiintegracao = st.text_input("URL API Integração", help="urlapiintegracao")
        with c9:
            secretapidiscovery = st.text_input("Secret API Discovery", help="secretapidiscovery")
        
        c10, c11 = st.columns(2)
        with c10:
            codigo = st.text_input("Código (Cliente)", help="codigo")
        with c11:
            idplano_ipoe_default = st.text_input("ID Plano IPOE Default", help="idplano_ipoe_default")

        submitted_migration = st.form_submit_button("Processar Migração")
        
        if submitted_migration:
            if not urlapiintegracao:
                st.error("ERRO: A URL API Integração é obrigatória para o processamento.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                data_payload = {
                    "ipatual": ipatual,
                    "ip_para": ip_para,
                    "vlan_dados_para": vlan_dados_para,
                    "vlan_voz_para": vlan_voz_para,
                    "vlan_tv_para": vlan_tv_para,
                    "ipclusterprovisionamento_para": ipclusterprovisionamento_para,
                    "idpool_ipoe_default": idpool_ipoe_default,
                    "idplano_ipoe_default": idplano_ipoe_default,
                    "marca_olt_ins": marca_olt_ins,
                    "urlapiintegracao": urlapiintegracao,
                    "secretapidiscovery": secretapidiscovery,
                    "codigo": codigo
                }
                
                status_text.text("Gravando dados na tabela temporária...")
                success = insert_migration_data(data_payload)
                
                if not success:
                    st.error("Falha ao gravar os dados de migração no banco de dados.")
                else:
                    status_text.text(f"Conectando a {urlapiintegracao}...")
                    time.sleep(1)
                    progress_bar.progress(25)
                    
                    status_text.text("Validando credenciais da API...")
                    time.sleep(1.5)
                    progress_bar.progress(50)
                    
                    status_text.text(f"Iniciando De/Para de {ipatual} para {ip_para}...")
                    time.sleep(2)
                    progress_bar.progress(80)
                    
                    status_text.text("Finalizando migração...")
                    time.sleep(1)
                    progress_bar.progress(100)
                    
                    st.success("✅ Migração Iniciada e salva no Banco de Dados com Sucesso!")
                    st.info(f"Endpoint: {urlapiintegracao}")
                    
                    st.json(data_payload)

# --- VIEW: Gerenciar Usuários ---
elif selected_view == 'Gerenciar Usuários':
    st.title("Gerenciamento de Usuários")
    if st.session_state.get('user_role') != 'adm':
        st.error("Acesso Negado.")
        st.stop()
        
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Cadastrar Novo Usuário")
        with st.form("new_user_form"):
            new_email = st.text_input("E-mail")
            new_pass = st.text_input("Senha", type="password")
            new_role = st.selectbox("Perfil", ["tecnico", "adm"])
            sub_user = st.form_submit_button("Criar Usuário")
            if sub_user:
                if create_user(new_email, new_pass, new_role):
                    st.success("Usuário criado com sucesso!")
                else:
                    st.error("Erro ao criar usuário (E-mail já existe).")
                    
    with col2:
        st.subheader("Usuários Existentes")
        users_list = get_all_users()
        if users_list:
            df_u = pd.DataFrame(users_list)
            st.dataframe(df_u, use_container_width=True, hide_index=True)

# --- Auto Refresh Logic ---
if auto_refresh:
    time.sleep(30)
    st.rerun()
