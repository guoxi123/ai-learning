"""
数据模型定义
"""
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

class SessionStatus(str, Enum):
    """会话状态枚举"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    EXPIRED = "expired"

class MessageRole(str, Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    FUNCTION = "function"

class CompressionStrategy(str, Enum):
    """压缩策略枚举"""
    SUMMARY = "summary"
    KEY_POINTS = "key_points"
    HIERARCHICAL = "hierarchical"
    TOKEN_WINDOW = "token_window"
    CUSTOM = "custom"

class TriggerType(str, Enum):
    """触发类型枚举"""
    MESSAGE_COUNT = "message_count"
    TOKEN_COUNT = "token_count"
    TIME_INTERVAL = "time_interval"
    MANUAL = "manual"

class CompressionFormat(str, Enum):
    """压缩格式枚举"""
    TEXT = "text"
    STRUCTURED_JSON = "structured_json"
    VECTOR_EMBEDDING = "vector_embedding"

class VersionStatus(str, Enum):
    """版本状态枚举"""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    FAILED = "failed"

class MessageRoleInCompression(str, Enum):
    """消息在压缩中的角色枚举"""
    SOURCE = "source"
    REFERENCE = "reference"
    CONTEXT = "context"

@dataclass
class Session:
    """会话数据模型"""
    session_id: str
    user_id: str
    agent_id: str
    status: SessionStatus = SessionStatus.ACTIVE
    title: Optional[str] = None
    context_data: Optional[Dict[str, Any]] = None
    total_messages: int = 0
    total_tokens: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        # 转换枚举类型
        data['status'] = self.status.value
        return data

@dataclass
class Message:
    """消息数据模型"""
    message_id: Optional[int]
    session_id: str
    role: MessageRole
    content: str
    content_type: str = "text"
    token_count: int = 0
    metadata: Optional[Dict[str, Any]] = None
    sequence_number: Optional[int] = None
    is_compressed: bool = False
    compression_version: Optional[int] = None
    parent_message_id: Optional[int] = None
    reply_to_message_id: Optional[int] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['role'] = self.role.value
        return data

@dataclass
class CompressionConfig:
    """压缩配置数据模型"""
    config_id: Optional[int]
    session_id: str
    strategy: CompressionStrategy
    trigger_type: TriggerType
    trigger_threshold: int
    target_compression_ratio: Optional[float] = None
    max_summary_tokens: int = 500
    preserve_last_n_messages: int = 4
    compression_model: str = "gpt-4"
    compression_prompt_template: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['strategy'] = self.strategy.value
        data['trigger_type'] = self.trigger_type.value
        return data

@dataclass
class CompressionVersion:
    """压缩版本数据模型"""
    version_id: Optional[int]
    session_id: str
    config_id: int
    version_number: int
    version_name: Optional[str]
    start_sequence_number: int
    end_sequence_number: int
    compressed_message_count: int
    compressed_content: str
    compression_format: CompressionFormat = CompressionFormat.TEXT
    original_tokens: int = 0
    compressed_tokens: int = 0
    compression_ratio: Optional[float] = None
    compression_time_ms: Optional[int] = None
    quality_score: Optional[float] = None
    quality_metrics: Optional[Dict[str, Any]] = None
    embedding_vector: Optional[List[float]] = None
    status: VersionStatus = VersionStatus.ACTIVE
    created_at: Optional[datetime] = None
    validated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['compression_format'] = self.compression_format.value
        data['status'] = self.status.value
        return data

@dataclass
class MessageCompressionMap:
    """消息压缩映射数据模型"""
    map_id: Optional[int]
    message_id: int
    version_id: int
    message_role_in_compression: MessageRoleInCompression = MessageRoleInCompression.SOURCE
    relevance_score: float = 1.0
    mapped_at: Optional[datetime] = None
    mapped_by: str = "system"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['message_role_in_compression'] = self.message_role_in_compression.value
        return data

@dataclass
class WorkingSession:
    """工作会话数据模型（热数据缓存）"""
    working_id: Optional[int]
    session_id: str
    active_messages: Optional[List[Dict[str, Any]]] = None
    layer_1_recent: Optional[str] = None
    layer_2_compressed: Optional[str] = None
    layer_3_summary: Optional[str] = None
    current_compression_version_id: Optional[int] = None
    max_active_messages: int = 10
    max_context_tokens: int = 4000
    built_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)