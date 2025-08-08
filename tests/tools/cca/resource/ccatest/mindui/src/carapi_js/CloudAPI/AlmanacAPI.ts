// 黄历API接口定义
export interface AlmanacAPIRequest {
  /** 查询文本，例如：查询今天黄历、明天的黄历宜忌、七月十五黄历等 */
  refText: string;
  /** 黄历API服务器地址，必须从knowledgeSearchTool的schema中获取 */
  apiUrl: string;
}

export interface AlmanacAPIResponse {
  /** 请求是否成功 */
  success: boolean;
  /** 业务状态码，0表示成功 */
  code: number;
  /** 结果描述 */
  msg: string;
  /** 黄历数据主体 */
  data: {
    /** 语音播报URL */
    speakUrl?: string | null;
    /** 语音采样率 */
    ttsSampleRate?: number | null;
    /** 技能名称 */
    skill?: string | null;
    /** 请求ID */
    requestId?: string | null;
    /** 记录ID */
    recordId?: string | null;
    /** 会话ID */
    sessionId?: string | null;
    /** 技能ID */
    skillId?: string | null;
    /** 上下文ID */
    contextId?: string | null;
    /** 对话管理信息 */
    dm?: {
      /** 意图名称 */
      intentName?: string | null;
      /** 任务类型 */
      task?: string | null;
      /** 任务ID */
      taskId?: string | null;
      /** 意图ID */
      intentId?: string | null;
      /** 用户输入 */
      input?: string | null;
      /** 黄历描述 */
      nlg?: string | null;
      /** 状态码 */
      status?: number | null;
      /** 是否应结束会话 */
      shouldEndSession?: boolean | null;
      /** 上下文信息 */
      context?: {
        /** 语言类型 */
        nlgLanguageClass?: string | null;
        /** 当前意图名称 */
        currentIntentName?: string | null;
      } | null;
      /** 组件信息 */
      widget?: {
        /** 组件名称 */
        widgetName?: string | null;
        /** 错误码 */
        errorcode?: number | null;
        /** 组件类型 */
        type?: string | null;
        /** 名称 */
        name?: string | null;
        /** DUI组件类型 */
        duiWidget?: string | null;
        /** 品牌信息 */
        brand?: {
          /** 小尺寸logo */
          logoSmall?: string | null;
          /** 中尺寸logo */
          logoMiddle?: string | null;
          /** 大尺寸logo */
          logoLarge?: string | null;
          /** 显示名称 */
          showName?: string | null;
          /** 名称 */
          name?: string | null;
          /** 是否导出 */
          isexport?: string | null;
        } | null;
        /** 额外信息 */
        extra?: {
          /** 节日 */
          festival?: string | null;
          /** 凶神宜忌 */
          xsyj?: string | null;
          /** 二十八宿信息 */
          ebxx?: string | null;
          /** 忌命中数 */
          ji_hit?: number | null;
          /** 是否异常 */
          except?: boolean | null;
          /** 喜神财神福神位置 */
          cxfgod?: string | null;
          /** 星座 */
          constellation?: string | null;
          /** 宜做的事 */
          yi?: string | null;
          /** 忌做的事 */
          ji?: string | null;
          /** 节气 */
          jieqi?: string | null;
          /** 阳历日期 */
          date?: string | null;
          /** 数据源ID */
          sourceId?: number | null;
          /** 宜命中数 */
          yi_hit?: number | null;
          /** 阴历日期 */
          lunar_date?: string | null;
          /** 冲煞信息 */
          cs?: string | null;
          /** 数据源信息 */
          source?: {
            /** 数据源名称 */
            name?: string | null;
            /** 数据源logo */
            logo?: string | null;
          } | null;
          /** 天干地支 */
          tgdz?: string | null;
          /** 彭祖百忌 */
          pzbg?: string | null;
        } | null;
      } | null;
    } | null;
  };
}

// 黄历API接口
export interface IAlmanacAPI {
  /**
   * 获取黄历信息
   * @param request 黄历查询请求参数
   * @returns 黄历信息响应
   */
  getAlmanacInfo(request: AlmanacAPIRequest): Promise<AlmanacAPIResponse>;
}

// 黄历API请求参数接口
interface AlmanacRequest {
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
 * 发送HTTP请求获取黄历数据
 * @param refText 查询文本
 * @param apiUrl API服务器地址，必须从knowledgeSearchTool的schema中获取
 * @returns 黄历数据JSON
 */
async function fetchAlmanacData(refText: string, apiUrl: string): Promise<any> {
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
        console.log('[carapi-js-lib][INFO] httpGetter result', result);
        console.log('[carapi-js-lib][INFO] httpGetter result type', typeof result);
        
        if (!result) {
          throw new Error('黄历API请求失败: 返回结果为空');
        }
        
        // 处理双重JSON格式
        let finalData;
        
        if (typeof result === 'string') {
          console.log('[carapi-js-lib][INFO] 解析JSON字符串');
          
          // 首先尝试解析外层JSON
          const parsedResult = JSON.parse(result);
          console.log('[carapi-js-lib][INFO] 第一次解析结果:', parsedResult);
          
          // 检查是否包含body字段（新格式：{code:200, body:"json_string", headers:{}}）
          if (parsedResult && typeof parsedResult === 'object' && parsedResult.body && parsedResult.code === 200) {
            console.log('[carapi-js-lib][INFO] 检测到包含body的格式，解析body字段');
            // 第二次解析body字段中的JSON字符串，这里才是真正的黄历数据
            finalData = JSON.parse(parsedResult.body);
            console.log('[carapi-js-lib][INFO] 第二次解析body结果（最终数据）:', finalData);
          } else {
            // 如果没有body字段，说明是直接的API响应
            console.log('[carapi-js-lib][INFO] 直接使用第一次解析结果');
            finalData = parsedResult;
          }
        } else if (typeof result === 'object') {
          console.log('[carapi-js-lib][INFO] 直接返回对象');
          finalData = result;
        } else {
          throw new Error('黄历API返回数据类型不正确: ' + typeof result);
        }
        
        console.log('[carapi-js-lib][INFO] 最终解析的黄历数据:', finalData);
        
        // 确保返回的是最终的黄历数据（包含success、code、data字段的对象）
        if (finalData && typeof finalData === 'object' && finalData.hasOwnProperty('success')) {
          return finalData;
        } else {
          throw new Error('黄历API返回数据格式不正确，缺少success字段');
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
        throw new Error(`黄历API请求失败: HTTP ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('[carapi-js-lib][INFO] 云端API返回数据:', data);
      
      // 直接返回云端API的响应数据
      return data;
    }
  } catch (error) {
    console.error('[carapi-js-lib][ERROR] 黄历API请求失败:', error);
    throw error;
  }
}

// 函数重载声明
export function GetAlmanacInfo(request: AlmanacRequest): Promise<any>;
export function GetAlmanacInfo(refText: string, apiUrl: string): Promise<any>;

/**
 * GetAlmanacInfo - 获取黄历信息接口
 * 重要：apiUrl参数必须传入，应从knowledgeSearchTool的schema中获取
 * @param requestOrRefText 请求参数对象或查询文本
 * @param apiUrl 当第一个参数为string时，必须传入的API服务器地址
 * @returns Promise<黄历数据JSON>
 */
export async function GetAlmanacInfo(
  requestOrRefText: AlmanacRequest | string,
  apiUrl?: string
): Promise<any> {
  if (typeof requestOrRefText === 'string') {
    // 直接传查询文本: GetAlmanacInfo("查询今天黄历", "必须的API地址")
    if (!apiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchAlmanacData(requestOrRefText, apiUrl);
  } else {
    // 对象参数的方式: GetAlmanacInfo({refText: "查询今天黄历", apiUrl: "必须的API地址"})
    const { refText, apiUrl: requestApiUrl } = requestOrRefText;
    if (!requestApiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchAlmanacData(refText, requestApiUrl);
  }
} 