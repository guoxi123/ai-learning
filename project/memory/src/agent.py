"""
Agent 主类 - 集成会话存储、查询和压缩功能的完整系统
"""
from typing import Dict, Any, List, Optional
from src.models import (
    Session, Message, CompressionConfig, CompressionVersion,
    CompressionStrategy, TriggerType, MessageRole, SessionStatus
)
from src.session_storage import SessionStorage
from src.session_query import SessionQuery
from src.session_compressor import SessionCompressor

class ChatAgent:
    """聊天Agent主类，集成完整的会话管理功能"""
    
    def __init__(self, agent_id: str, user_id: str):
        self.agent_id = agent_id
        self.user_id = user_id
        
        # 初始化各个组件
        self.storage = SessionStorage()
        self.query = SessionQuery()
        self.compressor = SessionCompressor()
        
        # 当前活动会话
        self.current_session: Optional[Session] = None
    
    def create_session(self, title: Optional[str] = None, 
                      context_data: Optional[Dict[str, Any]] = None) -> Session:
        """创建新会话"""
        session = self.storage.create_session(
            user_id=self.user_id,
            agent_id=self.agent_id,
            title=title,
            context_data=context_data
        )
        
        # 创建默认压缩配置
        self._create_default_compression_config(session.session_id)
        
        self.current_session = session
        return session
    
    def load_session(self, session_id: str) -> Optional[Session]:
        """加载现有会话"""
        session = self.storage.get_session(session_id)
        if session and session.user_id == self.user_id:
            self.current_session = session
            return session
        return None
    
    def send_message(self, content: str, session_id: Optional[str] = None) -> Message:
        """发送消息并处理响应"""
        # 确定使用的会话
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            # 自动创建新会话
            session = self.create_session(title="新对话")
            target_session_id = session.session_id
        
        # 保存用户消息
        user_message = self.storage.add_message(
            session_id=target_session_id,
            role=MessageRole.USER,
            content=content,
            token_count=len(content.split())  # 简单估算
        )
        
        # 获取会话上下文
        context = self.query.get_session_context(target_session_id, max_tokens=4000)
        
        # 生成助手回复（这里应该调用实际的LLM API）
        assistant_response = self._generate_assistant_response(content, context)
        
        # 保存助手消息
        assistant_message = self.storage.add_message(
            session_id=target_session_id,
            role=MessageRole.ASSISTANT,
            content=assistant_response,
            token_count=len(assistant_response.split()),  # 简单估算
            reply_to_message_id=user_message.message_id
        )
        
        # 检查是否需要压缩
        compression_config = self.compressor.check_compression_needed(target_session_id)
        if compression_config:
            try:
                compressed_version = self.compressor.compress_session(target_session_id, compression_config)
                print(f"会话已自动压缩，版本 {compressed_version.version_number}，压缩比: {compressed_version.compression_ratio:.2%}")
            except Exception as e:
                print(f"压缩失败: {e}")
        
        return assistant_message
    
    def get_context(self, session_id: Optional[str] = None, 
                   max_tokens: int = 4000) -> Dict[str, Any]:
        """获取会话上下文"""
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            return {
                'error': 'No active session',
                'active_messages': [],
                'compressed_content': None
            }
        
        return self.query.get_session_context(target_session_id, max_tokens)
    
    def get_hierarchical_context(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """获取分层上下文视图"""
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            return {
                'error': 'No active session',
                'layers': {}
            }
        
        return self.query.get_hierarchical_context(target_session_id)
    
    def get_compression_traceability(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取压缩可追溯性信息"""
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            return []
        
        return self.query.get_compression_traceability(target_session_id)
    
    def manual_compress(self, session_id: Optional[str] = None, 
                       strategy: CompressionStrategy = CompressionStrategy.SUMMARY) -> CompressionVersion:
        """手动触发压缩"""
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            raise ValueError("No active session")
        
        # 创建临时配置用于手动压缩
        config = self.compressor.create_compression_config(
            session_id=target_session_id,
            strategy=strategy,
            trigger_type=TriggerType.MANUAL,
            trigger_threshold=0  # 手动触发不需要阈值
        )
        
        return self.compressor.compress_session(target_session_id, config)
    
    def compare_compression_versions(self, version1_id: int, version2_id: int, 
                                    session_id: Optional[str] = None) -> Dict[str, Any]:
        """对比压缩版本"""
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            raise ValueError("No active session")
        
        return self.compressor.compare_versions(target_session_id, version1_id, version2_id)
    
    def search_sessions(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """搜索用户的会话"""
        return self.query.search_sessions(self.user_id, status=status, agent_id=self.agent_id)
    
    def get_session_messages(self, session_id: Optional[str] = None, 
                           limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取会话消息"""
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            return []
        
        messages = self.storage.get_messages(target_session_id, limit=limit)
        return [msg.to_dict() for msg in messages]
    
    def end_session(self, session_id: Optional[str] = None) -> bool:
        """结束会话"""
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            return False
        
        success = self.storage.update_session_status(target_session_id, SessionStatus.COMPLETED)
        
        if success and self.current_session and self.current_session.session_id == target_session_id:
            self.current_session = None
        
        return success
    
    def delete_session(self, session_id: Optional[str] = None) -> bool:
        """删除会话"""
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            return False
        
        success = self.storage.delete_session(target_session_id)
        
        if success and self.current_session and self.current_session.session_id == target_session_id:
            self.current_session = None
        
        return success
    
    def configure_compression(self, session_id: Optional[str] = None,
                            strategy: CompressionStrategy = CompressionStrategy.SUMMARY,
                            trigger_type: TriggerType = TriggerType.MESSAGE_COUNT,
                            trigger_threshold: int = 20,
                            **kwargs) -> CompressionConfig:
        """配置压缩策略"""
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            # 如果没有活动会话，创建一个新会话
            session = self.create_session()
            target_session_id = session.session_id
        
        return self.compressor.create_compression_config(
            session_id=target_session_id,
            strategy=strategy,
            trigger_type=trigger_type,
            trigger_threshold=trigger_threshold,
            **kwargs
        )
    
    def get_statistics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """获取会话统计信息"""
        target_session_id = session_id or (self.current_session.session_id if self.current_session else None)
        
        if not target_session_id:
            return {
                'error': 'No active session',
                'total_messages': 0,
                'total_tokens': 0,
                'compression_versions': 0
            }
        
        session = self.storage.get_session(target_session_id)
        compression_versions = self.compressor.get_compression_versions(target_session_id)
        
        # 获取压缩统计
        total_original_tokens = sum(v.original_tokens for v in compression_versions)
        total_compressed_tokens = sum(v.compressed_tokens for v in compression_versions)
        overall_compression_ratio = total_compressed_tokens / total_original_tokens if total_original_tokens > 0 else 0
        
        return {
            'session_id': target_session_id,
            'status': session.status.value if session else 'unknown',
            'total_messages': session.total_messages if session else 0,
            'total_tokens': session.total_tokens if session else 0,
            'compression_versions': len(compression_versions),
            'total_original_tokens': total_original_tokens,
            'total_compressed_tokens': total_compressed_tokens,
            'overall_compression_ratio': overall_compression_ratio,
            'average_quality_score': sum(v.quality_score or 0 for v in compression_versions) / len(compression_versions) if compression_versions else 0,
            'latest_compression': compression_versions[-1].to_dict() if compression_versions else None
        }
    
    def get_message_traceability(self, message_id: int) -> List[Dict[str, Any]]:
        """获取消息的完整压缩追溯链"""
        return self.query.get_message_versions(message_id)
    
    def _create_default_compression_config(self, session_id: str):
        """创建默认压缩配置"""
        self.compressor.create_compression_config(
            session_id=session_id,
            strategy=CompressionStrategy.SUMMARY,
            trigger_type=TriggerType.MESSAGE_COUNT,
            trigger_threshold=20,
            target_compression_ratio=0.3,
            max_summary_tokens=500,
            preserve_last_n_messages=4
        )
    
    def _generate_assistant_response(self, user_message: str, 
                                   context: Dict[str, Any]) -> str:
        """生成助手回复（模拟实现）"""
        # 在实际应用中，这里应该调用LLM API
        # 例如：OpenAI GPT、Claude、或其他模型
        
        active_messages = context.get('active_messages', [])
        compressed_content = context.get('layer_2_compressed', '')
        
        # 构建提示词
        prompt_parts = []
        
        if compressed_content:
            prompt_parts.append(f"历史对话摘要：{compressed_content}")
        
        if active_messages:
            recent_conversation = "\n".join([
                f"{msg['role']}: {msg['content']}" 
                for msg in active_messages[-4:]  # 只使用最近4条消息
            ])
            prompt_parts.append(f"最近对话：\n{recent_conversation}")
        
        prompt_parts.append(f"用户最新消息：{user_message}")
        prompt_parts.append("请根据上下文生成合适的回复。")
        
        full_prompt = "\n\n".join(prompt_parts)
        
        # 模拟LLM响应
        # 在实际应用中，这里应该是：
        # response = openai.ChatCompletion.create(...).choices[0].message.content
        
        if "你好" in user_message or "hello" in user_message.lower():
            return "你好！很高兴为您服务。有什么我可以帮助您的吗？"
        elif "帮助" in user_message or "help" in user_message.lower():
            return "我可以帮助您回答问题、提供信息、进行对话等。请告诉我您需要什么帮助？"
        elif "再见" in user_message or "拜拜" in user_message:
            return "再见！祝您有美好的一天。"
        else:
            return f"我理解您说的是：{user_message}。让我来帮您分析一下这个问题..."

class AgentManager:
    """Agent管理器，用于管理多个用户和Agent的会话"""
    
    def __init__(self):
        self.active_agents: Dict[str, ChatAgent] = {}  # key: "user_id:agent_id"
    
    def get_agent(self, user_id: str, agent_id: str) -> ChatAgent:
        """获取或创建Agent实例"""
        agent_key = f"{user_id}:{agent_id}"
        
        if agent_key not in self.active_agents:
            self.active_agents[agent_key] = ChatAgent(agent_id, user_id)
        
        return self.active_agents[agent_key]
    
    def remove_agent(self, user_id: str, agent_id: str):
        """移除Agent实例"""
        agent_key = f"{user_id}:{agent_id}"
        if agent_key in self.active_agents:
            del self.active_agents[agent_key]
    
    def get_active_agents_count(self) -> int:
        """获取活动Agent数量"""
        return len(self.active_agents)