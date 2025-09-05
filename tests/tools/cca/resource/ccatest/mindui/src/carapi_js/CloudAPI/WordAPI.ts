// 单词查询API接口定义
export interface WordAPIRequest {
  /** 查询文本，例如：帮我生成苹果的单词 */
  vector: string;
  /** 返回结果数量，默认为1 */
  topK?: number;
  /** 单词查询API服务器地址，必须传入完整的API端点地址 */
  apiUrl: string;
}

export interface WordAPIResponse {
  /** 请求是否成功 */
  success: boolean;
  /** 业务状态码，0表示成功 */
  code: number;
  /** 返回消息 */
  msg: string;
  /** 返回的数据主体 */
  data: {
    /** 向量化数据结果 */
    vfsData: Array<{
      /** 单词文本内容 */
      text: string;
      /** 相似度分数 */
      score: number;
      /** 知识块ID */
      knowledgeChunkId: string;
      /** 距离值 */
      distance: number | null;
      /** 字段信息 */
      fields: {
        /** 业务扩展载荷 */
        bizExtraPayload?: string | null;
        /** 创建时间 */
        createTime?: string | null;
        /** 音标 */
        sound?: string | null;
        /** 翻译 */
        translation?: string | null;
        /** 文本内容 */
        TEXT?: string | null;
        /** 分类 */
        category?: string | null;
        /** 向量 */
        VECTOR?: string | null;
      };
      /** 业务扩展载荷对象 */
      bizExtraPayload?: {
        /** 例句列表 */
        exampleList?: Array<{
          /** 例句 */
          sample: string;
          /** 翻译 */
          translate: string;
        }> | null;
      } | null;
      /** 业务扩展ID */
      bizExtraId: string | null;
      /** 业务创建时间 */
      bizCreateTime: string | null;
    }>;
    /** 图形数据 */
    graphData: any[];
  };
}

// 单词查询API接口
export interface IWordAPI {
  /**
   * 获取单词信息
   * @param request 单词查询请求参数
   * @returns 单词信息响应
   */
  getWordInfo(request: WordAPIRequest): Promise<WordAPIResponse>;
}

// 单词查询API请求参数接口
interface WordRequest {
  vector: string;
  topK?: number;
  apiUrl: string;        // API服务器地址，必须传入
}

// 必需的请求头参数
const API_HEADERS = {
  "Content-Type": "application/json",
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
 * 发送HTTP请求获取单词数据
 * @param vector 查询文本
 * @param topK 返回结果数量
 * @param apiUrl API服务器地址，必须传入
 * @returns 单词数据JSON
 */
async function fetchWordData(vector: string, topK: number, apiUrl: string): Promise<any> {
  try {
    // 判断是云端还是车端请求
    const isVehicleRequest = apiUrl.includes('crs-hmi');
    
    if (isVehicleRequest) {
      // 车端请求：使用widgetBridge，将POST请求转换为GET请求
      console.log('[carapi-js-lib][INFO] 检测到车端API地址，使用widgetBridge请求');
      
      if (typeof window !== 'undefined' && window.widgetBridge && window.widgetBridge.httpGet) {
        // 将POST参数转换为GET查询参数
        const params = new URLSearchParams({
          nameSpace: "CCA",
          vector: vector,
          topK: topK.toString()
        });
        const url = `${apiUrl}?${params.toString()}`;
        
        const result = window.widgetBridge.httpGet(url, JSON.stringify(API_HEADERS));
        console.log('[carapi-js-lib][INFO] word httpGetter result', result);
        console.log('[carapi-js-lib][INFO] word httpGetter result type', typeof result);
        
        if (!result) {
          throw new Error('单词API请求失败: 返回结果为空');
        }
        
        // 处理双重JSON格式
        let finalData;
        
        if (typeof result === 'string') {
          console.log('[carapi-js-lib][INFO] 解析单词JSON字符串');
          
          // 首先尝试解析外层JSON
          const parsedResult = JSON.parse(result);
          console.log('[carapi-js-lib][INFO] 单词第一次解析结果:', parsedResult);
          
          // 检查是否包含body字段（新格式：{code:200, body:"json_string", headers:{}}）
          if (parsedResult && typeof parsedResult === 'object' && parsedResult.body && parsedResult.code === 200) {
            console.log('[carapi-js-lib][INFO] 检测到包含body的格式，解析body字段');
            // 第二次解析body字段中的JSON字符串，这里才是真正的单词数据
            finalData = JSON.parse(parsedResult.body);
            console.log('[carapi-js-lib][INFO] 单词第二次解析body结果（最终数据）:', finalData);
          } else {
            // 如果没有body字段，说明是直接的API响应
            console.log('[carapi-js-lib][INFO] 直接使用第一次解析结果');
            finalData = parsedResult;
          }
        } else if (typeof result === 'object') {
          console.log('[carapi-js-lib][INFO] 直接返回单词对象');
          finalData = result;
        } else {
          throw new Error('单词API返回数据类型不正确: ' + typeof result);
        }
        
        console.log('[carapi-js-lib][INFO] 最终解析的单词数据:', finalData);
        
        // 对于单词API，检查是否包含vfsData或data字段（向量搜索API通常返回这种格式）
        if (finalData && typeof finalData === 'object' && (finalData.hasOwnProperty('vfsData') || finalData.hasOwnProperty('data'))) {
          return finalData;
        } else {
          throw new Error('单词API返回数据格式不正确，缺少vfsData或data字段');
        }
      } else {
        throw new Error('当前环境不支持车机HTTP请求，请在车机环境中使用');
      }
    } else {
      // 云端请求：使用GET请求，将原POST参数转换为查询参数
      console.log('[carapi-js-lib][INFO] 检测到云端API地址，使用fetch GET请求');
      
      // 将原POST请求体参数转换为GET查询参数
      const params = new URLSearchParams({
        nameSpace: "CCA",
        vector: vector,
        topK: topK.toString()
        // 单词API的paramCondition原本为空对象，所以不需要额外参数
      });
      
      const url = `${apiUrl}?${params.toString()}`;
      console.log('[carapi-js-lib][INFO] 单词云端GET请求URL:', url);
      
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          ...API_HEADERS,
          // GET请求不需要Content-Type
        }
      });
      
      if (!response.ok) {
        throw new Error(`单词API请求失败: HTTP ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log('[carapi-js-lib][INFO] 云端API返回数据:', data);
      
      // 直接返回云端API的响应数据
      return data;
    }
  } catch (error) {
    console.error('[carapi-js-lib][ERROR] 单词API请求失败:', error);
    throw error;
  }
}

// 函数重载声明
export function GetWordInfo(request: WordRequest): Promise<any>;
export function GetWordInfo(vector: string, apiUrl: string, topK?: number): Promise<any>;

/**
 * GetWordInfo - 获取单词信息接口
 * 重要：apiUrl参数必须传入，应从wordQueryTool的schema中获取
 * @param requestOrVector 请求参数对象或查询文本
 * @param apiUrl 当第一个参数为string时，必须传入的API服务器地址
 * @param topK 返回结果数量，默认为1
 * @returns Promise<单词数据JSON>
 */
export async function GetWordInfo(
  requestOrVector: WordRequest | string,
  apiUrl?: string,
  topK: number = 1
): Promise<any> {
  if (typeof requestOrVector === 'string') {
    // 直接传查询文本: GetWordInfo("帮我生成苹果的单词", "必须的API地址", 2)
    if (!apiUrl) {
      throw new Error('apiUrl参数是必需的，请从wordQueryTool的schema中获取API地址');
    }
    return await fetchWordData(requestOrVector, topK, apiUrl);
  } else {
    // 对象参数的方式: GetWordInfo({vector: "帮我生成苹果的单词", apiUrl: "必须的API地址", topK: 2})
    const { vector, apiUrl: requestApiUrl, topK: requestTopK = 1 } = requestOrVector;
    if (!requestApiUrl) {
      throw new Error('apiUrl参数是必需的，请从wordQueryTool的schema中获取API地址');
    }
    return await fetchWordData(vector, requestTopK, requestApiUrl);
  }
} 