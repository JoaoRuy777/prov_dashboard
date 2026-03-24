
import psycopg2
import sys

def test_conn():
    print("Testing dashboard database connection...")
    try:
        conn = psycopg2.connect(
            host="187.18.152.198",
            port="5432",
            dbname="provisionamento_core",
            user="dashboard",
            password="w33@4035DashBoard",
            connect_timeout=5
        )
        print("Dashboard DB connection: SUCCESS")
        conn.close()
    except Exception as e:
        print(f"Dashboard DB connection: FAILED - {e}")

    print("\nTesting migration database connection...")
    try:
        conn = psycopg2.connect(
            host="146.235.60.111",
            port="5432",
            dbname="ins",
            user="eng_dashboard",
            password="w33@4035DashBoard",
            connect_timeout=5
        )
        print("Migration DB connection: SUCCESS")
        conn.close()
    except Exception as e:
        print(f"Migration DB connection: FAILED - {e}")

if __name__ == "__main__":
    test_conn()
