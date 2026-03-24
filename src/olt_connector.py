import paramiko

# Monkeypatch for paramiko 3+ / sshtunnel compatibility
# MUST be done before importing sshtunnel
if not hasattr(paramiko, "DSSKey"):
    try:
        paramiko.DSSKey = paramiko.dsskey.DSSKey
    except (AttributeError, ImportError):
        pass

from sshtunnel import SSHTunnelForwarder
from netmiko import ConnectHandler
import re
import pandas as pd
import streamlit as st
import psycopg2

class OLTConnection:
    def __init__(self, olt_ip, user_override=None, pass_override=None):
        self.olt_ip = olt_ip
        self.user = user_override
        self.password = pass_override
        self.port = None # Default None so we don't accidentally override standard ports
        
        # Jump Host Config 
        # Ideally this should be in secrets.toml or env vars, but we use constants here as requested
        self.jump_host = '187.18.152.198'
        self.jump_port = 2222
        self.jump_user = 'dashboard'
        self.jump_pass = 'w33@4035DashBoard'
        
        # If credentials not provided, fetch from DB
        if not self.user or not self.password:
            self._fetch_credentials()

    def _get_db_connection(self):
        """Helper to get the appropriate DB for this OLT"""
        try:
            from src.database import get_db_for_olt
            return get_db_for_olt(self.olt_ip)
        except Exception as e:
            print(f"Failed to route DB connection internally: {e}")
            return None

    def _fetch_credentials(self):
        """Fetches credentials from configuracaoprofile for the given OLT IP."""
        conn = self._get_db_connection()
        if not conn:
            return

        try:
            query = "SELECT usuario, senha, porta FROM public.configuracaoprofile WHERE endereco = %s LIMIT 1"
            df = pd.read_sql(query, conn, params=[self.olt_ip])
            if not df.empty:
                self.user = df.iloc[0]['usuario']
                self.password = df.iloc[0]['senha'] 
                if df.iloc[0]['porta']:
                    self.port = int(df.iloc[0]['porta'])
            else:
                print(f"No credentials found for {self.olt_ip} in database.")
                # We don't raise here, allow execute_command to handle missing user
        except Exception as e:
            print(f"Error fetching credentials for {self.olt_ip}: {e}")
        finally:
            conn.close()

    def execute_command(self, vendor, slot=None, port=None):
        """
        Connects and runs vendor-specific commands via SSH Tunnel.
        """
        if not self.user or not self.password:
            return None, "Credenciais não encontradas e não fornecidas."

        # Determine Protocol/Port for OLT
        olt_protocol_port = 22
        device_type = 'generic_termserver'
        
        if vendor == 'Nokia':
            device_type = 'nokia_sros'
            olt_protocol_port = 22
        elif vendor == 'Zhone':
            device_type = 'cisco_ios_telnet'
            olt_protocol_port = 23
            
        # Allow DB override if logic matches known patterns (e.g. non-std SSH)
        if self.port and self.port != 22 and vendor == 'Nokia':
             olt_protocol_port = self.port
        if self.port and self.port != 23 and vendor == 'Zhone':
             olt_protocol_port = self.port



        try:
            output_text = ""
            
            # Setup SSH Tunnel
            # We map localhost:random -> jump_host -> olt_ip:olt_protocol_port
            with SSHTunnelForwarder(
                (self.jump_host, self.jump_port),
                ssh_username=self.jump_user,
                ssh_password=self.jump_pass,
                remote_bind_address=(self.olt_ip, olt_protocol_port)
            ) as tunnel:
                
                # Netmiko connects to LOCALHOST port provided by tunnel
                netmiko_params = {
                    'device_type': device_type,
                    'host': '127.0.0.1',
                    'port': tunnel.local_bind_port, # The random local port
                    'username': self.user,
                    'password': self.password,
                    'global_delay_factor': 4,
                    'session_log': 'debug_netmiko.log',
                    'fast_cli': False,
                    'banner_timeout': 60,
                    'auth_timeout': 60
                }
                
                # Connect
                try:
                    # Nokia - Keep Netmiko
                    if vendor == 'Nokia':
                        with ConnectHandler(**netmiko_params) as net_connect:
                            # environment inhibit-alarms might change prompt, causing timeout. 
                            # We try running show directly.
                            cmds = [
                                f"show equipment ont status pon 1/1/{slot}/{port} | no-more"
                            ]
                            for cmd in cmds:
                                output_text += f"\n--- CMD: {cmd} ---\n"
                                # Relaxed matching and higher timeout
                                output_text += net_connect.send_command(
                                    cmd, 
                                    strip_prompt=False, 
                                    strip_command=False, 
                                    read_timeout=60,
                                    expect_string=r"[#>]" # Generic prompt match
                                )

                    # Zhone - Switch to telnetlib for full control
                    elif vendor == 'Zhone':
                        # We must bypass Netmiko's strict login for Zhone because of "login:" prompt
                        # Netmiko expects "Username:"
                        import telnetlib
                        
                        # Connect to the LOCAL end of the tunnel
                        tn = telnetlib.Telnet('127.0.0.1', tunnel.local_bind_port, timeout=10)
                        
                        # Handle Login
                        # Expect 'login:'
                        tn.read_until(b"login:", timeout=10)
                        tn.write(self.user.encode('ascii') + b"\n")
                        
                        # Expect 'Password:' (or 'pass:', 'senha:')
                        tn.read_until(b"assword:", timeout=10)
                        tn.write(self.password.encode('ascii') + b"\n")
                        
                        # Expect Prompt (Assume '>' or '#')
                        tn.read_until(b">", timeout=10)
                        
                        # Send Command
                        # setline 0
                        tn.write(b"setline 0\n")
                        tn.read_until(b">", timeout=5)
                        
                        cmd_show = f"onu showall {slot}/{port}"
                        output_text += f"\n--- CMD: {cmd_show} ---\n"
                        tn.write(cmd_show.encode('ascii') + b"\n")
                        
                        # Loop for output and paging
                        # Zhone paging: "Do you want to continue?" -> Send "yes" (or just enter?) usually "yes"
                        while True:
                            # Read chunk
                            chunk = tn.read_until(b"continue?", timeout=5)
                            output_text += chunk.decode('ascii', errors='ignore')
                            
                            if b"continue?" in chunk:
                                tn.write(b"yes\n")
                            else:
                                break
                        
                        tn.write(b"setline 30\n")
                        tn.close()


                    if vendor == 'Nokia':
                         return self._parse_output(output_text, vendor), output_text
                    else:
                         # Standardize return for Zhone
                         return self._parse_output(output_text, vendor), output_text

                except Exception as netmiko_err:
                     err_str = str(netmiko_err)
                     if "Authentication failed" in err_str:
                         return None, "Erro de Autenticação: Login ou Senha incorretos na OLT."
                     elif "Connection refused" in err_str:
                         return None, f"Conexão Recusada: Porta {olt_protocol_port} fechada na OLT {self.olt_ip}."
                     elif "timed out" in err_str.lower():
                         return None, f"Timeout de Conexão: A OLT {self.olt_ip} não respondeu no tempo limite."
                     return None, f"Erro na conexão de rede: {netmiko_err}"

        except Exception as e:
            error_msg = f"Erro no Túnel SSH ({self.jump_host}): {str(e)}"
            if "Authentication failed" in str(e):
                error_msg = f"Erro de Autenticação no Jump Host ({self.jump_host}). Verifique as credenciais do dashboard."
            return None, error_msg

    def _parse_output(self, text, vendor):
        """
        Parses raw text into DataFrame.
        """
        data = []
        lines = text.splitlines()
        
        if vendor == 'Nokia':
            # Parsing logic for: show equipment ont status pon 1/1/{slot}/{port}
            # Expected output format needed.
            # Assuming generic table.
            # We will use simple regex for Serial / Status which are key.
            # Example Line: 1/1/3/13   ALCLB3F50247   active   ...
            
            for line in lines:
                # Regex to find Serial (ALCL... or ZNTS:...)
                # Screenshot shows: 1/1/6/1   1/1/6/1/1   ZNTS:3CF2F79A   up   up   -26.3   4.2
                match = re.search(r'\b((?:ALCL|ZNTS)[:A-Z0-9]+)\b', line)
                if match:
                    parts = line.split()
                    serial = match.group(1)
                    
                    # Basic extraction based on typical position if serial is found
                    # parts: [pon, ont, serial, admin, oper, rx, dist]
                    # We map dynamically if length matches expectation, else just raw
                    record = {
                        'Serial': serial,
                        'Status': 'Auth' if 'up' in line.lower() else 'Down', # Simplistic inference
                        'Signal': parts[5] if len(parts) > 6 else 'N/A',
                        'Raw Line': line
                    }
                    
                    # Try to get better status from parts if structure holds
                    # index of serial in parts
                    try:
                        idx = parts.index(serial)
                        if idx + 2 < len(parts):
                            record['Admin'] = parts[idx+1]
                            record['Oper'] = parts[idx+2]
                            record['Status'] = parts[idx+2] # Use Oper status
                    except ValueError:
                        pass
                        
                    data.append(record)

        elif vendor == 'Zhone':
            # Parsing logic for Zhone
            # Similar approach
            for line in lines:
                match = re.search(r'\b(ALCL[A-Z0-9]+|ZNTS[A-Z0-9]+)\b', line)
                if match:
                    record = {'Raw Line': line, 'Serial': match.group(0)}
                    data.append(record)
                    
        if not data:
            return pd.DataFrame() # Empty
            
        return pd.DataFrame(data)

