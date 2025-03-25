from typing import Any, List, Tuple
from psycopg2 import pool
from psycopg2.extras import DictCursor
from contextlib import contextmanager
from datetime import datetime
import traceback
import bittensor

from pydantic import BaseModel

RowType = Tuple[Any, Any] | None
RowsType = List[RowType]

class PgsqlStorage:
    def __init__(self, database = "metagraph"):
        self.database = database
        self.tabledata = []
        try:
            self.connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                user='metagraph',
                password='hJ1}vO0)tI',
                # host='127.0.0.1',
                host='162.244.82.223',
                port='5432',
                database='metagraph'
            )
            
            with self.get_connection_from_pool() as connection:
                with connection.cursor() as cursor:
                    # Set the session to use UTC timezone
                    cursor.execute("SET TIME ZONE 'UTC';")
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
    
    def insert_transfer_log(self, name:str, balance:float,dest:str) -> bool:
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
        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
            errors = f"write_register failed: {traceback.print_exc()}"
            print(errors)
            return False

        return True
        
