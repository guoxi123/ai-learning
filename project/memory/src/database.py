"""
数据库连接管理模块
"""
import os
from typing import Optional
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import pooling
import json
from contextlib import contextmanager

load_dotenv()

class DatabaseManager:
    """数据库连接管理器"""
    
    def __init__(self):
        self.config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', 'chat_system'),
            'port': int(os.getenv('DB_PORT', 3306)),
            'charset': 'utf8mb4',
            'autocommit': False,
        }
        self.connection_pool = pooling.MySQLConnectionPool(
            pool_name="chat_system_pool",
            pool_size=10,
            pool_reset_session=True,
            **self.config
        )
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = self.connection_pool.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    @contextmanager
    def get_cursor(self, dictionary=False):
        """获取数据库游标的上下文管理器"""
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=dictionary)
            try:
                yield cursor
            finally:
                cursor.close()
    
    def initialize_tables(self):
        """初始化数据库表结构"""
        # 这里应该执行 table 文件中的 SQL，在实际使用中可以读取 SQL 文件执行
        # 由于涉及 vector 类型，需要 MySQL 8.0+ 
        pass

# 全局数据库管理器实例
db_manager = DatabaseManager()