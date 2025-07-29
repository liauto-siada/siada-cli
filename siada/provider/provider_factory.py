from siada.provider.li.li_provider import SiadaProvider
from agents import ModelProvider

def get_provider(provider_name: str) -> ModelProvider:
    """
    根据提供商名称获取相应的模型提供商实例。

    Args:
        provider_name (str): 提供商的名称，例如 'li'。

    Returns:
        ModelProvider: 对应的模型提供商实例。

    Raises:
        ValueError: 如果提供商名称不受支持。
    """
    if provider_name == "li":
        return SiadaProvider()
    # TODO: 在此添加对 'openrouter' 的支持
    # elif provider_name == "openrouter":
    #     from siada.provider.openrouter.openrouter_provider import OpenRouterProvider
    #     return OpenRouterProvider() 
    else:
        raise ValueError(f"Model provider '{provider_name}' not supported") 