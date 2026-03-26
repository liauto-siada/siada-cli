import agents
from pydantic_settings import BaseSettings
from typing import Optional, ClassVar


class Settings(BaseSettings):
    """
    Application configuration class
    
    Manages configuration using pydantic_settings, supports loading from environment variables
    """
    # Application basic information
    APP_NAME: str = "Siada API"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "Provides RPC capabilities for Siada agent"

    # API configuration
    API_PREFIX: str = "/api/v1"

    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True

    # Logging configuration
    LOG_LEVEL: str = "INFO"

    # OpenAI API configuration
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: Optional[str] = None
    OPENAI_API_VERSION: Optional[str] = None
    OPENAI_API_TYPE: Optional[str] = None
    OPENAI_ORGANIZATION: Optional[str] = None

    # Agent configuration
    Claude_4_0_SONNET: str = "claude-sonnet-4"
    Gemini_2_5_PRO: str = "gemini-2.5-pro"
    Deepseek_V3_0324: str = "deepseek-v3-0324"
    Deepseek_R1_0528: str = "deepseek-r1-0528"
    O1_MINI: str = "o1-mini"
    MAX_TURNS: int = 200
    DEFAULT_MODEL: str = Claude_4_0_SONNET
    
    # Memory search configuration
    ENABLE_MEMORY_SEARCH: bool = True


    # Set RunConfig as ClassVar so it won't be included in model validation
    _DEFAULT_RUN_CONFIG: ClassVar[agents.RunConfig] = None

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # 忽略未知的环境变量，避免升级后旧配置导致启动失败

    class Constants:
        # Agent name
        JANK_PROBLEM_AGENT_NAME: str = "JankProblemAgent"


# Create global settings object
settings = Settings()
settings.model_rebuild()  # Ensure model is fully built
