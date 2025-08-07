import React, { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { IconButton } from '@/components/ui/iconbutton'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'

import '../index.css'
import { DynamicTemplates } from '../templates/dynamicDisplayTemplates/dynamicTemplates'
import { NewsTemplates } from '../templates/newsTemplates/newsTemplates'
import { HorizontalSelector } from '../components/mindui/horizontal-selector'
import { MapPin, Cloud, Sun, CloudRain } from "lucide-react"

// @ts-ignore
import { get_vehicle_driving_status, set_vehicle_driving_control } from 'carapi-js-lib'
// @ts-ignore
import { GetWeatherInfo } from 'carapi-js-lib'
import { GetLixiangStudentInfo } from "../carapi_js/CloudAPI/LixiangStudentAPI"

// 车控卡片组件
const VehicleControlCard = () => {
  return (
    <DynamicTemplates data={[
      {
        label: "动力模式",
        iconSrc: "Car",
        setFunc: async (value) => {
          try {
            return await set_vehicle_driving_control('CarSettingsTpuPlugin_PowerMode', value);
          } catch (error) {
            console.error('设置API调用错误:', error);
          }
        },
        getFunc: async () => {
          try {
            const result = await get_vehicle_driving_status('DrivingMode');
            if (result?.success && result?.data) {
              return result.data.DrivingMode;
            }
            return null;
          } catch (error) {
            console.error('API调用错误:', error);
            return null;
          }
        },
        getType: "DrivingMode",
        needAdjust: true,
        valueMapping: new Map([
          [0, "舒适"],
          [1, "标准"],
          [2, "运动"],
          [3, "高性能"],
          [4, "节能"],
          [5, "后排舒适"]
        ])
      },
      {
        label: "魔毯悬架",
        iconSrc: "Car",
        setFunc: async (value) => {
          try {
            return await set_vehicle_driving_control('CarSettingsTpuPlugin_MagicSuspensionMode', value);
          } catch (error) {
            console.error('设置API调用错误:', error);
          }
        },
        getFunc: async () => {
          try {
            const result = await get_vehicle_driving_status('AirSuspension');
            if (result?.success && result?.data) {
              return result.data.AirSuspension;
            }
            return null;
          } catch (error) {
            console.error('API调用错误:', error);
            return null;
          }
        },
        getType: "AirSuspension",
        needAdjust: false,
        valueMapping: new Map([
          [0, "舒适魔毯"],
          [1, "运动魔毯"]
        ])
      },
      {
        label: "悬架舒适度",
        iconSrc: "Car",
        setFunc: async (value) => {
          try {
            return await set_vehicle_driving_control('CarSettingsTpuPlugin_SuspensionComfortLevel', value);
          } catch (error) {
            console.error('设置API调用错误:', error);
          }
        },
        getFunc: async () => {
          try {
            const result = await get_vehicle_driving_status('SuspensionAdjustment');
            if (result?.success && result?.data) {
              return result.data.SuspensionAdjustment;
            }
            return null;
          } catch (error) {
            console.error('API调用错误:', error);
            return null;
          }
        },
        getType: "SuspensionAdjustment",
        needAdjust: true,
        valueMapping: new Map([
          [0, "舒适"],
          [1, "标准"],
          [2, "运动"]
        ])
      },
      {
        label: "转向模式",
        iconSrc: "Car",
        setFunc: async (value) => {
          try {
            return await set_vehicle_driving_control('CarSettingsTpuPlugin_SteeringMode', value);
          } catch (error) {
            console.error('设置API调用错误:', error);
          }
        },
        getFunc: async () => {
          try {
            const result = await get_vehicle_driving_status('TurnRound');
            if (result?.success && result?.data) {
              return result.data.TurnRound;
            }
            return null;
          } catch (error) {
            console.error('API调用错误:', error);
            return null;
          }
        },
        getType: "TurnRound",
        needAdjust: true,
        valueMapping: new Map([
          [0, "舒适"],
          [1, "标准"],
          [2, "运动"]
        ])
      },
      {
        label: "能量回收",
        iconSrc: "Car",
        setFunc: async (value) => {
          try {
            return await set_vehicle_driving_control('CarSettingsTpuPlugin_RegenerativeBrakingLevel', value);
          } catch (error) {
            console.error('设置API调用错误:', error);
          }
        },
        getFunc: async () => {
          try {
            const result = await get_vehicle_driving_status('EnergyRecovery');
            if (result?.success && result?.data) {
              return result.data.EnergyRecovery;
            }
            return null;
          } catch (error) {
            console.error('API调用错误:', error);
            return null;
          }
        },
        getType: "EnergyRecovery",
        needAdjust: true,
        valueMapping: new Map([
          [0, "舒适"],
          [1, "标准"],
          [2, "强"]
        ])
      },
      {
        label: "低速警示音",
        iconSrc: "Car",
        setFunc: async (value) => {
          try {
            return await set_vehicle_driving_control('CarSettingsTpuPlugin_LowSpeedWarningEnabled', value);
          } catch (error) {
            console.error('设置API调用错误:', error);
          }
        },
        getFunc: async () => {
          try {
            const result = await get_vehicle_driving_status('VESS');
            if (result?.success && result?.data) {
              return result.data.VESS;
            }
            return null;
          } catch (error) {
            console.error('API调用错误:', error);
            return null;
          }
        },
        getType: "VESS",
        needAdjust: false,
        valueMapping: new Map([
          [0, "关闭"],
          [1, "开启"]
        ])
      }
    ]} />
  );
};

// 新闻卡片组件
const InternationalNewsCard = () => {
    return (
        <NewsTemplates 
            data={{
        text: "国际新闻热点",
        vin: "WEB1b247b0f111111",
        apiUrl: "请填写实际的API Url"
    }}
        />
    );
};

// 天气卡片组件类型定义
interface CityWeatherProps {
  location: string;
  temperature: string;
  weather: string;
  wind: string;
  humidity: string;
  visibility: string;
}

const CityWeather = ({
  location,
  temperature,
  weather,
  wind,
  humidity,
  visibility,
}: CityWeatherProps) => {
  const getWeatherIcon = (weatherDesc: string) => {
    if (weatherDesc.includes("雨")) return <CloudRain className="w-16 h-16 text-gray-600" />;
    if (weatherDesc.includes("云")) return <Cloud className="w-16 h-16 text-gray-600" />;
    return <Sun className="w-16 h-16 text-gray-600" />;
  };

  return (
    <div className="flex h-[480px] w-full flex-col rounded-3xl bg-slate-50">
      {/* 顶部：温度、天气、城市 */}
      <div className="flex flex-1 flex-col">
        <div className="flex items-start justify-between">
          <div className="ml-[35px] text-gray-950">
            <div className="mt-[35px] text-8xl leading-none font-bold">
              {temperature}
              <span className="ml-[6px] box-border inline-block h-[32px] w-[32px] rounded-full border-[9px] border-gray-950 align-top" />
            </div>
            <div className="mt-[25px] flex items-center gap-4">
              <div className="text-3xl font-bold text-gray-900">{weather}</div>
              {getWeatherIcon(weather)}
            </div>
          </div>
          <div className="mt-[25px] mr-[30px] flex items-center justify-end text-xl font-bold text-gray-400">
            <MapPin className="mr-2 w-6 h-6" />
            {location}
          </div>
        </div>
      </div>
      {/* 底部三栏 */}
      <div className="mx-[25px] mt-auto flex border-t-2 border-gray-100">
        <div className="my-[25px] flex-1 border-r-2 border-gray-100 pl-[30px] text-left">
          <div className="text-lg font-semibold text-gray-600">风力</div>
          <div className="text-2xl font-semibold text-gray-950">{wind}</div>
        </div>
        <div className="my-[25px] flex-1 pl-[30px] text-left">
          <div className="text-lg font-semibold text-gray-600">湿度</div>
          <div className="text-2xl font-semibold text-gray-950">{humidity}</div>
        </div>
        <div className="my-[25px] flex-1 border-l-2 border-gray-100 pl-[30px] text-left">
          <div className="text-lg font-semibold text-gray-600">能见度</div>
          <div className="text-2xl font-semibold text-gray-950">
            {visibility}
          </div>
        </div>
      </div>
    </div>
  );
};

const WeatherCard = () => {
  const [beijingWeather, setBeijingWeather] = useState<CityWeatherProps>({
    location: "北京",
    temperature: "",
    weather: "",
    wind: "",
    humidity: "",
    visibility: "",
  });

  // 从API schema获取apiUrl参数
  const apiUrl = "请填写实际的API Url";

  useEffect(() => {
    const fetchWeatherData = async () => {
      try {
        // 获取北京天气
        const beijingResult = await GetWeatherInfo({
          district: "北京市北京城区朝阳区",
          apiUrl: apiUrl
        });

        if (beijingResult?.success && beijingResult?.data) {
          const data = beijingResult.data;
          const temp = Math.round(parseFloat(data.realtime?.temperature || "0"));
          const windSpeed = Math.round(parseFloat(data.realtime?.wind?.speed || "0") * 3.6 / 10);
          const humidity = Math.round(parseFloat(data.realtime?.humidity || "0") * 100);
          const visibility = Math.round(parseFloat(data.realtime?.visibility || "0"));
          
          let weatherDesc = "晴";
          const skycon = data.realtime?.skycon;
          if (skycon?.includes("CLOUDY")) weatherDesc = "多云";
          else if (skycon?.includes("RAIN")) weatherDesc = "雨";
          else if (skycon?.includes("SNOW")) weatherDesc = "雪";
          
          setBeijingWeather({
            location: "北京",
            temperature: temp.toString(),
            weather: weatherDesc,
            wind: `${windSpeed}级`,
            humidity: `${humidity}%`,
            visibility: `${visibility}km`,
          });
        }
      } catch (error) {
        console.error("天气接口调用错误:", error);
      }
    };

    fetchWeatherData();
    // 每15分钟刷新一次天气数据
    const timer = setInterval(fetchWeatherData, 900000);
    return () => clearInterval(timer);
  }, []);

  return (
    <ScrollArea className="h-full w-full">
      <div className="space-y-[20px] pb-[20px]">
        <CityWeather {...beijingWeather} />
      </div>
    </ScrollArea>
  );
};

// 主要的组合卡片组件
const CombinedCard = () => {
  const [activeTab, setActiveTab] = useState("news");

  // 卡片选项
  const cardOptions = [
    { label: "📰 新闻资讯", value: "news" },
    { label: "🚗 车辆控制", value: "car" },
    { label: "🌤️ 北京天气", value: "weather" }
  ];

  return (
    <div className="w-full h-full flex flex-col">
      {/* 使用 HorizontalSelector 替代自定义 Tab */}
      <div className="mb-[30px]">
        <HorizontalSelector
          options={cardOptions}
          value={activeTab}
          onChange={setActiveTab}
          size="lg"
          color="primary"
        />
      </div>

      {/* 卡片内容区域 */}
      <div className="flex-1 min-h-0">
        {activeTab === "news" && <InternationalNewsCard />}
        {activeTab === "car" && <VehicleControlCard />}
        {activeTab === "weather" && <WeatherCard />}
      </div>
    </div>
  );
};

export default CombinedCard


import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'

const App = () => {
  return (
    <div className="w-[933px] h-[1360px] bg-slate-200 rounded-[20px] py-[60px] relative">
      {/* 标题区域 */}
      <div className="px-[60px] mb-[100px]">
        <h1 className="text-[52px] font-bold text-gray-800">智能卡片中心</h1>
      </div>

      {/* 内容区域 - 左右都保持60px边距，滚动条包含在右边距内，底部保持50px安全距离 */}
      <div className="pl-[60px] pr-[30px] pb-[50px]" style={{ height: 'calc(100% - 120px)' }}>
        <div className="relative h-full">
          <ScrollArea className="h-full w-full">
            <div className="pr-[35px]">
              <CombinedCard />
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  )
}

const rootElement = document.getElementById('root')
if (rootElement) {
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>
  )
}
