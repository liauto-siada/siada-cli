// 交通限行查询API接口定义
export interface TrafficRestrictionAPIRequest {
  /** 查询文本，例如：北京明天限行吗、上海今天限行、广州限行情况等 */
  refText: string;
  /** 交通限行查询API服务器地址，必须从knowledgeSearchTool的schema中获取 */
  apiUrl: string;
}

export interface TrafficRestrictionAPIResponse {
  /** 请求是否成功 */
  success: boolean;
  /** 业务状态码，0表示成功 */
  code: number;
  /** 结果描述 */
  msg: string;
  /** 交通限行数据主体 */
  data: {
    /** 请求ID */
    requestId?: string | null;
    /** 记录ID */
    recordId?: string | null;
    /** 会话ID */
    sessionId?: string | null;
    /** 技能ID */
    skillId?: string | null;
    /** 对话管理信息 */
    dm?: {
      /** 限行情况的自然语言描述 */
      nlg?: string | null;
      /** 意图名称 */
      intentName?: string | null;
      /** 任务类型 */
      task?: string | null;
      /** 任务ID */
      taskId?: string | null;
      /** 组件信息 */
      widget?: {
        /** 组件类型 */
        type?: string | null;
        /** 错误代码 */
        errorCode?: string | null;
        /** 组件名称 */
        name?: string | null;
        /** 额外信息 */
        extra?: {
          /** 查询城市 */
          bacCity?: string | null;
          /** 查询日期 */
          bacDate?: string | null;
          /** 限行详情文本 */
          text?: string | null;
          /** 是否限行，1表示限行，0表示不限行 */
          isRestricted?: string | null;
        } | null;
        /** 限行规则数量 */
        count?: number | null;
        /** 当前页码 */
        currentPage?: number | null;
        /** 上一页码 */
        lastCurrentPage?: number | null;
        /** 详细限行规则列表 */
        data?: Array<{
          /** 不受限行规则影响的车辆类型 */
          carException?: string | null;
          /** 限行区域 */
          area?: string | null;
          /** 违反限行规定的罚款金额和扣分情况 */
          fine?: string | null;
          /** 是否限行，1表示限行，0表示不限行 */
          isRestricted?: string | null;
          /** 限行尾号 */
          tailNos?: string | null;
          /** 限行时间段 */
          time?: string | null;
          /** 限行车辆类型 */
          carType?: string | null;
        }> | null;
        /** 组件名称 */
        widgetName?: string | null;
        /** DUI组件类型 */
        duiWidget?: string | null;
      } | null;
      /** 是否应该结束会话 */
      shouldEndSession?: boolean | null;
      /** 上下文信息 */
      context?: {
        /** 自然语言生成的语言类别 */
        nlgLanguageClass?: string | null;
        /** 当前意图名称 */
        currentIntentName?: string | null;
      } | null;
      /** 输入文本 */
      input?: string | null;
      /** 意图ID */
      intentId?: string | null;
      /** 状态码 */
      status?: number | null;
    } | null;
    /** 技能名称 */
    skill?: string | null;
    /** 语音播报URL */
    speakUrl?: string | null;
    /** TTS采样率 */
    ttsSampleRate?: number | null;
    /** 上下文ID */
    contextId?: string | null;
    /** 错误信息 */
    error?: object | null;
  };
}

// 交通限行查询API接口
export interface ITrafficRestrictionAPI {
  /**
   * 获取交通限行信息
   * @param request 交通限行查询请求参数
   * @returns 交通限行信息响应
   */
  getTrafficRestrictionInfo(request: TrafficRestrictionAPIRequest): Promise<TrafficRestrictionAPIResponse>;
}

// 交通限行查询API请求参数接口
interface TrafficRestrictionRequest {
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
 * 发送HTTP请求获取交通限行数据
 * @param refText 查询文本
 * @param apiUrl API服务器地址，必须从knowledgeSearchTool的schema中获取
 * @returns 交通限行数据JSON
 */
async function fetchTrafficRestrictionData(refText: string, apiUrl: string): Promise<any> {
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
    console.error('交通限行查询API请求失败:', error);
    throw error;
  }
}

// 函数重载声明
export function GetTrafficRestrictionInfo(request: TrafficRestrictionRequest): Promise<any>;
export function GetTrafficRestrictionInfo(refText: string, apiUrl: string): Promise<any>;

/**
 * GetTrafficRestrictionInfo - 获取交通限行信息接口
 * 重要：apiUrl参数必须传入，应从knowledgeSearchTool的schema中获取
 * @param requestOrRefText 请求参数对象或查询文本
 * @param apiUrl 当第一个参数为string时，必须传入的API服务器地址
 * @returns Promise<交通限行数据JSON>
 */
export async function GetTrafficRestrictionInfo(
  requestOrRefText: TrafficRestrictionRequest | string,
  apiUrl?: string
): Promise<any> {
  if (typeof requestOrRefText === 'string') {
    // 直接传查询文本: GetTrafficRestrictionInfo("北京明天限行吗", "必须的API地址")
    if (!apiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchTrafficRestrictionData(requestOrRefText, apiUrl);
  } else {
    // 对象参数的方式: GetTrafficRestrictionInfo({refText: "北京明天限行吗", apiUrl: "必须的API地址"})
    const { refText, apiUrl: requestApiUrl } = requestOrRefText;
    if (!requestApiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchTrafficRestrictionData(refText, requestApiUrl);
  }
} 