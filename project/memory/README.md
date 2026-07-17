# 会话压缩 Agent 系统

LLM 长对话的上下文管理实验项目。核心思路：**原始消息永不丢失，压缩只是衍生视图**。
通过「原始表 + 压缩表 + 映射表 + 缓存表」四层结构，实现可追溯、可版本化、分层的上下文压缩。

完整设计思路见 [TECH_DESIGN.md](TECH_DESIGN.md)。

## 目录结构

```
project/memory/
├── src/                       源码包（import 形式：from src.xxx import ...）
│   ├── models.py              数据模型与枚举
│   ├── database.py            数据库连接池（MySQL）
│   ├── session_storage.py     会话 / 消息 CRUD
│   ├── session_query.py       上下文构建、分层查询、可追溯查询
│   ├── session_compressor.py  压缩策略执行、版本管理
│   └── agent.py               ChatAgent / AgentManager（对外统一接口）
├── examples/
│   ├── examples.py            完整使用示例（run_all_examples）
│   └── session_manager_draft.py   早期 AgentSessionManager 设计草图（伪代码，不可运行）
├── db/
│   └── schema.sql             6 张表的 DDL
├── requirements.txt
├── .env.example
├── TECH_DESIGN.md
└── README.md
```

## 模块依赖

```
models.py / database.py                     基础层
        │
 session_storage ─── session_query ─── session_compressor     服务层
        └──────────────── agent ────────────────┘            编排层
```

## 快速开始

```bash
cd project/memory
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # 填入数据库与可选的 OpenAI 配置
mysql chat_system < db/schema.sql   # 初始化 6 张表

python -m examples.examples   # 运行全部示例
```

> 源码组织为 `src` 包，模块间以包前缀互相引用（`from src.models import ...`），
> 因此需从本目录以模块方式运行（`python -m ...`），而非直接执行脚本文件。
