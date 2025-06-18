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
    DEFAULT_MODEL: str = "claude-3-7-sonnet"
    Claude_4_0_SONNET: str = "claude-sonnet-4"
    O1_MINI: str = "o1-mini"
    MAX_TURNS: int = 60

    # 将RunConfig设置为ClassVar，这样它不会被包含在模型验证中
    _DEFAULT_RUN_CONFIG: ClassVar[agents.RunConfig] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True

    class Constants:
        # Agent名称
        JANK_PROBLEM_AGENT_NAME: str = "JankProblemAgent"

    @property
    def DEFAULT_RUN_CONFIG(self) -> agents.RunConfig:
        """
        延迟加载RunConfig，避免循环导入
        """
        if self._DEFAULT_RUN_CONFIG is None:
            # 在这里导入SiadaProvider，避免循环导入
            from siada.models.provider import SiadaProvider
            self.__class__._DEFAULT_RUN_CONFIG = agents.RunConfig(model=self.DEFAULT_MODEL,
                                                                  tracing_disabled=True,
                                                                  model_provider=SiadaProvider())
        return self._DEFAULT_RUN_CONFIG





# 创建全局设置对象
settings = Settings()
settings.model_rebuild()  # 确保模型完全构建
