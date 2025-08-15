import agents
from pydantic_settings import BaseSettings
from typing import Optional, ClassVar


class Settings(BaseSettings):
    """
    应用配置类
    
    使用pydantic_settings管理配置，支持从环境变量加载
    """
    # 应用基本信息
    APP_NAME: str = "Siada API"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "提供Siada agent对外的RPC能力"

    # API配置
    API_PREFIX: str = "/api/v1"

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True

    # 日志配置
    LOG_LEVEL: str = "INFO"

    # OpenAI API配置
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: Optional[str] = None
    OPENAI_API_VERSION: Optional[str] = None
    OPENAI_API_TYPE: Optional[str] = None
    OPENAI_ORGANIZATION: Optional[str] = None

    # Agent配置
    Claude_4_0_SONNET: str = "claude-sonnet-4"
    Gemini_2_5_PRO: str = "gemini-2.5-pro"
    Deepseek_V3_0324: str = "deepseek-v3-0324"
    Deepseek_R1_0528: str = "deepseek-r1-0528"
    O1_MINI: str = "o1-mini"
    MAX_TURNS: int = 200
    DEFAULT_MODEL: str = Claude_4_0_SONNET


    # 将RunConfig设置为ClassVar，这样它不会被包含在模型验证中
    _DEFAULT_RUN_CONFIG: ClassVar[agents.RunConfig] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

    class Constants:
        # Agent名称
        JANK_PROBLEM_AGENT_NAME: str = "JankProblemAgent"


# 创建全局设置对象
settings = Settings()
settings.model_rebuild()  # 确保模型完全构建
