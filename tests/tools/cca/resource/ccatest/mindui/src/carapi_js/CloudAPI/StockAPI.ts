// 股票查询API接口定义
export interface StockAPIRequest {
  /** 查询文本，例如：查一下理想现在的股价、苹果股票最新行情、000001股票信息等 */
  refText: string;
  /** 股票查询API服务器地址，必须从knowledgeSearchTool的schema中获取 */
  apiUrl: string;
}

export interface StockAPIResponse {
  /** 请求是否成功 */
  success: boolean;
  /** 业务状态码，0表示成功 */
  code: number;
  /** 结果描述 */
  msg: string;
  /** 股票数据主体 */
  data: {
    /** 技能ID */
    skillId?: string | null;
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
      /** 股票信息描述 */
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
        /** 消息 */
        msg?: string | null;
        /** 内容数量 */
        count?: number | null;
        /** 名称 */
        name?: string | null;
        /** DUI组件类型 */
        duiWidget?: string | null;
        /** 组件名称 */
        widgetName?: string | null;
        /** 文本内容 */
        text?: string | null;
        /** 当前页码 */
        currentPage?: number | null;
        /** 上一页页码 */
        lastCurrentPage?: number | null;
        /** 错误码 */
        errorcode?: number | null;
        /** 产品ID */
        productId?: string | null;
        /** 记录ID */
        recordId?: string | null;
        /** 股票内容列表 */
        content?: Array<{
          /** 绝对变化 */
          absChange?: number | null;
          /** 交易时间 */
          tradeTimes?: string | null;
          /** 成交量 */
          volume?: string | null;
          /** 均价 */
          avg?: string | null;
          /** 开盘价 */
          open?: string | null;
          /** 换手率 */
          hsl?: string | null;
          /** 日期TTS */
          dateTts?: string | null;
          /** 涨跌百分比 */
          percentage?: string | null;
          /** 股票代码 */
          code?: string | null;
          /** 当前价格 */
          current?: string | null;
          /** 股票符号 */
          symbol?: string | null;
          /** 成交额 */
          amount?: string | null;
          /** 下跌百分比 */
          down_percentage?: number | null;
          /** 涨跌额 */
          change?: string | null;
          /** THS代码 */
          thscode?: string | null;
          /** 昨收价 */
          lastClose?: string | null;
          /** 股票名称 */
          name?: string | null;
          /** 日期 */
          beforedate?: string | null;
          /** 时间 */
          time?: string | null;
          /** 约成交量 */
          aboutVolume?: string | null;
          /** 最低价 */
          low?: string | null;
          /** 最高价 */
          high?: string | null;
          /** 涨跌数值 */
          change_num?: number | null;
          /** 约成交额 */
          aboutAmount?: string | null;
          /** 绝对百分比 */
          absPercentage?: number | null;
          /** 交易所 */
          exchange?: string | null;
          /** 收盘价 */
          close?: string | null;
          /** 涨跌百分比数值 */
          percentage_num?: number | null;
        }> | null;
        /** 额外信息 */
        extra?: {
          /** 绝对变化 */
          absChange?: number | null;
          /** 交易时间 */
          tradeTimes?: string | null;
          /** 成交量 */
          volume?: string | null;
          /** 均价 */
          avg?: string | null;
          /** 开盘价 */
          open?: string | null;
          /** 换手率 */
          hsl?: string | null;
          /** 日期TTS */
          dateTts?: string | null;
          /** 涨跌百分比 */
          percentage?: string | null;
          /** 股票代码 */
          code?: string | null;
          /** 当前价格 */
          current?: string | null;
          /** 股票符号 */
          symbol?: string | null;
          /** 成交额 */
          amount?: string | null;
          /** 下跌百分比 */
          down_percentage?: number | null;
          /** 涨跌额 */
          change?: string | null;
          /** THS代码 */
          thscode?: string | null;
          /** 昨收价 */
          lastClose?: string | null;
          /** 股票名称 */
          name?: string | null;
          /** 日期 */
          beforedate?: string | null;
          /** 时间 */
          time?: string | null;
          /** 约成交量 */
          aboutVolume?: string | null;
          /** 最低价 */
          low?: string | null;
          /** 最高价 */
          high?: string | null;
          /** 涨跌数值 */
          change_num?: number | null;
          /** 约成交额 */
          aboutAmount?: string | null;
          /** 绝对百分比 */
          absPercentage?: number | null;
          /** 交易所 */
          exchange?: string | null;
          /** 收盘价 */
          close?: string | null;
          /** 涨跌百分比数值 */
          percentage_num?: number | null;
        } | null;
      } | null;
    } | null;
  };
}

// 股票查询API接口
export interface IStockAPI {
  /**
   * 获取股票信息
   * @param request 股票查询请求参数
   * @returns 股票信息响应
   */
  getStockInfo(request: StockAPIRequest): Promise<StockAPIResponse>;
}

// 股票查询API请求参数接口
interface StockRequest {
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
 * 发送HTTP请求获取股票数据
 * @param refText 查询文本
 * @param apiUrl API服务器地址，必须从knowledgeSearchTool的schema中获取
 * @returns 股票数据JSON
 */
async function fetchStockData(refText: string, apiUrl: string): Promise<any> {
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
        console.log('[carapi-js-lib][INFO] stock httpGetter result', result);
        console.log('[carapi-js-lib][INFO] stock httpGetter result type', typeof result);
        
        if (!result) {
          throw new Error('股票API请求失败: 返回结果为空');
        }
        
        // 处理双重JSON格式
        let finalData;
        
        if (typeof result === 'string') {
          console.log('[carapi-js-lib][INFO] 解析股票JSON字符串');
          
          // 首先尝试解析外层JSON
          const parsedResult = JSON.parse(result);
          console.log('[carapi-js-lib][INFO] 股票第一次解析结果:', parsedResult);
          
          // 检查是否包含body字段（新格式：{code:200, body:"json_string", headers:{}}）
          if (parsedResult && typeof parsedResult === 'object' && parsedResult.body && parsedResult.code === 200) {
            console.log('[carapi-js-lib][INFO] 检测到包含body的格式，解析body字段');
            // 第二次解析body字段中的JSON字符串，这里才是真正的股票数据
            finalData = JSON.parse(parsedResult.body);
            console.log('[carapi-js-lib][INFO] 股票第二次解析body结果（最终数据）:', finalData);
          } else {
            // 如果没有body字段，说明是直接的API响应
            console.log('[carapi-js-lib][INFO] 直接使用第一次解析结果');
            finalData = parsedResult;
          }
        } else if (typeof result === 'object') {
          console.log('[carapi-js-lib][INFO] 直接返回股票对象');
          finalData = result;
        } else {
          throw new Error('股票API返回数据类型不正确: ' + typeof result);
        }
        
        console.log('[carapi-js-lib][INFO] 最终解析的股票数据:', finalData);
        
        // 确保返回的是最终的股票数据（包含success、code、data字段的对象）
        if (finalData && typeof finalData === 'object' && finalData.hasOwnProperty('success')) {
          return finalData;
        } else {
          throw new Error('股票API返回数据格式不正确，缺少success字段');
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
        throw new Error(`股票API请求失败: HTTP ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('[carapi-js-lib][INFO] 云端API返回数据:', data);
      
      // 直接返回云端API的响应数据
      return data;
    }
  } catch (error) {
    console.error('[carapi-js-lib][ERROR] 股票API请求失败:', error);
    throw error;
  }
}

// 函数重载声明
export function GetStockInfo(request: StockRequest): Promise<any>;
export function GetStockInfo(refText: string, apiUrl: string): Promise<any>;

/**
 * GetStockInfo - 获取股票信息接口
 * 重要：apiUrl参数必须传入，应从knowledgeSearchTool的schema中获取
 * @param requestOrRefText 请求参数对象或查询文本
 * @param apiUrl 当第一个参数为string时，必须传入的API服务器地址
 * @returns Promise<股票数据JSON>
 */
export async function GetStockInfo(
  requestOrRefText: StockRequest | string,
  apiUrl?: string
): Promise<any> {
  if (typeof requestOrRefText === 'string') {
    // 直接传查询文本: GetStockInfo("查一下理想现在的股价", "必须的API地址")
    if (!apiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchStockData(requestOrRefText, apiUrl);
  } else {
    // 对象参数的方式: GetStockInfo({refText: "查一下理想现在的股价", apiUrl: "必须的API地址"})
    const { refText, apiUrl: requestApiUrl } = requestOrRefText;
    if (!requestApiUrl) {
      throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
    }
    return await fetchStockData(refText, requestApiUrl);
  }
} 