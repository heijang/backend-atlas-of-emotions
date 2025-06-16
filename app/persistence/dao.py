import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2

class PostgresDAO:
    def __init__(self):
        dotenv_path = Path(__file__).parent.parent.parent / "ENV" / ".env"
        if dotenv_path.exists():
            load_dotenv(dotenv_path=dotenv_path)
        self.host = os.getenv("POSTGRES_HOST")
        self.port = os.getenv("POSTGRES_PORT")
        self.db = os.getenv("POSTGRES_DB")
        self.user = os.getenv("POSTGRES_USER")
        self.password = os.getenv("POSTGRES_PASSWORD")
        self.conn = None

    def connect(self):
        self.conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.db,
            user=self.user,
            password=self.password,
        )

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def execute_query(self, query, params=None):
        if self.conn is None:
            self.connect()
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return None

    def get_connection(self):
        if self.conn is None:
            self.connect()
        return self.conn

class ReportDAO(PostgresDAO):
    ...

if __name__ == "__main__":
    dao = PostgresDAO()
    try:
        dao.connect()
        print("DB 연결 성공!")
        result = dao.execute_query("SELECT 1;")
        print(f"SELECT 1 결과: {result}")
    except Exception as e:
        print(f"DB 연결 또는 쿼리 실패: {e}")
    finally:
        dao.close() 