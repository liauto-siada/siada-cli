from agents import function_tool
from typing_extensions import TypedDict


class Location(TypedDict):
    lat: float
    long: float


@function_tool
async def fetch_weather(city: str) -> str:
    """Fetch weather information for a specified city.
    
    Args:
        city (str): Name of the city, e.g., "Beijing", "Shanghai"
    """
    # In a real application, we would fetch data from a weather API
    return f"the weather of {city} is sunny"
