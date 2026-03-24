import sqlite3
import hashlib
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'users.db')

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            email TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')
    conn.commit()
    
    # Injetar usuário administrador padrão se a tabela estiver vazia
    cursor.execute('SELECT COUNT(*) FROM usuarios')
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            'INSERT INTO usuarios (email, password_hash, role) VALUES (?, ?, ?)',
            ('joao.ruy@interfocus.com.br', _hash_password('teste123'), 'adm')
        )
        conn.commit()
        
    conn.close()

def create_user(email: str, password: str, role: str) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO usuarios (email, password_hash, role) VALUES (?, ?, ?)',
            (email.strip(), _hash_password(password), role)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        print(f"Error creating user: {e}")
        return False

def verify_user(email: str, password: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM usuarios WHERE email = ? AND password_hash = ?', 
                  (email.strip(), _hash_password(password)))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return True, result[0] # Returns True and Role
    return False, None

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT email, role FROM usuarios')
    results = cursor.fetchall()
    conn.close()
    return [{'email': r[0], 'role': r[1]} for r in results]
