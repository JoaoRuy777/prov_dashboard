# Documentação do Dashboard de Provisionamento

## 1. Visão Geral
Esta aplicação é um dashboard interativo desenvolvido em **Python** utilizando **Streamlit**, focado no monitoramento de falhas e sucessos no provisionamento de serviços (Internet, TV, Telefonia).

Além da visualização de dados históricos do banco de dados, o sistema possui uma funcionalidade avançada de **Extração Direta da OLT**, permitindo conexão em tempo real com equipamentos Nokia e Zhone através de um túnel SSH seguro.

## 2. Arquitetura do Sistema

### Backend
- **Core:** Python 3.12+
- **Framework Web:** Streamlit
- **Manipulação de Dados:** Pandas
- **Conectividade de Rede:**
    - `netmiko`: Para conexão SSH/Telnet com as OLTs.
    - `sshtunnel`: Para criar túneis SSH através de um Jump Host (Bastion/Stack).
    - `paramiko` (v2.12.0): Biblioteca SSH base.

### Banco de Dados
- **PostgreSQL**: O sistema conecta-se a um banco de dados PostgreSQL para buscar:
    - Histórico de provisionamento (`public.filaprovisionamento`).
    - Credenciais e endereços das OLTs (`public.configuracaoprofile`).

### Fluxo de Conexão OLT (Túnel SSH)
Para acessar as OLTs, que estão em uma rede privada, o sistema utiliza um **Jump Host** intermediário.
1.  A aplicação cria um túnel SSH local (`localhost:random_port` -> `Jump Host` -> `OLT_IP:22/23`).
2.  O `netmiko` conecta-se na porta local do túnel.
3.  Os comandos são enviados de forma segura através desta ponte.

## 3. Funcionalidades

### 3.1 Visão Geral e Monitoramento
- **Métricas:** Total de comandos, taxas de sucesso e erro.
- **Gráficos:** Distribuição por status e ranking de motivos de erro.
- **Tabela Detalhada:** Lista completa dos comandos com status, data e diagnóstico.
- **Filtros:** Seleção por OLT e intervalo de datas.

### 3.2 Abas Específicas
- **Dados (Internet) / TV / Telefonia:** Visões filtradas por tipo de serviço.
- **Base Completa:** Visualização tabular bruta ("Raw Data").

### 3.3 Extração Direta da OLT
Permite executar comandos de diagnóstico diretamente no equipamento.
- **Suporte Multi-Vendor:**
    - **Nokia:** Conexão SSH. Comando: `show equipment ont status pon ...`
    - **Zhone:** Conexão Telnet. Comando: `onu showall ...`
- **Output:** Exibe o retorno bruto (Raw Log) do equipamento para análise técnica.
- **Exportação:** Permite baixar o log gerado em Excel.

### 3.4 Relatórios
- Interface para seleção de colunas e filtros personalizados.
- Exportação dos dados filtrados para planilha Excel (`.xlsx`).

## 4. Configuração e Instalação

### Pré-requisitos
- Python 3.10 ou superior.
- Acesso à rede do Jump Host (para funcionalidade de OLT).

### Instalação das Dependências
```bash
pip install -r requirements.txt
```
Principais bibliotecas: `streamlit`, `pandas`, `psycopg2-binary`, `netmiko`, `sshtunnel`, `paramiko==2.12.0`.

### Configuração de Credenciais
1.  **Banco de Dados:** As credenciais devem estar no arquivo `.streamlit/secrets.toml`:
    ```toml
    [postgres]
    host = "..."
    dbname = "..."
    user = "..."
    password = "..."
    port = 5432
    ```
2.  **Jump Host:** Atualmente, as credenciais do Jump Host são configuradas internamente no módulo `src/olt_connector.py`.

### Execução
Para iniciar o dashboard:
```bash
streamlit run app.py
```
A aplicação estará acessível tipicamente em `http://localhost:8501`.

## 5. Estrutura de Arquivos
- `app.py`: Ponto de entrada da aplicação. Gerencia a interface e navegação.
- `src/`
    - `database.py`: Gerencia conexão com PostgreSQL.
    - `processing.py`: Lógica de tratamento e limpeza de dados.
    - `olt_connector.py`: Módulo responsável pela conexão SSH/Telnet e Tunneling com as OLTs.
- `requirements.txt`: Lista de dependências do projeto.

## 6. Solução de Problemas Comuns
- **Erro `paramiko.DSSKey`:** Certifique-se de usar `paramiko==2.12.0`. Versões mais recentes (3.0+) removeram suporte a chaves DSS antigas usadas por alguns equipamentos/túneis.
- **Porta em uso:** Se o Streamlit não subir na porta 8501, verifique se já existe um processo rodando ou especifique outra porta: `streamlit run app.py --server.port 8502`.
