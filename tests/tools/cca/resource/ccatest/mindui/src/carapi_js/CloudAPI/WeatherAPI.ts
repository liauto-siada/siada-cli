// 天气API接口定义
export interface WeatherAPIRequest {
  /** 城市或区域名称，必须是完整的中国行政区划名称（省/市/区格式） */
  district: string;
  /** 天气API服务器地址，必须从knowledgeSearchTool的schema中获取 */
  apiUrl: string;
  /** 数据刷新间隔时间，单位为毫秒，默认60000毫秒（60秒） */
  refreshMs?: number;
}

export interface WeatherAPIResponse {
  /** 请求是否成功 */
  success: boolean;
  /** 状态码 */
  code: number;
  /** 天气数据主体 */
  data: {
    /** 天气预警信息 */
    alert: {
      status?: string | null;
      adcodes?: Array<{
        name?: string | null;
        adcode?: string | null;
      }> | null;
      content?: Array<{
        province?: string | null;
        status?: string | null;
        code?: string | null;
        description?: string | null;
        title?: string | null;
        city?: string | null;
      }> | null;
    };
    /** 实时天气信息 */
    realtime: {
      status?: string | null;
      /** 温度(°C) */
      temperature?: string | null;
      /** 湿度(0-1) */
      humidity?: string | null;
      /** 云量(0-1) */
      cloudrate?: string | null;
      /** 天空状况 */
      skycon?: string | null;
      /** 能见度(km) */
      visibility?: string | null;
      /** 短波辐射(W/m²) */
      dswrf?: string | null;
      /** 风力信息 */
      wind: {
        /** 风速(m/s) */
        speed?: string | null;
        /** 风向(°) */
        direction?: string | null;
        datetime?: string | null;
      };
      /** 气压(Pa) */
      pressure?: string | null;
      /** 体感温度(°C) */
      apparent_temperature?: string | null;
      /** 实时降水 */
      precipitation: {
        local: {
          status?: string | null;
          datasource?: string | null;
          /** 降水强度(mm/h) */
          intensity?: string | null;
        };
        nearest: {
          status?: string | null;
          /** 强度(mm/h) */
          intensity?: string | null;
          /** 距离(km) */
          distance?: string | null;
        };
      };
      /** 实时空气质量 */
      air_quality: {
        aqi: {
          /** 中国AQI */
          chn?: string | null;
          /** 美国AQI */
          usa?: string | null;
        };
        /** PM2.5(µg/m³) */
        pm25?: string | null;
        /** PM10(µg/m³) */
        pm10?: string | null;
        /** 一氧化碳(mg/m³) */
        co?: string | null;
        /** 二氧化氮(µg/m³) */
        no2?: string | null;
        /** 臭氧(µg/m³) */
        o3?: string | null;
        /** 二氧化硫(µg/m³) */
        so2?: string | null;
        description: {
          /** 中文描述 */
          chn?: string | null;
          /** 英文描述 */
          usa?: string | null;
        };
      };
      /** 实时生活指数 */
      life_index: {
        ultraviolet: {
          index?: string | null;
          desc?: string | null;
        };
        comfort: {
          index?: string | null;
          desc?: string | null;
        };
      };
    };
    /** 每日天气信息（未来7天） */
    daily: {
      status?: string | null;
      /** 七日日出日落信息 */
      astro?: Array<{
        date?: string | null;
        sunrise: { time?: string | null };
        sunset: { time?: string | null };
      }> | null;
      /** 七日温度预报 */
      temperature?: Array<{
        date?: string | null;
        /** 最高温度(°C) */
        max?: string | null;
        /** 最低温度(°C) */
        min?: string | null;
        /** 平均温度(°C) */
        avg?: string | null;
      }> | null;
      /** 七日天空状况 */
      skycon?: Array<{
        date?: string | null;
        value?: string | null;
      }> | null;
      /** 七日白天天空状况(08:00-20:00) */
      skycon_08h_20h?: Array<{
        date?: string | null;
        value?: string | null;
      }> | null;
      /** 七日夜间天空状况(20:00-次日08:00) */
      skycon_20h_32h?: Array<{
        date?: string | null;
        value?: string | null;
      }> | null;
      /** 七日空气质量预报 */
      air_quality: {
        aqi?: Array<{
          date?: string | null;
          max: { chn?: string | null };
          min: { chn?: string | null };
          avg: { chn?: string | null };
        }> | null;
        pm25?: Array<{
          date?: string | null;
          max?: string | null;
          min?: string | null;
          avg?: string | null;
        }> | null;
      };
      /** 七日生活指数预报 */
      life_index: {
        ultraviolet?: Array<{
          index?: string | null;
          date?: string | null;
          desc?: string | null;
        }> | null;
        comfort?: Array<{
          index?: string | null;
          date?: string | null;
          desc?: string | null;
        }> | null;
      };
    };
    /** 预报要点 */
    forecast_keypoint?: string | null;
  };
  /** 响应消息 */
  msg: string;
}

// 天气API接口
export interface IWeatherAPI {
  /**
   * 获取天气信息
   * @param request 天气查询请求参数
   * @returns 天气信息响应
   */
  getWeatherInfo(request: WeatherAPIRequest): Promise<WeatherAPIResponse>;
}

// 天气API接口实现
interface WeatherAPIProps {
  district: string;      // 地区名称
  apiUrl: string;        // API服务器地址，必须传入
  refreshMs?: number;    // 刷新间隔，默认60秒
}

// 天气API请求参数接口
interface WeatherRequest {
  district: string;
  apiUrl: string;        // API服务器地址，必须传入
  refreshMs?: number;    // 保留参数定义但不在API内部使用
}

// 必需的请求头参数
const API_HEADERS = {
  appId: "com.chehejia.car.cca",
  tripartiteDeviceId: "1122344",
  msgId: "weather-request-" + Date.now()
};

// 为widgetBridge添加类型声明
declare global {
  interface Window {
    widgetBridge?: {
      httpGet: (url: string, headers?: string) => string;
    };
  }
}

/**
 * 发送HTTP请求获取天气数据
 * @param district 地区名称
 * @param apiUrl API服务器地址，必须从knowledgeSearchTool的schema中获取
 * @returns 天气数据JSON
 */
async function fetchWeatherData(district: string, apiUrl: string): Promise<any> {
  try {
    const url = `${apiUrl}?district=${district}`;
    
    // 判断是云端还是车端请求
    const isVehicleRequest = apiUrl.includes('crs-hmi');
    
    if (isVehicleRequest) {
      // 车端请求：使用widgetBridge
      console.log('[carapi-js-lib][INFO] 检测到车端API地址，使用widgetBridge请求');
      
      if (typeof window !== 'undefined' && window.widgetBridge && window.widgetBridge.httpGet) {
        const headers = {
          ...API_HEADERS,
          msgId: "weather-request-" + Date.now()
        };
        const result = window.widgetBridge.httpGet(url, JSON.stringify(headers));
        console.log('[carapi-js-lib][INFO] weather httpGetter result', result);
        console.log('[carapi-js-lib][INFO] weather httpGetter result type', typeof result);
        
        if (!result) {
          throw new Error('天气API请求失败: 返回结果为空');
        }
        
        // 处理双重JSON格式
        let finalData;
        
        if (typeof result === 'string') {
          console.log('[carapi-js-lib][INFO] 解析天气JSON字符串');
          
          // 首先尝试解析外层JSON
          const parsedResult = JSON.parse(result);
          console.log('[carapi-js-lib][INFO] 天气第一次解析结果:', parsedResult);
          
          // 检查是否包含body字段（新格式：{code:200, body:"json_string", headers:{}}）
          if (parsedResult && typeof parsedResult === 'object' && parsedResult.body && parsedResult.code === 200) {
            console.log('[carapi-js-lib][INFO] 检测到包含body的格式，解析body字段');
            // 第二次解析body字段中的JSON字符串，这里才是真正的天气数据
            finalData = JSON.parse(parsedResult.body);
            console.log('[carapi-js-lib][INFO] 天气第二次解析body结果（最终数据）:', finalData);
          } else {
            // 如果没有body字段，说明是直接的API响应
            console.log('[carapi-js-lib][INFO] 直接使用第一次解析结果');
            finalData = parsedResult;
          }
        } else if (typeof result === 'object') {
          console.log('[carapi-js-lib][INFO] 直接返回天气对象');
          finalData = result;
        } else {
          throw new Error('天气API返回数据类型不正确: ' + typeof result);
        }
        
        console.log('[carapi-js-lib][INFO] 最终解析的天气数据:', finalData);
        
        // 对于天气API，检查是否包含success字段或data字段
        if (finalData && typeof finalData === 'object' && (finalData.hasOwnProperty('success') || finalData.hasOwnProperty('data'))) {
          return finalData;
        } else {
          throw new Error('天气API返回数据格式不正确，缺少success或data字段');
        }
      } else {
        throw new Error('当前环境不支持车机HTTP请求，请在车机环境中使用');
      }
    } else {
      // 云端请求：直接发起HTTP请求
      console.log('[carapi-js-lib][INFO] 检测到云端API地址，使用fetch请求');
      
      const headers = {
        ...API_HEADERS,
        msgId: "weather-request-" + Date.now()
      };
      
      const response = await fetch(url, {
        method: 'GET',
        headers: headers
      });
      
      if (!response.ok) {
        throw new Error(`天气API请求失败: HTTP ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('[carapi-js-lib][INFO] 云端API返回数据:', data);
      
      // 直接返回云端API的响应数据
      return data;
    }
  } catch (error) {
    console.error('[carapi-js-lib][ERROR] 天气API请求失败:', error);
    throw error;
  }
}

// 函数重载声明
export function GetWeatherInfo(request: WeatherRequest): Promise<any>;
export function GetWeatherInfo(district: string, apiUrl: string): Promise<any>;

/**
 * GetWeatherInfo - 获取天气信息接口
 * 重要：apiUrl参数必须传入，应从knowledgeSearchTool的schema中获取
 * @param requestOrDistrict 请求参数对象或地区名称
 * @param apiUrl 当第一个参数为string时，必须传入的API服务器地址
 * @returns Promise<天气数据JSON>
 */
export async function GetWeatherInfo(
  requestOrDistrict: WeatherRequest | string,
  apiUrl?: string
): Promise<any> {
  if (typeof requestOrDistrict === 'string') {
    // 直接传地区名称: GetWeatherInfo("地区", "必须的API地址")
    if (!apiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchWeatherData(requestOrDistrict, apiUrl);
  } else {
    // 对象参数的方式: GetWeatherInfo({district: "地区", apiUrl: "必须的API地址"})
    const { district, apiUrl: requestApiUrl } = requestOrDistrict;
    if (!requestApiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchWeatherData(district, requestApiUrl);
  }
} 