// 日历API接口定义
export interface CalendarAPIRequest {
  /** 查询文本，例如：三月十五日是什么节日、中秋节那天是星期几、现在几点、今天是什么星座、距离春节还有几天等 */
  refText: string;
  /** 日历API服务器地址，必须从knowledgeSearchTool的schema中获取 */
  apiUrl: string;
}

export interface CalendarAPIResponse {
  /** 请求是否成功 */
  success: boolean;
  /** 业务状态码，0表示成功 */
  code: number;
  /** 结果描述 */
  msg: string;
  /** 日历数据主体 */
  data: {
    /** 记录ID */
    recordId?: string | null;
    /** 请求ID */
    requestId?: string | null;
    /** 技能名称 */
    skill?: string | null;
    /** 上下文ID */
    contextId?: string | null;
    /** 会话ID */
    sessionId?: string | null;
    /** 技能ID */
    skillId?: string | null;
    /** 语音播报URL */
    speakUrl?: string | null;
    /** 语音采样率 */
    ttsSampleRate?: number | null;
    /** 对话管理信息 */
    dm?: {
      /** 任务ID */
      taskId?: string | null;
      /** 意图ID */
      intentId?: string | null;
      /** 日历信息描述 */
      nlg?: string | null;
      /** 用户输入 */
      input?: string | null;
      /** 任务类型 */
      task?: string | null;
      /** 意图名称 */
      intentName?: string | null;
      /** 状态码 */
      status?: number | null;
      /** 是否应结束会话 */
      shouldEndSession?: boolean | null;
      /** 上下文信息 */
      context?: {
        /** 当前意图名称 */
        currentIntentName?: string | null;
        /** 语言类型 */
        nlgLanguageClass?: string | null;
      } | null;
      /** 组件信息 */
      widget?: {
        /** 组件类型 */
        type?: string | null;
        /** 日期文本 */
        text?: string | null;
        /** DUI组件类型 */
        duiWidget?: string | null;
        /** 组件名称 */
        widgetName?: string | null;
        /** 名称 */
        name?: string | null;
        /** 额外信息 */
        extra?: {
          /** 星期 */
          weekday?: string | null;
          /** 星座 */
          constellation?: string | null;
          /** 星座起始日期 */
          constellationBegin?: string | null;
          /** 星座结束日期 */
          constellationEnd?: string | null;
          /** 星座(兼容字段) */
          cinstellation?: string | null;
          /** 农历日 */
          nlDay?: string | null;
          /** 月份 */
          month?: number | null;
          /** 是否为负数 */
          negative?: boolean | null;
          /** 天数间隔 */
          daysInterval?: number | null;
          /** 节日 */
          festival?: string | null;
          /** 年份 */
          year?: number | null;
          /** 日期 */
          day?: number | null;
          /** 节气 */
          solarTerm?: string | null;
          /** 农历月 */
          nlMonth?: string | null;
          /** 生肖 */
          zodiac?: string | null;
          /** 农历年 */
          nlYear?: string | null;
        } | null;
      } | null;
    } | null;
  };
}

// 日历API接口
export interface ICalendarAPI {
  /**
   * 获取日历信息
   * @param request 日历查询请求参数
   * @returns 日历信息响应
   */
  getCalendarInfo(request: CalendarAPIRequest): Promise<CalendarAPIResponse>;
}

// 日历API请求参数接口
interface CalendarRequest {
  refText: string;
  apiUrl: string;        // API服务器地址，必须传入
}

// 必需的请求头参数
const API_HEADERS = {
  Accept: "*/*",
  "Accept-Encoding": "gzip, deflate, br",
  Connection: "keep-alive",
  "User-Agent": "PostmanRuntime-ApipostRuntime/1.1.0"
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
 * 发送HTTP请求获取日历数据
 * @param refText 查询文本
 * @param apiUrl API服务器地址，必须从knowledgeSearchTool的schema中获取
 * @returns 日历数据JSON
 */
async function fetchCalendarData(refText: string, apiUrl: string): Promise<any> {
  try {
    const encodedRefText = encodeURIComponent(refText);
    const url = `${apiUrl}?refText=${encodedRefText}`;
    
    // 判断是云端还是车端请求
    const isVehicleRequest = apiUrl.includes('crs-hmi');
    
    if (isVehicleRequest) {
      // 车端请求：使用widgetBridge
      console.log('[carapi-js-lib][INFO] 检测到车端API地址，使用widgetBridge请求');
      
      if (typeof window !== 'undefined' && window.widgetBridge && window.widgetBridge.httpGet) {
        const result = window.widgetBridge.httpGet(url, JSON.stringify(API_HEADERS));
        console.log('[carapi-js-lib][INFO] calendar httpGetter result', result);
        console.log('[carapi-js-lib][INFO] calendar httpGetter result type', typeof result);
        
        if (!result) {
          throw new Error('日历API请求失败: 返回结果为空');
        }
        
        // 处理双重JSON格式
        let finalData;
        
        if (typeof result === 'string') {
          console.log('[carapi-js-lib][INFO] 解析日历JSON字符串');
          
          // 首先尝试解析外层JSON
          const parsedResult = JSON.parse(result);
          console.log('[carapi-js-lib][INFO] 日历第一次解析结果:', parsedResult);
          
          // 检查是否包含body字段（新格式：{code:200, body:"json_string", headers:{}}）
          if (parsedResult && typeof parsedResult === 'object' && parsedResult.body && parsedResult.code === 200) {
            console.log('[carapi-js-lib][INFO] 检测到包含body的格式，解析body字段');
            // 第二次解析body字段中的JSON字符串，这里才是真正的日历数据
            finalData = JSON.parse(parsedResult.body);
            console.log('[carapi-js-lib][INFO] 日历第二次解析body结果（最终数据）:', finalData);
          } else {
            // 如果没有body字段，说明是直接的API响应
            console.log('[carapi-js-lib][INFO] 直接使用第一次解析结果');
            finalData = parsedResult;
          }
        } else if (typeof result === 'object') {
          console.log('[carapi-js-lib][INFO] 直接返回日历对象');
          finalData = result;
        } else {
          throw new Error('日历API返回数据类型不正确: ' + typeof result);
        }
        
        console.log('[carapi-js-lib][INFO] 最终解析的日历数据:', finalData);
        
        // 确保返回的是最终的日历数据（包含success、code、data字段的对象）
        if (finalData && typeof finalData === 'object' && finalData.hasOwnProperty('success')) {
          return finalData;
        } else {
          throw new Error('日历API返回数据格式不正确，缺少success字段');
        }
      } else {
        throw new Error('当前环境不支持车机HTTP请求，请在车机环境中使用');
      }
    } else {
      // 云端请求：直接发起HTTP请求
      console.log('[carapi-js-lib][INFO] 检测到云端API地址，使用fetch请求');
      
      const response = await fetch(url, {
        method: 'GET',
        headers: API_HEADERS
      });
      
      if (!response.ok) {
        throw new Error(`日历API请求失败: HTTP ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('[carapi-js-lib][INFO] 云端API返回数据:', data);
      
      // 直接返回云端API的响应数据
      return data;
    }
  } catch (error) {
    console.error('[carapi-js-lib][ERROR] 日历API请求失败:', error);
    throw error;
  }
}

// 函数重载声明
export function GetCalendarInfo(request: CalendarRequest): Promise<any>;
export function GetCalendarInfo(refText: string, apiUrl: string): Promise<any>;

/**
 * GetCalendarInfo - 获取日历信息接口
 * 重要：apiUrl参数必须传入，应从knowledgeSearchTool的schema中获取
 * @param requestOrRefText 请求参数对象或查询文本
 * @param apiUrl 当第一个参数为string时，必须传入的API服务器地址
 * @returns Promise<日历数据JSON>
 */
export async function GetCalendarInfo(
  requestOrRefText: CalendarRequest | string,
  apiUrl?: string
): Promise<any> {
  if (typeof requestOrRefText === 'string') {
    // 直接传查询文本: GetCalendarInfo("中秋节那天是星期几", "必须的API地址")
    if (!apiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchCalendarData(requestOrRefText, apiUrl);
  } else {
    // 对象参数的方式: GetCalendarInfo({refText: "中秋节那天是星期几", apiUrl: "必须的API地址"})
    const { refText, apiUrl: requestApiUrl } = requestOrRefText;
    if (!requestApiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchCalendarData(refText, requestApiUrl);
  }
} 