// 汇率API接口定义
export interface ExchangeRateAPIRequest {
  /** 查询文本，例如：查一下美元的汇率、欧元兑换人民币汇率、100美元等于多少人民币等 */
  refText: string;
  /** 汇率API服务器地址，必须从knowledgeSearchTool的schema中获取 */
  apiUrl: string;
}

export interface ExchangeRateAPIResponse {
  /** 请求是否成功 */
  success: boolean;
  /** 业务状态码，0表示成功 */
  code: number;
  /** 结果描述 */
  msg: string;
  /** 汇率数据主体 */
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
    /** TTS采样率 */
    ttsSampleRate?: number | null;
    /** 对话管理信息 */
    dm?: {
      /** 任务ID */
      taskId?: string | null;
      /** 意图ID */
      intentId?: string | null;
      /** 输入文本 */
      input?: string | null;
      /** 是否应该结束会话 */
      shouldEndSession?: boolean | null;
      /** 状态码 */
      status?: number | null;
      /** 汇率信息的自然语言描述 */
      nlg?: string | null;
      /** 意图名称 */
      intentName?: string | null;
      /** 任务类型 */
      task?: string | null;
      /** 组件信息 */
      widget?: {
        /** 汇率结果 */
        result?: string | null;
        /** DUI组件类型 */
        duiWidget?: string | null;
        /** 错误ID */
        errId?: number | null;
        /** 组件类型 */
        type?: string | null;
        /** 组件名称 */
        name?: string | null;
        /** 错误代码 */
        errorCode?: number | null;
        /** 组件名称 */
        widgetName?: string | null;
        /** 额外信息 */
        extra?: {
          /** 汇率日期 */
          date?: string | null;
          /** 源货币代码 */
          fromCode?: string | null;
          /** 汇率结果 */
          result?: string | null;
          /** 汇率时间 */
          time?: string | null;
          /** 目标货币名称 */
          to?: string | null;
          /** 源货币名称 */
          from?: string | null;
          /** 源货币数量 */
          fromNumber?: string | null;
          /** 目标货币代码 */
          toCode?: string | null;
        } | null;
      } | null;
      /** 上下文信息 */
      context?: {
        /** 当前意图名称 */
        currentIntentName?: string | null;
        /** 自然语言生成的语言类别 */
        nlgLanguageClass?: string | null;
      } | null;
    } | null;
  };
}

// 汇率API接口
export interface IExchangeRateAPI {
  /**
   * 获取汇率信息
   * @param request 汇率查询请求参数
   * @returns 汇率信息响应
   */
  getExchangeRateInfo(request: ExchangeRateAPIRequest): Promise<ExchangeRateAPIResponse>;
}

// 汇率API请求参数接口
interface ExchangeRateRequest {
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

/**
 * 发送HTTP请求获取汇率数据
 * @param refText 查询文本
 * @param apiUrl API服务器地址，必须从knowledgeSearchTool的schema中获取
 * @returns 汇率数据JSON
 */
async function fetchExchangeRateData(refText: string, apiUrl: string): Promise<any> {
  try {
    const encodedRefText = encodeURIComponent(refText);
    const url = `${apiUrl}?refText=${encodedRefText}`;
    
    const response = await fetch(url, {
      method: 'GET',
      headers: API_HEADERS
    });

    const jsonData = await response.json();
    
    if (!response.ok) {
      throw new Error(`HTTP错误: ${response.status} ${response.statusText}`);
    }

    return jsonData;
  } catch (error) {
    console.error('汇率API请求失败:', error);
    throw error;
  }
}

// 函数重载声明
export function GetExchangeRateInfo(request: ExchangeRateRequest): Promise<any>;
export function GetExchangeRateInfo(refText: string, apiUrl: string): Promise<any>;

/**
 * GetExchangeRateInfo - 获取汇率信息接口
 * 重要：apiUrl参数必须传入，应从knowledgeSearchTool的schema中获取
 * @param requestOrRefText 请求参数对象或查询文本
 * @param apiUrl 当第一个参数为string时，必须传入的API服务器地址
 * @returns Promise<汇率数据JSON>
 */
export async function GetExchangeRateInfo(
  requestOrRefText: ExchangeRateRequest | string,
  apiUrl?: string
): Promise<any> {
  if (typeof requestOrRefText === 'string') {
    // 直接传查询文本: GetExchangeRateInfo("查一下美元的汇率", "必须的API地址")
    if (!apiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchExchangeRateData(requestOrRefText, apiUrl);
  } else {
    // 对象参数的方式: GetExchangeRateInfo({refText: "查一下美元的汇率", apiUrl: "必须的API地址"})
    const { refText, apiUrl: requestApiUrl } = requestOrRefText;
    if (!requestApiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchExchangeRateData(refText, requestApiUrl);
  }
} 