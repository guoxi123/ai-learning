"""
会话查询模块 - 提供多层次的会话查询和上下文构建功能
"""
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from src.models import Session, Message, WorkingSession, CompressionVersion
from src.database import db_manager

class SessionQuery:
    """会话查询管理器"""
    
    def __init__(self):
        self.db = db_manager
    
    def get_session_context(self, session_id: str, max_tokens: int = 4000) -> Dict[str, Any]:
        """获取会话上下文，优先从工作会话缓存获取"""
        # 先尝试从工作会话获取缓存
        working_session = self._get_working_session(session_id)
        
        if working_session and self._is_working_session_valid(working_session):
            return self._build_context_from_working_session(working_session, max_tokens)
        
        # 缓存失效，重新构建上下文
        return self._rebuild_session_context(session_id, max_tokens)
    
    def get_compression_traceability(self, session_id: str) -> List[Dict[str, Any]]:
        """获取压缩可追溯性信息"""
        traceability = []
        
        with self.db.get_cursor() as cursor:
            # 获取所有压缩版本
            cursor.execute("""
                SELECT cv.*, cc.strategy, cc.trigger_type
                FROM compression_versions cv
                JOIN compression_configs cc ON cv.config_id = cc.config_id
                WHERE cv.session_id = %s
                ORDER BY cv.version_number ASC
            """, (session_id,))
            
            versions = cursor.fetchall()
            
            for version in versions:
                version_data = {
                    'version_id': version['version_id'],
                    'version_number': version['version_number'],
                    'version_name': version['version_name'],
                    'strategy': version['strategy'],
                    'trigger_type': version['trigger_type'],
                    'start_sequence': version['start_sequence_number'],
                    'end_sequence': version['end_sequence_number'],
                    'compressed_count': version['compressed_message_count'],
                    'compression_ratio': version['compression_ratio'],
                    'created_at': version['created_at'],
                    'messages': []
                }
                
                # 获取该版本包含的消息
                cursor.execute("""
                    SELECT m.*, mcm.message_role_in_compression, mcm.relevance_score
                    FROM messages m
                    JOIN message_compression_map mcm ON m.message_id = mcm.message_id
                    WHERE mcm.version_id = %s
                    ORDER BY m.sequence_number ASC
                """, (version['version_id'],))
                
                messages = cursor.fetchall()
                for msg in messages:
                    version_data['messages'].append({
                        'message_id': msg['message_id'],
                        'role': msg['role'],
                        'content': msg['content'][:100] + '...' if len(msg['content']) > 100 else msg['content'],
                        'sequence_number': msg['sequence_number'],
                        'role_in_compression': msg['message_role_in_compression'],
                        'relevance_score': msg['relevance_score']
                    })
                
                traceability.append(version_data)
        
        return traceability
    
    def get_message_versions(self, message_id: int) -> List[Dict[str, Any]]:
        """获取消息关联的所有压缩版本（双向查询）"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT cv.*, mcm.message_role_in_compression, mcm.relevance_score, mcm.mapped_at, mcm.mapped_by
                FROM message_compression_map mcm
                JOIN compression_versions cv ON mcm.version_id = cv.version_id
                WHERE mcm.message_id = %s
                ORDER BY cv.version_number ASC
            """, (message_id,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_hierarchical_context(self, session_id: str) -> Dict[str, Any]:
        """获取分层上下文视图"""
        context = {
            'layer_1_recent': self._get_layer_1_recent(session_id),
            'layer_2_compressed': self._get_layer_2_compressed(session_id),
            'layer_3_summary': self._get_layer_3_summary(session_id),
            'metadata': {
                'session_id': session_id,
                'generated_at': datetime.now().isoformat(),
                'total_messages': self._count_messages(session_id),
                'compression_versions': self._count_compression_versions(session_id)
            }
        }
        
        return context
    
    def get_active_messages(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的活跃消息"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM messages 
                WHERE session_id = %s AND is_compressed = FALSE
                ORDER BY sequence_number DESC
                LIMIT %s
            """, (session_id, limit))
            
            results = cursor.fetchall()
            return [self._message_to_dict(row) for row in reversed(results)]
    
    def search_sessions(self, user_id: str, status: Optional[str] = None,
                       agent_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索会话"""
        with self.db.get_cursor() as cursor:
            query = "SELECT * FROM sessions WHERE user_id = %s"
            params = [user_id]
            
            if status:
                query += " AND status = %s"
                params.append(status)
            
            if agent_id:
                query += " AND agent_id = %s"
                params.append(agent_id)
            
            query += " ORDER BY updated_at DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            return [self._session_to_dict(row) for row in results]
    
    def get_message_by_sequence(self, session_id: str, sequence_number: int) -> Optional[Dict[str, Any]]:
        """根据序列号获取消息"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM messages 
                WHERE session_id = %s AND sequence_number = %s
            """, (session_id, sequence_number))
            
            result = cursor.fetchone()
            if result:
                return self._message_to_dict(result)
            return None
    
    def get_conversation_thread(self, session_id: str, start_sequence: int, 
                               end_sequence: int) -> List[Dict[str, Any]]:
        """获取对话线程"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM messages 
                WHERE session_id = %s 
                  AND sequence_number >= %s 
                  AND sequence_number <= %s
                ORDER BY sequence_number ASC
            """, (session_id, start_sequence, end_sequence))
            
            results = cursor.fetchall()
            return [self._message_to_dict(row) for row in results]
    
    def _get_working_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取工作会话缓存"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM working_sessions WHERE session_id = %s
            """, (session_id,))
            return cursor.fetchone()
    
    def _is_working_session_valid(self, working_session: Dict[str, Any]) -> bool:
        """检查工作会话是否有效"""
        if not working_session:
            return False
        
        # 检查是否过期
        if working_session['expires_at']:
            expires_at = working_session['expires_at']
            if datetime.now() > expires_at:
                return False
        
        # 检查是否在合理时间内构建
        built_at = working_session['built_at']
        if datetime.now() - built_at > timedelta(hours=1):
            return False
        
        return True
    
    def _build_context_from_working_session(self, working_session: Dict[str, Any], 
                                           max_tokens: int) -> Dict[str, Any]:
        """从工作会话构建上下文"""
        context = {
            'active_messages': json.loads(working_session['active_messages']) if working_session['active_messages'] else [],
            'layer_1_recent': working_session['layer_1_recent'],
            'layer_2_compressed': working_session['layer_2_compressed'],
            'layer_3_summary': working_session['layer_3_summary'],
            'current_compression_version_id': working_session['current_compression_version_id'],
            'source': 'cache',
            'max_tokens': max_tokens
        }
        
        # 根据token限制裁剪上下文
        return self._trim_context_by_tokens(context, max_tokens)
    
    def _rebuild_session_context(self, session_id: str, max_tokens: int) -> Dict[str, Any]:
        """重新构建会话上下文"""
        # 获取最近的消息
        recent_messages = self.get_active_messages(session_id, limit=20)
        
        # 获取最新的压缩版本
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM compression_versions 
                WHERE session_id = %s AND status = 'active'
                ORDER BY version_number DESC 
                LIMIT 1
            """, (session_id,))
            
            latest_compression = cursor.fetchone()
        
        # 构建上下文
        context = {
            'active_messages': recent_messages,
            'layer_2_compressed': latest_compression['compressed_content'] if latest_compression else None,
            'layer_3_summary': None,  # 可以根据需要添加长期摘要
            'current_compression_version_id': latest_compression['version_id'] if latest_compression else None,
            'source': 'rebuild',
            'max_tokens': max_tokens
        }
        
        # 更新工作会话缓存
        self._update_working_session(session_id, context)
        
        return self._trim_context_by_tokens(context, max_tokens)
    
    def _update_working_session(self, session_id: str, context: Dict[str, Any]):
        """更新工作会话缓存"""
        with self.db.get_cursor() as cursor:
            # 删除旧的缓存
            cursor.execute("DELETE FROM working_sessions WHERE session_id = %s", (session_id,))
            
            # 插入新的缓存
            cursor.execute("""
                INSERT INTO working_sessions 
                (session_id, active_messages, layer_2_compressed, current_compression_version_id, 
                 built_at, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                active_messages = VALUES(active_messages),
                layer_2_compressed = VALUES(layer_2_compressed),
                current_compression_version_id = VALUES(current_compression_version_id),
                built_at = VALUES(built_at),
                expires_at = VALUES(expires_at)
            """, (
                session_id,
                json.dumps(context['active_messages']),
                context['layer_2_compressed'],
                context['current_compression_version_id'],
                datetime.now(),
                datetime.now() + timedelta(hours=2)  # 2小时后过期
            ))
    
    def _trim_context_by_tokens(self, context: Dict[str, Any], max_tokens: int) -> Dict[str, Any]:
        """根据token限制裁剪上下文"""
        # 简单实现：可以添加更复杂的token计算逻辑
        estimated_tokens = 0
        
        # 裁剪活跃消息
        trimmed_messages = []
        for msg in context.get('active_messages', []):
            msg_tokens = len(msg.get('content', '').split())  # 简单估算
            if estimated_tokens + msg_tokens > max_tokens:
                break
            trimmed_messages.append(msg)
            estimated_tokens += msg_tokens
        
        context['active_messages'] = trimmed_messages
        context['estimated_tokens'] = estimated_tokens
        
        return context
    
    def _get_layer_1_recent(self, session_id: str) -> str:
        """获取第一层：最近完整消息"""
        messages = self.get_active_messages(session_id, limit=5)
        return json.dumps([{'role': msg['role'], 'content': msg['content']} for msg in messages], ensure_ascii=False)
    
    def _get_layer_2_compressed(self, session_id: str) -> str:
        """获取第二层：压缩后的近期会话"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT compressed_content FROM compression_versions 
                WHERE session_id = %s AND status = 'active'
                ORDER BY version_number DESC 
                LIMIT 1
            """, (session_id,))
            
            result = cursor.fetchone()
            return result['compressed_content'] if result else ""
    
    def _get_layer_3_summary(self, session_id: str) -> str:
        """获取第三层：长期摘要"""
        # 可以实现更复杂的摘要逻辑
        return ""
    
    def _count_messages(self, session_id: str) -> int:
        """统计消息数量"""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM messages WHERE session_id = %s", (session_id,))
            result = cursor.fetchone()
            return result['count']
    
    def _count_compression_versions(self, session_id: str) -> int:
        """统计压缩版本数量"""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM compression_versions WHERE session_id = %s", (session_id,))
            result = cursor.fetchone()
            return result['count']
    
    def _message_to_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """将消息行转换为字典"""
        return {
            'message_id': row['message_id'],
            'session_id': row['session_id'],
            'role': row['role'],
            'content': row['content'],
            'content_type': row['content_type'],
            'token_count': row['token_count'],
            'metadata': json.loads(row['metadata']) if row['metadata'] else None,
            'sequence_number': row['sequence_number'],
            'is_compressed': row['is_compressed'],
            'compression_version': row['compression_version'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None
        }
    
    def _session_to_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """将会话行转换为字典"""
        return {
            'session_id': row['session_id'],
            'user_id': row['user_id'],
            'agent_id': row['agent_id'],
            'status': row['status'],
            'title': row['title'],
            'context_data': json.loads(row['context_data']) if row['context_data'] else None,
            'total_messages': row['total_messages'],
            'total_tokens': row['total_tokens'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
            'last_message_at': row['last_message_at'].isoformat() if row['last_message_at'] else None
        }