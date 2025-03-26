from typing import Any, List, Tuple
from psycopg2 import pool
from contextlib import contextmanager
from datetime import datetime
import traceback

RowType = Tuple[Any, Any] | None
RowsType = List[RowType]

class PgsqlStorage:
    WALLET_TRANSFER_LOG_CREATE = """CREATE TABLE IF NOT EXISTS wallet_transfer_log (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        amount NUMERIC NOT NULL,
        dest TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""

    WALLET_STAKE_LOG_CREATE = """CREATE TABLE IF NOT EXISTS wallet_stake_log (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        amount NUMERIC NOT NULL,
        dest TEXT NOT NULL,
        total_stake NUMERIC NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""

    VALIDATOR_STAKE_CREATE = """CREATE TABLE IF NOT EXISTS validator_stake (
        id SERIAL PRIMARY KEY,
        hotkey TEXT NOT NULL,
        subnet INTEGER NOT NULL,
        stake NUMERIC NOT NULL,
        stake_weight NUMERIC NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""

    def __init__(self, database="metagraph"):
        self.database = database
        self.tabledata = []
        try:
            self.connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                user='tao',
                password='umobile$prabayar',
                host='127.0.0.1',
                port='5432',
                database=database
            )

            with self.get_connection_from_pool() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SET TIME ZONE 'UTC';")
                    cursor.execute(PgsqlStorage.WALLET_TRANSFER_LOG_CREATE)
                    cursor.execute(PgsqlStorage.WALLET_STAKE_LOG_CREATE)
                    cursor.execute(PgsqlStorage.VALIDATOR_STAKE_CREATE)
                    connection.commit()

        except Exception:
            errors = f"write row failed: {traceback.print_exc()}"
            print(errors)

    def __exit__(self):
        self.close_connection_pool()

    def close_connection_pool(self):
        self.connection_pool.closeall()

    @contextmanager
    def get_connection_from_pool(self):
        connection = self.connection_pool.getconn()
        try:
            yield connection
        finally:
            self.connection_pool.putconn(connection)

    def insert_transfer_log(self, name: str, balance: float, dest: str) -> bool:
        insert_sql = """INSERT INTO wallet_transfer_log (
                        name, amount, dest
                    ) VALUES (
                        %s, %s, %s
                    )"""
        try:
            with self.get_connection_from_pool() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(insert_sql, [name, balance, dest])
                connection.commit()
        except Exception:
            errors = f"write_register failed: {traceback.print_exc()}"
            print(errors)
            return False

        return True

    def insert_stake_log(self, name: str, amount: float, dest: str, total_stake: float) -> bool:
        insert_sql = """INSERT INTO wallet_stake_log (
                         name, amount, dest, total_stake
                     ) VALUES (
                         %s, %s, %s ,%s
                     )"""
        try:
            with self.get_connection_from_pool() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(insert_sql, [name, amount, dest, total_stake])
                connection.commit()
        except Exception:
            errors = f"write_register failed: {traceback.print_exc()}"
            print(errors)
            return False

        return True

    def insert_validator_stake(self, hotkey: str, subnet: int, stake: float) -> bool:
        insert_sql = """INSERT INTO validator_stake (
                            hotkey, subnet, stake, stake_weight
                        ) VALUES (
                            %s, %s, %s ,%s
                        )"""
        try:
            with self.get_connection_from_pool() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(insert_sql, [hotkey, subnet, stake, stake])
                connection.commit()
        except Exception:
            errors = f"write_register failed: {traceback.print_exc()}"
            print(errors)
            return False

        return True
