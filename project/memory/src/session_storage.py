"""
会话存储模块 - 处理会话和消息的持久化存储
"""
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from src.models import Session, Message, SessionStatus, MessageRole
from src.database import db_manager

class SessionStorage:
    """会话存储管理器"""
    
    def __init__(self):
        self.db = db_manager
    
    def create_session(self, user_id: str, agent_id: str, 
                      title: Optional[str] = None,
                      context_data: Optional[Dict[str, Any]] = None) -> Session:
        """创建新会话"""
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            title=title,
            context_data=context_data,
            status=SessionStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO sessions 
                (session_id, user_id, agent_id, status, title, context_data, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id, user_id, agent_id, session.status.value,
                title, json.dumps(context_data) if context_data else None,
                datetime.now(), datetime.now()
            ))
        
        return session
    
    def update_session_status(self, session_id: str, status: SessionStatus) -> bool:
        """更新会话状态"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                UPDATE sessions 
                SET status = %s, updated_at = %s 
                WHERE session_id = %s
            """, (status.value, datetime.now(), session_id))
            return cursor.rowcount > 0
    
    def update_session_stats(self, session_id: str, total_messages: int, total_tokens: int) -> bool:
        """更新会话统计信息"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                UPDATE sessions 
                SET total_messages = %s, total_tokens = %s, 
                    last_message_at = %s, updated_at = %s
                WHERE session_id = %s
            """, (total_messages, total_tokens, datetime.now(), datetime.now(), session_id))
            return cursor.rowcount > 0
    
    def add_message(self, session_id: str, role: MessageRole, content: str,
                   content_type: str = "text", token_count: int = 0,
                   metadata: Optional[Dict[str, Any]] = None,
                   reply_to_message_id: Optional[int] = None) -> Message:
        """添加新消息"""
        # 获取当前消息序列号
        sequence_number = self._get_next_sequence_number(session_id)
        
        message = Message(
            message_id=None,  # 将在插入时生成
            session_id=session_id,
            role=role,
            content=content,
            content_type=content_type,
            token_count=token_count,
            metadata=metadata,
            sequence_number=sequence_number,
            is_compressed=False,
            reply_to_message_id=reply_to_message_id,
            created_at=datetime.now()
        )
        
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO messages 
                (session_id, role, content, content_type, token_count, metadata, 
                 sequence_number, is_compressed, reply_to_message_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id, role.value, content, content_type, token_count,
                json.dumps(metadata) if metadata else None,
                sequence_number, False, reply_to_message_id, datetime.now()
            ))
            
            message.message_id = cursor.lastrowid
        
        # 更新会话统计
        self._increment_message_stats(session_id, token_count)
        
        return message
    
    def _get_next_sequence_number(self, session_id: str) -> int:
        """获取下一条消息的序列号"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT MAX(sequence_number) as max_seq 
                FROM messages 
                WHERE session_id = %s
            """, (session_id,))
            
            result = cursor.fetchone()
            return (result['max_seq'] + 1) if result['max_seq'] else 1
    
    def _increment_message_stats(self, session_id: str, token_count: int):
        """增加会话消息统计"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                UPDATE sessions 
                SET total_messages = total_messages + 1,
                    total_tokens = total_tokens + %s,
                    last_message_at = %s,
                    updated_at = %s
                WHERE session_id = %s
            """, (token_count, datetime.now(), datetime.now(), session_id))
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话信息"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM sessions WHERE session_id = %s
            """, (session_id,))
            
            result = cursor.fetchone()
            if result:
                return self._row_to_session(result)
            return None
    
    def get_messages(self, session_id: str, limit: Optional[int] = None,
                    start_sequence: Optional[int] = None,
                    end_sequence: Optional[int] = None) -> List[Message]:
        """获取会话消息"""
        with self.db.get_cursor() as cursor:
            query = "SELECT * FROM messages WHERE session_id = %s"
            params = [session_id]
            
            if start_sequence is not None:
                query += " AND sequence_number >= %s"
                params.append(start_sequence)
            
            if end_sequence is not None:
                query += " AND sequence_number <= %s"
                params.append(end_sequence)
            
            query += " ORDER BY sequence_number ASC"
            
            if limit:
                query += " LIMIT %s"
                params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            return [self._row_to_message(row) for row in results]
    
    def get_uncompressed_messages(self, session_id: str) -> List[Message]:
        """获取未压缩的消息"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM messages 
                WHERE session_id = %s AND is_compressed = FALSE
                ORDER BY sequence_number ASC
            """, (session_id,))
            
            results = cursor.fetchall()
            return [self._row_to_message(row) for row in results]
    
    def mark_message_compressed(self, message_ids: List[int], compression_version: int):
        """标记消息为已压缩"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                UPDATE messages 
                SET is_compressed = TRUE, compression_version = %s
                WHERE message_id IN (%s)
            """ % (compression_version, ','.join(map(str, message_ids))))
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话（级联删除相关数据）"""
        with self.db.get_cursor() as cursor:
            cursor.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
            return cursor.rowcount > 0
    
    def _row_to_session(self, row: Dict[str, Any]) -> Session:
        """将数据库行转换为 Session 对象"""
        return Session(
            session_id=row['session_id'],
            user_id=row['user_id'],
            agent_id=row['agent_id'],
            status=SessionStatus(row['status']),
            title=row['title'],
            context_data=json.loads(row['context_data']) if row['context_data'] else None,
            total_messages=row['total_messages'],
            total_tokens=row['total_tokens'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            last_message_at=row['last_message_at'],
            expires_at=row['expires_at']
        )
    
    def _row_to_message(self, row: Dict[str, Any]) -> Message:
        """将数据库行转换为 Message 对象"""
        return Message(
            message_id=row['message_id'],
            session_id=row['session_id'],
            role=MessageRole(row['role']),
            content=row['content'],
            content_type=row['content_type'],
            token_count=row['token_count'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None,
            sequence_number=row['sequence_number'],
            is_compressed=row['is_compressed'],
            compression_version=row['compression_version'],
            parent_message_id=row['parent_message_id'],
            reply_to_message_id=row['reply_to_message_id'],
            created_at=row['created_at']
        )