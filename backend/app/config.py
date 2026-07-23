"""
配置管理
从项目根目录加载配置文件（可见文件，非隐藏）
优先顺序：env.txt → env.example → 环境变量
"""

import os
from dotenv import load_dotenv

# 只加载可见的配置文件
project_root = os.path.join(os.path.dirname(__file__), "../..")
env_txt = os.path.join(project_root, "env.txt")
env_example = os.path.join(project_root, "env.example")

if os.path.exists(env_txt):
    load_dotenv(env_txt, override=True)
elif os.path.exists(env_example):
    load_dotenv(env_example, override=True)


class Config:
    """Flask配置类"""
    
    SECRET_KEY = os.environ.get("SECRET_KEY", "writegod-secret-key")
    DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    JSON_AS_ASCII = False
    
    # LLM配置
    LLM_API_KEY = os.environ.get("LLM_API_KEY")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini")
    
    # ===== 结构化输出（JSON模式）LLM配置 =====
    JSON_LLM_API_KEY = os.environ.get("JSON_LLM_API_KEY") or os.environ.get("LLM_API_KEY")
    JSON_LLM_BASE_URL = os.environ.get("JSON_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL")
    JSON_LLM_MODEL_NAME = os.environ.get("JSON_LLM_MODEL_NAME") or os.environ.get("LLM_MODEL_NAME")
    
    # ===== Embedding 模型配置 =====
    EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY") or os.environ.get("LLM_API_KEY")
    EMBEDDING_BASE_URL = os.environ.get("EMBEDDING_BASE_URL") or os.environ.get("LLM_BASE_URL")
    EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "text-embedding-3-small")
    
    # ===== Neo4j 图数据库配置 =====
    NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "writegod")
    
    # 加速 LLM 配置
    LLM_BOOST_API_KEY = os.environ.get("LLM_BOOST_API_KEY")
    LLM_BOOST_BASE_URL = os.environ.get("LLM_BOOST_BASE_URL")
    LLM_BOOST_MODEL_NAME = os.environ.get("LLM_BOOST_MODEL_NAME")
    
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "../uploads")
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}
    DEFAULT_CHUNK_SIZE = 500
    DEFAULT_CHUNK_OVERLAP = 50
    
    @classmethod
    def validate(cls) -> list[str]:
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        if not cls.NEO4J_URI:
            errors.append("NEO4J_URI 未配置")
        if not cls.NEO4J_PASSWORD or cls.NEO4J_PASSWORD == "writegod":
            errors.append("NEO4J_PASSWORD 未配置或使用了默认值，请在 env.txt 中设置")
        return errors
