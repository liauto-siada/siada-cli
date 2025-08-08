// 星座运势API接口定义
export interface HoroscopeAPIRequest {
  /** 查询文本，例如：查询天蝎座的运势、白羊座今日运势、双子座爱情运势等 */
  refText: string;
  /** 星座运势API服务器地址，必须从knowledgeSearchTool的schema中获取 */
  apiUrl: string;
}

export interface HoroscopeAPIResponse {
  /** 请求是否成功 */
  success: boolean;
  /** 业务状态码，0表示成功 */
  code: number;
  /** 结果描述 */
  msg: string;
  /** 星座运势数据主体 */
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
      /** 运势描述 */
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
        /** 副标题 */
        subTitle?: string | null;
        /** 星座名称 */
        title?: string | null;
        /** DUI组件类型 */
        duiWidget?: string | null;
        /** 组件名称 */
        widgetName?: string | null;
        /** 错误码 */
        errorCode?: number | null;
        /** 名称 */
        name?: string | null;
        /** 品牌信息 */
        brand?: {
          /** 显示名称 */
          showName?: string | null;
          /** 是否导出 */
          isexport?: string | null;
          /** 小尺寸logo */
          logoSmall?: string | null;
          /** 名称 */
          name?: string | null;
          /** 中尺寸logo */
          logoMiddle?: string | null;
          /** 大尺寸logo */
          logoLarge?: string | null;
        } | null;
        /** 额外信息 */
        extra?: {
          /** 数据源ID */
          sourceId?: number | null;
          /** 工作指数 */
          workIndex?: number | null;
          /** 爱情指数 */
          loveIndex?: number | null;
          /** 爱情运势 */
          loveTxt?: string | null;
          /** 幸运颜色 */
          luckyColor?: string | null;
          /** 财富指数 */
          moneyIndex?: number | null;
          /** 速配星座 */
          matchSign?: string | null;
          /** 幸运数字 */
          luckyNumber?: number | null;
          /** 工作运势 */
          workText?: string | null;
          /** 星座性格 */
          signFeature?: string | null;
          /** 星座运势 */
          signSummary?: string | null;
          /** 财富运势 */
          moneyText?: string | null;
          /** 综合指数 */
          totalScore?: number | null;
          /** 出生日期范围 */
          dateRange?: string | null;
        } | null;
      } | null;
    } | null;
  };
}

// 星座运势API接口
export interface IHoroscopeAPI {
  /**
   * 获取星座运势信息
   * @param request 星座运势查询请求参数
   * @returns 星座运势信息响应
   */
  getHoroscopeInfo(request: HoroscopeAPIRequest): Promise<HoroscopeAPIResponse>;
}

// 星座运势API请求参数接口
interface HoroscopeRequest {
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
 * 发送HTTP请求获取星座运势数据
 * @param refText 查询文本
 * @param apiUrl API服务器地址，必须从knowledgeSearchTool的schema中获取
 * @returns 星座运势数据JSON
 */
async function fetchHoroscopeData(refText: string, apiUrl: string): Promise<any> {
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
        console.log('[carapi-js-lib][INFO] horoscope httpGetter result', result);
        console.log('[carapi-js-lib][INFO] horoscope httpGetter result type', typeof result);
        
        if (!result) {
          throw new Error('星座运势API请求失败: 返回结果为空');
        }
        
        // 处理双重JSON格式
        let finalData;
        
        if (typeof result === 'string') {
          console.log('[carapi-js-lib][INFO] 解析星座运势JSON字符串');
          
          // 首先尝试解析外层JSON
          const parsedResult = JSON.parse(result);
          console.log('[carapi-js-lib][INFO] 星座运势第一次解析结果:', parsedResult);
          
          // 检查是否包含body字段（新格式：{code:200, body:"json_string", headers:{}}）
          if (parsedResult && typeof parsedResult === 'object' && parsedResult.body && parsedResult.code === 200) {
            console.log('[carapi-js-lib][INFO] 检测到包含body的格式，解析body字段');
            // 第二次解析body字段中的JSON字符串，这里才是真正的星座运势数据
            finalData = JSON.parse(parsedResult.body);
            console.log('[carapi-js-lib][INFO] 星座运势第二次解析body结果（最终数据）:', finalData);
          } else {
            // 如果没有body字段，说明是直接的API响应
            console.log('[carapi-js-lib][INFO] 直接使用第一次解析结果');
            finalData = parsedResult;
          }
        } else if (typeof result === 'object') {
          console.log('[carapi-js-lib][INFO] 直接返回星座运势对象');
          finalData = result;
        } else {
          throw new Error('星座运势API返回数据类型不正确: ' + typeof result);
        }
        
        console.log('[carapi-js-lib][INFO] 最终解析的星座运势数据:', finalData);
        
        // 确保返回的是最终的星座运势数据（包含success、code、data字段的对象）
        if (finalData && typeof finalData === 'object' && finalData.hasOwnProperty('success')) {
          return finalData;
        } else {
          throw new Error('星座运势API返回数据格式不正确，缺少success字段');
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
        throw new Error(`星座运势API请求失败: HTTP ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('[carapi-js-lib][INFO] 云端API返回数据:', data);
      
      // 直接返回云端API的响应数据
      return data;
    }
  } catch (error) {
    console.error('[carapi-js-lib][ERROR] 星座运势API请求失败:', error);
    throw error;
  }
}

// 函数重载声明
export function GetHoroscopeInfo(request: HoroscopeRequest): Promise<any>;
export function GetHoroscopeInfo(refText: string, apiUrl: string): Promise<any>;

/**
 * GetHoroscopeInfo - 获取星座运势信息接口
 * 重要：apiUrl参数必须传入，应从knowledgeSearchTool的schema中获取
 * @param requestOrRefText 请求参数对象或查询文本
 * @param apiUrl 当第一个参数为string时，必须传入的API服务器地址
 * @returns Promise<星座运势数据JSON>
 */
export async function GetHoroscopeInfo(
  requestOrRefText: HoroscopeRequest | string,
  apiUrl?: string
): Promise<any> {
  if (typeof requestOrRefText === 'string') {
    // 直接传查询文本: GetHoroscopeInfo("查询天蝎座的运势", "必须的API地址")
    if (!apiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchHoroscopeData(requestOrRefText, apiUrl);
  } else {
    // 对象参数的方式: GetHoroscopeInfo({refText: "查询天蝎座的运势", apiUrl: "必须的API地址"})
    const { refText, apiUrl: requestApiUrl } = requestOrRefText;
    if (!requestApiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchHoroscopeData(refText, requestApiUrl);
  }
} 