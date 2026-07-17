-- ============================================
-- 1. 会话主表
-- ============================================
CREATE TABLE sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    agent_id VARCHAR(64) NOT NULL,
    
    -- 会话状态
    status ENUM('active', 'paused', 'completed', 'expired') DEFAULT 'active',
    
    -- 会话元数据
    title VARCHAR(255),
    context_data JSON COMMENT '会话上下文，如用户偏好、环境变量',
    
    -- 会话统计
    total_messages INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    
    INDEX idx_user_agent (user_id, agent_id),
    INDEX idx_status_expires (status, expires_at),
    INDEX idx_last_message (last_message_at)
) COMMENT='会话主表，记录会话基本信息和状态';

-- ============================================
-- 2. 原始消息表（Source of Truth）
-- ============================================
CREATE TABLE messages (
    message_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    
    -- 消息基础信息
    role ENUM('user', 'assistant', 'system', 'tool', 'function') NOT NULL,
    content TEXT NOT NULL,
    content_type VARCHAR(50) DEFAULT 'text' COMMENT 'text, image_url, tool_call等',
    
    -- 消息元数据
    token_count INT DEFAULT 0,
    metadata JSON COMMENT '额外信息：工具调用、引用来源、思考过程等',
    
    -- 消息序列号，保证顺序
    sequence_number INT NOT NULL,
    
    -- 消息状态
    is_compressed BOOLEAN DEFAULT FALSE COMMENT '是否已被压缩处理',
    compression_version INT DEFAULT NULL COMMENT '被哪个压缩版本处理',
    
    -- 关联信息
    parent_message_id BIGINT NULL COMMENT '关联的上一条消息（用于树形对话结构）',
    reply_to_message_id BIGINT NULL COMMENT '直接回复的消息ID',
    
    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    PRIMARY KEY (message_id),
    UNIQUE KEY uk_session_seq (session_id, sequence_number),
    INDEX idx_session_time (session_id, created_at),
    INDEX idx_compression (session_id, is_compressed, compression_version),
    INDEX idx_parent (parent_message_id),
    
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
) COMMENT='原始消息表，存储所有完整的消息记录';

-- ============================================
-- 3. 压缩配置表
-- ============================================
CREATE TABLE compression_configs (
    config_id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    
    -- 压缩策略
    strategy ENUM('summary', 'key_points', 'hierarchical', 'token_window', 'custom') NOT NULL,
    
    -- 触发条件
    trigger_type ENUM('message_count', 'token_count', 'time_interval', 'manual') NOT NULL,
    trigger_threshold INT NOT NULL COMMENT '触发阈值',
    
    -- 压缩参数
    target_compression_ratio DECIMAL(3,2) COMMENT '目标压缩比，如0.3表示压缩到30%',
    max_summary_tokens INT DEFAULT 500,
    preserve_last_n_messages INT DEFAULT 4 COMMENT '保留最近N条不压缩',
    
    -- 模型配置
    compression_model VARCHAR(100) DEFAULT 'gpt-4',
    compression_prompt_template TEXT,
    
    -- 状态
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
) COMMENT='压缩配置表，定义压缩策略和参数';

-- ============================================
-- 4. 压缩版本表（管理压缩批次）
-- ============================================
CREATE TABLE compression_versions (
    version_id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    config_id INT NOT NULL,
    
    -- 版本信息
    version_number INT NOT NULL,
    version_name VARCHAR(100),
    
    -- 压缩范围
    start_sequence_number INT NOT NULL COMMENT '压缩起始消息序号',
    end_sequence_number INT NOT NULL COMMENT '压缩结束消息序号',
    compressed_message_count INT NOT NULL COMMENT '被压缩的消息数量',
    
    -- 压缩结果
    compressed_content TEXT NOT NULL COMMENT '压缩后的内容',
    compression_format ENUM('text', 'structured_json', 'vector_embedding') DEFAULT 'text',
    
    -- 压缩元数据
    original_tokens INT NOT NULL COMMENT '原始总token数',
    compressed_tokens INT NOT NULL COMMENT '压缩后token数',
    compression_ratio DECIMAL(5,4) COMMENT '压缩比',
    compression_time_ms INT COMMENT '压缩耗时(毫秒)',
    
    -- 质量评估
    quality_score DECIMAL(3,2) COMMENT '压缩质量评分',
    quality_metrics JSON COMMENT '详细质量指标',
    
    -- 向量存储（用于相似度检索）
    embedding_vector VECTOR(1536) COMMENT '压缩内容的向量表示',
    
    -- 状态和时间
    status ENUM('draft', 'active', 'archived', 'failed') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    validated_at TIMESTAMP NULL,
    
    -- 索引
    UNIQUE KEY uk_session_version (session_id, version_number),
    INDEX idx_session_active (session_id, status),
    INDEX idx_sequence_range (session_id, start_sequence_number, end_sequence_number),
    INDEX idx_embedding (embedding_vector) USING IVFFLAT,
    
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (config_id) REFERENCES compression_configs(config_id)
) COMMENT='压缩版本表，记录每次压缩操作的结果';

-- ============================================
-- 5. 消息压缩映射表（核心关联表）
-- ============================================
CREATE TABLE message_compression_map (
    map_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- 双向外键关联
    message_id BIGINT NOT NULL,
    version_id INT NOT NULL,
    
    -- 消息在压缩版本中的角色
    message_role_in_compression ENUM('source', 'reference', 'context') DEFAULT 'source',
    
    -- 关联权重（该消息对压缩结果的重要性）
    relevance_score DECIMAL(4,3) DEFAULT 1.000,
    
    -- 映射元数据
    mapped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mapped_by VARCHAR(50) DEFAULT 'system' COMMENT 'system, manual, ai',
    
    -- 唯一约束：一个消息在同一个版本中只能有一条映射
    UNIQUE KEY uk_message_version (message_id, version_id),
    INDEX idx_version_messages (version_id, message_id),
    INDEX idx_message_versions (message_id, version_id),
    
    FOREIGN KEY (message_id) REFERENCES messages(message_id) ON DELETE CASCADE,
    FOREIGN KEY (version_id) REFERENCES compression_versions(version_id) ON DELETE CASCADE
) COMMENT='消息压缩映射表，建立消息与压缩版本的多对多关系';

-- ============================================
-- 6. 工作会话表（热数据缓存）
-- ============================================
CREATE TABLE working_sessions (
    working_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    
    -- 当前活跃上下文
    active_messages JSON COMMENT '最近N条未压缩的消息',
    
    -- 分层上下文
    layer_1_recent TEXT COMMENT '第1层：最近完整消息',
    layer_2_compressed TEXT COMMENT '第2层：压缩后的近期会话',
    layer_3_summary TEXT COMMENT '第3层：长期摘要',
    
    -- 当前使用的压缩版本
    current_compression_version_id INT,
    
    -- 上下文构建配置
    max_active_messages INT DEFAULT 10,
    max_context_tokens INT DEFAULT 4000,
    
    -- 时间戳
    built_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    
    UNIQUE KEY uk_session (session_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (current_compression_version_id) REFERENCES compression_versions(version_id)
) COMMENT='工作会话表，缓存当前查询所需的热数据';