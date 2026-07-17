"""
Agent 系统测试和使用示例
"""
import json
from src.agent import ChatAgent, AgentManager
from src.models import CompressionStrategy, TriggerType

def example_basic_usage():
    """基本使用示例"""
    print("=== 基本使用示例 ===")
    
    # 创建Agent实例
    agent = ChatAgent(agent_id="assistant_001", user_id="user_123")
    
    # 创建新会话
    session = agent.create_session(title="技术咨询会话")
    print(f"创建会话: {session.session_id}")
    
    # 发送消息
    response1 = agent.send_message("你好，我想了解一下机器学习的基本概念")
    print(f"助手回复: {response1.content}")
    
    response2 = agent.send_message("什么是监督学习？")
    print(f"助手回复: {response2.content}")
    
    # 获取上下文
    context = agent.get_context()
    print(f"当前上下文: {context['source']}, 活跃消息数: {len(context['active_messages'])}")
    
    # 结束会话
    agent.end_session()
    print("会话已结束")

def example_compression_usage():
    """压缩功能示例"""
    print("\n=== 压缩功能示例 ===")
    
    # 创建Agent实例
    agent = ChatAgent(agent_id="assistant_001", user_id="user_456")
    
    # 创建会话并配置压缩
    session = agent.create_session(title="长对话测试")
    
    # 配置压缩策略
    agent.configure_compression(
        strategy=CompressionStrategy.SUMMARY,
        trigger_type=TriggerType.MESSAGE_COUNT,
        trigger_threshold=5,  # 5条消息后触发压缩
        target_compression_ratio=0.3,
        max_summary_tokens=300
    )
    
    # 发送多条消息触发压缩
    messages = [
        "我想学习Python编程",
        "Python有哪些基本数据类型？",
        "如何定义一个函数？",
        "什么是列表推导式？",
        "Python中的装饰器是什么？",
        "如何处理文件读写操作？"
    ]
    
    for i, msg in enumerate(messages, 1):
        response = agent.send_message(msg)
        print(f"{i}. 用户: {msg}")
        print(f"   助手: {response.content[:50]}...")
    
    # 手动触发压缩
    compressed_version = agent.manual_compress(strategy=CompressionStrategy.KEY_POINTS)
    print(f"\n手动压缩完成，版本: {compressed_version.version_number}")
    print(f"压缩内容: {compressed_version.compressed_content}")
    
    # 获取统计信息
    stats = agent.get_statistics()
    print(f"\n会话统计:")
    print(f"总消息数: {stats['total_messages']}")
    print(f"总token数: {stats['total_tokens']}")
    print(f"压缩版本数: {stats['compression_versions']}")
    print(f"整体压缩比: {stats['overall_compression_ratio']:.2%}")

def example_query_usage():
    """查询功能示例"""
    print("\n=== 查询功能示例 ===")
    
    agent = ChatAgent(agent_id="assistant_001", user_id="user_789")
    session = agent.create_session(title="查询测试会话")
    
    # 添加一些测试消息
    test_messages = [
        "我想了解数据库设计的基本原则",
        "什么是范式？",
        "第一范式和第二范式有什么区别？",
        "如何进行数据库性能优化？"
    ]
    
    for msg in test_messages:
        agent.send_message(msg)
    
    # 获取分层上下文
    hierarchical_context = agent.get_hierarchical_context()
    print("分层上下文:")
    print(f"第1层(最近消息): {hierarchical_context['layer_1_recent'][:100]}...")
    print(f"第2层(压缩内容): {hierarchical_context['layer_2_compressed'][:100] if hierarchical_context['layer_2_compressed'] else '无'}...")
    
    # 搜索会话
    user_sessions = agent.search_sessions()
    print(f"\n用户会话列表:")
    for sess in user_sessions:
        print(f"- {sess['title']} (ID: {sess['session_id']}, 状态: {sess['status']})")

def example_traceability_usage():
    """可追溯性示例"""
    print("\n=== 可追溯性示例 ===")
    
    agent = ChatAgent(agent_id="assistant_001", user_id="user_999")
    session = agent.create_session(title="可追溯性测试")
    
    # 发送消息
    agent.send_message("什么是深度学习？")
    agent.send_message("深度学习和机器学习有什么关系？")
    
    # 手动压缩
    agent.manual_compress(strategy=CompressionStrategy.SUMMARY)
    
    # 再发送消息
    agent.send_message("什么是神经网络？")
    agent.send_message("如何训练一个神经网络？")
    
    # 再次压缩
    agent.manual_compress(strategy=CompressionStrategy.KEY_POINTS)
    
    # 获取压缩可追溯性
    traceability = agent.get_compression_traceability()
    print(f"压缩历史 (共{len(traceability)}个版本):")
    
    for version_info in traceability:
        print(f"\n版本 {version_info['version_number']}:")
        print(f"  策略: {version_info['strategy']}")
        print(f"  压缩范围: {version_info['start_sequence']} - {version_info['end_sequence']}")
        print(f"  压缩消息数: {version_info['compressed_count']}")
        print(f"  压缩比: {version_info['compression_ratio']:.2%}")
        print(f"  包含消息:")
        for msg in version_info['messages'][:3]:  # 只显示前3条
            print(f"    - 序列{msg['sequence_number']}: {msg['role']} (相关度: {msg['relevance_score']:.2f})")

def example_agent_manager_usage():
    """Agent管理器示例"""
    print("\n=== Agent管理器示例 ===")
    
    manager = AgentManager()
    
    # 为多个用户获取Agent
    agent1 = manager.get_agent("user_001", "assistant_001")
    agent2 = manager.get_agent("user_002", "assistant_001")
    agent3 = manager.get_agent("user_001", "assistant_002")  # 同一用户，不同Agent
    
    # 各自创建会话
    session1 = agent1.create_session(title="用户1的会话")
    session2 = agent2.create_session(title="用户2的会话")
    session3 = agent3.create_session(title="用户1的另一个会话")
    
    print(f"活动Agent数量: {manager.get_active_agents_count()}")
    
    # 发送消息
    agent1.send_message("你好，我是用户1")
    agent2.send_message("你好，我是用户2")
    agent3.send_message("你好，我是用户1，在使用另一个助手")
    
    # 搜索各自用户的会话
    user1_sessions = agent1.search_sessions()
    print(f"用户1的会话数: {len(user1_sessions)}")
    
    user2_sessions = agent2.search_sessions()
    print(f"用户2的会话数: {len(user2_sessions)}")

def example_advanced_features():
    """高级功能示例"""
    print("\n=== 高级功能示例 ===")
    
    agent = ChatAgent(agent_id="assistant_001", user_id="user_advanced")
    session = agent.create_session(title="高级功能测试", context_data={"theme": "技术讨论"})
    
    # 配置多种压缩策略对比
    agent.configure_compression(
        strategy=CompressionStrategy.SUMMARY,
        trigger_type=TriggerType.MESSAGE_COUNT,
        trigger_threshold=8,
        target_compression_ratio=0.25
    )
    
    # 模拟长对话
    long_conversation = [
        "我想了解人工智能的发展历史",
        "AI的起源是什么时候？",
        "图灵测试是什么？",
        "专家系统是如何工作的？",
        "神经网络的发展历程？",
        "深度学习的突破是什么？",
        "GPT模型的特点是什么？",
        "大语言模型的局限性？",
        "AI的未来发展方向？",
        "如何避免AI的安全风险？"
    ]
    
    for msg in long_conversation:
        agent.send_message(msg)
    
    # 手动创建不同策略的压缩版本进行对比
    version1 = agent.manual_compress(strategy=CompressionStrategy.SUMMARY)
    print(f"\n摘要压缩版本 {version1.version_number}:")
    print(f"内容: {version1.compressed_content}")
    print(f"压缩比: {version1.compression_ratio:.2%}")
    
    # 重新加载会话以创建新压缩
    agent.load_session(session.session_id)
    version2 = agent.manual_compress(strategy=CompressionStrategy.KEY_POINTS)
    print(f"\n关键点压缩版本 {version2.version_number}:")
    print(f"内容: {version2.compressed_content}")
    print(f"压缩比: {version2.compression_ratio:.2%}")
    
    # 对比两个版本
    comparison = agent.compare_compression_versions(version1.version_id, version2.version_id)
    print(f"\n版本对比:")
    print(f"压缩比差异: {comparison['comparison']['ratio_improvement']:.2%}")
    print(f"质量分数差异: {comparison['comparison']['quality_improvement']:.2f}")
    
    # 获取详细统计
    stats = agent.get_statistics()
    print(f"\n详细统计:")
    print(json.dumps(stats, indent=2, ensure_ascii=False, default=str))

def run_all_examples():
    """运行所有示例"""
    try:
        example_basic_usage()
        example_compression_usage()
        example_query_usage()
        example_traceability_usage()
        example_agent_manager_usage()
        example_advanced_features()
        
        print("\n=== 所有示例运行完成 ===")
        
    except Exception as e:
        print(f"示例运行出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Agent系统测试和使用示例")
    print("=" * 50)
    
    # 检查数据库连接
    try:
        from database import db_manager
        print("数据库连接正常")
        
        # 运行示例
        run_all_examples()
        
    except Exception as e:
        print(f"数据库连接失败: {e}")
        print("请确保数据库已正确配置并运行")
        print("\n提示：需要设置以下环境变量:")
        print("- DB_HOST: 数据库主机地址")
        print("- DB_USER: 数据库用户名")
        print("- DB_PASSWORD: 数据库密码")
        print("- DB_NAME: 数据库名称")
        print("- DB_PORT: 数据库端口")