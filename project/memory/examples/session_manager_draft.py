class AgentSessionManager:
    def __init__(self):
        self.db = DatabaseConnection()
        self.llm = LLMClient()
    
    def handle_message(self, session_id, user_message):
        """处理用户消息的完整流程"""
        
        # 1. 存储用户消息
        user_msg_id = self._store_message(
            session_id, 'user', user_message
        )
        
        # 2. 构建上下文（混合压缩和原始消息）
        context = self._build_context(session_id)
        
        # 3. 调用LLM生成回复
        assistant_response = self.llm.generate(context + [{
            'role': 'user',
            'content': user_message
        }])
        
        # 4. 存储助手回复
        assistant_msg_id = self._store_message(
            session_id, 'assistant', assistant_response
        )
        
        # 5. 检查是否需要压缩
        if self._should_compress(session_id):
            self._trigger_compression(session_id)
        
        return assistant_response
    
    def _build_context(self, session_id):
        """构建分层上下文"""
        
        # 从数据库获取分层数据
        working_session = self.db.query("""
            SELECT * FROM working_sessions 
            WHERE session_id = %s
        """, (session_id,)).fetchone()
        
        context = []
        
        # 第3层：长期记忆（最早）
        if working_session['layer_3_summary']:
            context.append({
                'role': 'system',
                'content': f"[长期上下文] {working_session['layer_3_summary']}"
            })
        
        # 第2层：压缩的短期记忆
        if working_session['layer_2_compressed']:
            context.append({
                'role': 'system',
                'content': f"[近期摘要] {working_session['layer_2_compressed']}"
            })
        
        # 第1层：最近未压缩消息
        recent_messages = json.loads(working_session['active_messages'])
        context.extend(recent_messages)
        
        return context
    
    def _should_compress(self, session_id):
        """判断是否需要压缩"""
        config = self.db.query("""
            SELECT * FROM compression_configs 
            WHERE session_id = %s AND is_active = TRUE
        """, (session_id,)).fetchone()
        
        if not config:
            return False
        
        # 检查触发条件
        if config['trigger_type'] == 'message_count':
            unarchived_count = self.db.query("""
                SELECT COUNT(*) as cnt 
                FROM messages 
                WHERE session_id = %s AND is_compressed = FALSE
            """, (session_id,)).fetchone()['cnt']
            
            return unarchived_count >= config['trigger_threshold']
        
        return False
    
    def _trigger_compression(self, session_id):
        """触发压缩流程"""
        
        # 1. 获取需要压缩的消息范围
        config = self.db.query("""
            SELECT preserve_last_n_messages 
            FROM compression_configs 
            WHERE session_id = %s AND is_active = TRUE
        """, (session_id,)).fetchone()
        
        preserve_count = config['preserve_last_n_messages']
        
        # 2. 确定压缩范围
        messages_to_compress = self.db.query("""
            SELECT MIN(sequence_number) as start_seq,
                   MAX(sequence_number) as end_seq
            FROM messages
            WHERE session_id = %s 
            AND is_compressed = FALSE
            ORDER BY sequence_number
            LIMIT (SELECT COUNT(*) - %s FROM messages 
                   WHERE session_id = %s AND is_compressed = FALSE)
        """, (session_id, preserve_count, session_id)).fetchone()
        
        if messages_to_compress and messages_to_compress['start_seq']:
            # 3. 执行压缩
            compressor = SessionCompressor(self.db)
            version_id = compressor.create_compression(
                session_id,
                messages_to_compress['start_seq'],
                messages_to_compress['end_seq']
            )
            
            # 4. 更新工作会话
            self._update_working_session_after_compression(
                session_id, version_id
            )