"""
会话压缩模块 - 实现多种压缩策略和版本管理
"""
import json
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.models import (
    CompressionConfig, CompressionVersion, MessageCompressionMap,
    CompressionStrategy, TriggerType, CompressionFormat, VersionStatus,
    MessageRoleInCompression, Message
)
from src.database import db_manager
from src.session_storage import SessionStorage

class SessionCompressor:
    """会话压缩管理器"""
    
    def __init__(self):
        self.db = db_manager
        self.storage = SessionStorage()
    
    def create_compression_config(self, session_id: str, strategy: CompressionStrategy,
                                  trigger_type: TriggerType, trigger_threshold: int,
                                  **kwargs) -> CompressionConfig:
        """创建压缩配置"""
        config = CompressionConfig(
            config_id=None,
            session_id=session_id,
            strategy=strategy,
            trigger_type=trigger_type,
            trigger_threshold=trigger_threshold,
            **kwargs
        )
        
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO compression_configs 
                (session_id, strategy, trigger_type, trigger_threshold, 
                 target_compression_ratio, max_summary_tokens, preserve_last_n_messages,
                 compression_model, compression_prompt_template, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id, strategy.value, trigger_type.value, trigger_threshold,
                config.target_compression_ratio, config.max_summary_tokens,
                config.preserve_last_n_messages, config.compression_model,
                config.compression_prompt_template, config.is_active, datetime.now()
            ))
            
            config.config_id = cursor.lastrowid
        
        return config
    
    def check_compression_needed(self, session_id: str) -> Optional[CompressionConfig]:
        """检查是否需要压缩"""
        with self.db.get_cursor() as cursor:
            # 获取活跃的压缩配置
            cursor.execute("""
                SELECT * FROM compression_configs 
                WHERE session_id = %s AND is_active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
            """, (session_id,))
            
            config_row = cursor.fetchone()
            if not config_row:
                return None
            
            config = self._row_to_compression_config(config_row)
            
            # 根据触发类型检查是否需要压缩
            if config.trigger_type == TriggerType.MESSAGE_COUNT:
                return self._check_message_count_trigger(session_id, config)
            elif config.trigger_type == TriggerType.TOKEN_COUNT:
                return self._check_token_count_trigger(session_id, config)
            elif config.trigger_type == TriggerType.TIME_INTERVAL:
                return self._check_time_interval_trigger(session_id, config)
            
            return None
    
    def compress_session(self, session_id: str, config: Optional[CompressionConfig] = None) -> CompressionVersion:
        """执行会话压缩"""
        if config is None:
            config = self.check_compression_needed(session_id)
            if config is None:
                raise ValueError("No active compression config found")
        
        # 获取需要压缩的消息
        messages_to_compress = self._get_messages_for_compression(session_id, config)
        
        if not messages_to_compress:
            raise ValueError("No messages to compress")
        
        start_time = time.time()
        
        # 根据策略执行压缩
        if config.strategy == CompressionStrategy.SUMMARY:
            compressed_content = self._summary_compression(messages_to_compress, config)
        elif config.strategy == CompressionStrategy.KEY_POINTS:
            compressed_content = self._key_points_compression(messages_to_compress, config)
        elif config.strategy == CompressionStrategy.HIERARCHICAL:
            compressed_content = self._hierarchical_compression(messages_to_compress, config)
        elif config.strategy == CompressionStrategy.TOKEN_WINDOW:
            compressed_content = self._token_window_compression(messages_to_compress, config)
        else:
            compressed_content = self._custom_compression(messages_to_compress, config)
        
        compression_time_ms = int((time.time() - start_time) * 1000)
        
        # 计算压缩统计
        original_tokens = sum(msg.token_count for msg in messages_to_compress)
        compressed_tokens = len(compressed_content.split())  # 简单估算
        compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 0
        
        # 创建压缩版本
        version_number = self._get_next_version_number(session_id)
        version = CompressionVersion(
            version_id=None,
            session_id=session_id,
            config_id=config.config_id,
            version_number=version_number,
            version_name=f"Version {version_number} - {config.strategy.value}",
            start_sequence_number=messages_to_compress[0].sequence_number,
            end_sequence_number=messages_to_compress[-1].sequence_number,
            compressed_message_count=len(messages_to_compress),
            compressed_content=compressed_content,
            compression_format=CompressionFormat.TEXT,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compression_ratio,
            compression_time_ms=compression_time_ms,
            quality_score=self._calculate_quality_score(messages_to_compress, compressed_content),
            status=VersionStatus.ACTIVE,
            created_at=datetime.now()
        )
        
        with self.db.get_cursor() as cursor:
            # 插入压缩版本
            cursor.execute("""
                INSERT INTO compression_versions 
                (session_id, config_id, version_number, version_name, 
                 start_sequence_number, end_sequence_number, compressed_message_count,
                 compressed_content, compression_format, original_tokens, compressed_tokens,
                 compression_ratio, compression_time_ms, quality_score, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id, config.config_id, version_number, version.version_name,
                version.start_sequence_number, version.end_sequence_number, version.compressed_message_count,
                compressed_content, version.compression_format.value, original_tokens, compressed_tokens,
                compression_ratio, compression_time_ms, version.quality_score,
                version.status.value, datetime.now()
            ))
            
            version.version_id = cursor.lastrowid
            
            # 创建消息压缩映射
            message_ids = []
            for msg in messages_to_compress:
                cursor.execute("""
                    INSERT INTO message_compression_map 
                    (message_id, version_id, message_role_in_compression, relevance_score, mapped_at)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    msg.message_id, version.version_id, 
                    MessageRoleInCompression.SOURCE.value,
                    self._calculate_relevance_score(msg), datetime.now()
                ))
                message_ids.append(msg.message_id)
        
        # 标记消息为已压缩
        self.storage.mark_message_compressed(message_ids, version_number)
        
        # 清除工作会话缓存
        self._invalidate_working_session(session_id)
        
        return version
    
    def get_compression_versions(self, session_id: str) -> List[CompressionVersion]:
        """获取会话的所有压缩版本"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM compression_versions 
                WHERE session_id = %s
                ORDER BY version_number ASC
            """, (session_id,))
            
            return [self._row_to_compression_version(row) for row in cursor.fetchall()]
    
    def compare_versions(self, session_id: str, version1_id: int, version2_id: int) -> Dict[str, Any]:
        """对比两个压缩版本"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM compression_versions 
                WHERE version_id IN (%s, %s) AND session_id = %s
            """, (version1_id, version2_id, session_id))
            
            versions = [self._row_to_compression_version(row) for row in cursor.fetchall()]
            
            if len(versions) != 2:
                raise ValueError("Both versions not found")
            
            v1, v2 = versions
            
            return {
                'version_1': {
                    'version_number': v1.version_number,
                    'compression_ratio': v1.compression_ratio,
                    'quality_score': v1.quality_score,
                    'message_count': v1.compressed_message_count,
                    'compression_time_ms': v1.compression_time_ms
                },
                'version_2': {
                    'version_number': v2.version_number,
                    'compression_ratio': v2.compression_ratio,
                    'quality_score': v2.quality_score,
                    'message_count': v2.compressed_message_count,
                    'compression_time_ms': v2.compression_time_ms
                },
                'comparison': {
                    'ratio_improvement': v2.compression_ratio - v1.compression_ratio,
                    'quality_improvement': v2.quality_score - v1.quality_score,
                    'time_difference': v2.compression_time_ms - v1.compression_time_ms
                }
            }
    
    def _check_message_count_trigger(self, session_id: str, config: CompressionConfig) -> Optional[CompressionConfig]:
        """检查消息数量触发条件"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) as count FROM messages 
                WHERE session_id = %s AND is_compressed = FALSE
            """, (session_id,))
            
            count = cursor.fetchone()['count']
            if count >= config.trigger_threshold:
                return config
        
        return None
    
    def _check_token_count_trigger(self, session_id: str, config: CompressionConfig) -> Optional[CompressionConfig]:
        """检查token数量触发条件"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT SUM(token_count) as total_tokens FROM messages 
                WHERE session_id = %s AND is_compressed = FALSE
            """, (session_id,))
            
            result = cursor.fetchone()
            total_tokens = result['total_tokens'] or 0
            
            if total_tokens >= config.trigger_threshold:
                return config
        
        return None
    
    def _check_time_interval_trigger(self, session_id: str, config: CompressionConfig) -> Optional[CompressionConfig]:
        """检查时间间隔触发条件"""
        # 简化实现：检查最近一次压缩时间
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT MAX(created_at) as last_compression 
                FROM compression_versions 
                WHERE session_id = %s
            """, (session_id,))
            
            result = cursor.fetchone()
            last_compression = result['last_compression']
            
            if last_compression and (datetime.now() - last_compression).total_seconds() >= config.trigger_threshold:
                return config
        
        return None
    
    def _get_messages_for_compression(self, session_id: str, config: CompressionConfig) -> List[Message]:
        """获取需要压缩的消息"""
        messages = self.storage.get_uncompressed_messages(session_id)
        
        # 保留最近N条消息不压缩
        if len(messages) > config.preserve_last_n_messages:
            return messages[:-config.preserve_last_n_messages]
        
        return []
    
    def _summary_compression(self, messages: List[Message], config: CompressionConfig) -> str:
        """摘要压缩策略"""
        # 构建对话文本
        conversation = []
        for msg in messages:
            conversation.append(f"{msg.role}: {msg.content}")
        
        conversation_text = "\n".join(conversation)
        
        # 这里应该调用LLM API生成摘要
        # 简化实现：返回前N个字符
        prompt = f"请为以下对话生成一个简洁的摘要，保留关键信息：\n\n{conversation_text}\n\n摘要："
        
        # 模拟LLM响应
        summary = f"对话摘要：包含{len(messages)}条消息，主要涉及用户与助手的交互。"
        
        return summary
    
    def _key_points_compression(self, messages: List[Message], config: CompressionConfig) -> str:
        """关键点压缩策略"""
        key_points = []
        
        for msg in messages:
            # 简化实现：提取每个消息的前几句
            sentences = msg.content.split('。')[:2]
            point = '。'.join(sentences)
            if point:
                key_points.append(f"- {msg.role}: {point}")
        
        return "\n".join(key_points)
    
    def _hierarchical_compression(self, messages: List[Message], config: CompressionConfig) -> str:
        """分层压缩策略"""
        # 按消息类型分组压缩
        user_messages = [msg for msg in messages if msg.role.value == 'user']
        assistant_messages = [msg for msg in messages if msg.role.value == 'assistant']
        
        user_summary = f"用户提出了{len(user_messages)}个问题/请求"
        assistant_summary = f"助手提供了{len(assistant_messages)}次响应"
        
        return f"{user_summary}\n{assistant_summary}"
    
    def _token_window_compression(self, messages: List[Message], config: CompressionConfig) -> str:
        """窗口压缩策略"""
        # 保留token窗口内的消息
        current_tokens = 0
        window_messages = []
        
        for msg in reversed(messages):
            if current_tokens + msg.token_count > config.max_summary_tokens:
                break
            window_messages.insert(0, msg)
            current_tokens += msg.token_count
        
        return "\n".join([f"{msg.role}: {msg.content}" for msg in window_messages])
    
    def _custom_compression(self, messages: List[Message], config: CompressionConfig) -> str:
        """自定义压缩策略"""
        # 使用自定义提示模板
        if config.compression_prompt_template:
            return self._apply_custom_template(messages, config.compression_prompt_template)
        
        return self._summary_compression(messages, config)
    
    def _apply_custom_template(self, messages: List[Message], template: str) -> str:
        """应用自定义模板"""
        conversation = "\n".join([f"{msg.role}: {msg.content}" for msg in messages])
        
        # 简化实现：直接替换占位符
        return template.replace("{conversation}", conversation)
    
    def _calculate_quality_score(self, original_messages: List[Message], compressed_content: str) -> float:
        """计算压缩质量分数"""
        # 简化实现：基于压缩率和内容长度
        original_length = sum(len(msg.content) for msg in original_messages)
        compressed_length = len(compressed_content)
        
        if original_length == 0:
            return 1.0
        
        # 压缩率分数 (0.4) + 内容保留分数 (0.6)
        compression_score = max(0, 1 - (compressed_length / original_length))
        content_score = min(1, compressed_length / 100)  # 假设理想长度为100字符
        
        return (compression_score * 0.4 + content_score * 0.6)
    
    def _calculate_relevance_score(self, message: Message) -> float:
        """计算消息相关性分数"""
        # 简化实现：基于token数量和角色
        base_score = 0.8
        
        if message.role.value == 'user':
            base_score += 0.1  # 用户消息更重要
        
        # 根据token数量调整
        token_factor = min(0.2, message.token_count / 500)
        
        return min(1.0, base_score + token_factor)
    
    def _get_next_version_number(self, session_id: str) -> int:
        """获取下一个版本号"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT MAX(version_number) as max_version 
                FROM compression_versions 
                WHERE session_id = %s
            """, (session_id,))
            
            result = cursor.fetchone()
            return (result['max_version'] + 1) if result['max_version'] else 1
    
    def _invalidate_working_session(self, session_id: str):
        """使工作会话缓存失效"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                DELETE FROM working_sessions WHERE session_id = %s
            """, (session_id,))
    
    def _row_to_compression_config(self, row: Dict[str, Any]) -> CompressionConfig:
        """将数据库行转换为CompressionConfig对象"""
        return CompressionConfig(
            config_id=row['config_id'],
            session_id=row['session_id'],
            strategy=CompressionStrategy(row['strategy']),
            trigger_type=TriggerType(row['trigger_type']),
            trigger_threshold=row['trigger_threshold'],
            target_compression_ratio=row['target_compression_ratio'],
            max_summary_tokens=row['max_summary_tokens'],
            preserve_last_n_messages=row['preserve_last_n_messages'],
            compression_model=row['compression_model'],
            compression_prompt_template=row['compression_prompt_template'],
            is_active=row['is_active'],
            created_at=row['created_at']
        )
    
    def _row_to_compression_version(self, row: Dict[str, Any]) -> CompressionVersion:
        """将数据库行转换为CompressionVersion对象"""
        return CompressionVersion(
            version_id=row['version_id'],
            session_id=row['session_id'],
            config_id=row['config_id'],
            version_number=row['version_number'],
            version_name=row['version_name'],
            start_sequence_number=row['start_sequence_number'],
            end_sequence_number=row['end_sequence_number'],
            compressed_message_count=row['compressed_message_count'],
            compressed_content=row['compressed_content'],
            compression_format=CompressionFormat(row['compression_format']),
            original_tokens=row['original_tokens'],
            compressed_tokens=row['compressed_tokens'],
            compression_ratio=row['compression_ratio'],
            compression_time_ms=row['compression_time_ms'],
            quality_score=row['quality_score'],
            quality_metrics=json.loads(row['quality_metrics']) if row['quality_metrics'] else None,
            embedding_vector=row['embedding_vector'],
            status=VersionStatus(row['status']),
            created_at=row['created_at'],
            validated_at=row['validated_at']
        )