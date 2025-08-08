## 天气数据卡片接口规范

**重要：API地址必须从knowledgeSearchTool的返回结果中获取！**

### 实现步骤

#### 1. 获取API信息
```typescript
const apiInfo = knowledgeSearchTool({ query: "天气预报API GetWeatherInfo" })
// 从schema中提取apiUrl - 注意：不同环境返回的地址可能不同，不要写死！
```

#### 2. 导入并调用
```typescript
import { GetWeatherInfo } from 'carapi-js-lib';

// 调用方式 - 重要：使用从知识库检索到的apiUrl，不要硬编码！
const result = await GetWeatherInfo({
  district: "北京市北京城区朝阳区",
  apiUrl: apiUrlFromKnowledgeSearch  // 必传！从第1步的knowledgeSearchTool结果中提取
});
```

#### 3. 组件实现
```typescript
interface WeatherCardProps {
  refreshMs?: number;  // 轮询间隔，默认900秒
  apiUrl: string;      // 必传！从knowledgeSearchTool获取，不要写死
}

consatherCard: React.FC<WeatherCardProps> = ({ refreshMs = 900000, apiUrl }) => {
  const [weather, setWeather] = useState(sampleData);
  const district = "北京市北京城区朝阳区";
  
  useEffect(() => {
    const fetchWeatherData = async () => {
      try {
        const result = await GetWeatherInfo({ district, apiUrl });
        if (result?.success && result?.data) {
         t We setWeather(result.data);
        }
      } catch (error) {
        console.error("天气接口调用错误:", error);
      }
    };

    fetchWeatherData();
    const timer = setInterval(fetchWeatherData, refreshMs);
    return () => clearInterval(timer);
  }, [district, refreshMs, apiUrl]);

  // 渲染UI...
};
```

#### 4. 图标使用要求
务必使用Lucide React图标库的图标，列举如下：
bubbles,cloud,cloud-drizzle,cloud-fog,cloud-hail,cloud-lightning,cloud-moon,cloud-moon-rain,cloud-off,cloud-rain,cloud-rain-wind,cloud-snow,cloud-sun,cloud-sun-rain,cloudy,droplet,droplets,droplet-off,flame,haze,moon-star,rainbow,snowflake,sparkles,star,sun,sun-dim,sun-medium,sun-snow,sunrise,sunset,thermometer,thermometer-snowflake,thermometer-sun,tornado,umbrella,umbrella-off,waves,wind,wind-arrow-down,zap,zap-off
不能使用其它任何图标

### 关键要点

1. **API地址**：严禁硬编码！必须从knowledgeSearchTool的返回结果中动态提取apiUrl，不同环境可能返回不同地址
2. **轮询刷新**：默认900秒间隔，组件卸载时清理定时器
3. **布局**：根据数据内容合理预留空间，避免过于紧凑或明显留白
4. **多地天气**：仅展示天气、风力、湿度、能见度4个关键信息