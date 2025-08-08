import { getHttpDataAsync } from "carapi-js-lib";
import callbackManager from "../callbackManager.js";
import * as log from "../log.js";

// 理想同学API接口定义
export interface LixiangStudentAPIRequest {
  /** 查询文本，例如：今日热点新闻、理想汽车最新消息等 */
  text: string;
  /** VIN码，车辆识别码 */
  vin: string;
  /** 理想同学API服务器地址，必须从knowledgeSearchTool的schema中获取 */
  apiUrl: string;
}

export interface LixiangStudentAPIResponse {
  /** 请求是否成功 */
  success: boolean;
  /** 业务状态码，0表示成功 */
  code: number;
  /** 结果描述 */
  msg: string;
  /** 理想同学响应数据主体 */
  data: {
    /** 响应内容 */
    content?: string | null;
    /** 会话ID */
    sessionId?: string | null;
    /** 请求ID */
    requestId?: string | null;
    /** 其他扩展字段 */
    [key: string]: any;
  };
}

// 理想同学API接口
export interface ILixiangStudentAPI {
  /**
   * 获取理想同学信息
   * @param request 理想同学查询请求参数
   * @returns 理想同学信息响应
   */
  getLixiangStudentInfo(request: LixiangStudentAPIRequest): Promise<LixiangStudentAPIResponse>;
}

// 理想同学API请求参数接口
interface LixiangStudentRequest {
  text: string;
  vin: string;
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

// 保存第一个请求的时间戳和ID
// 移除时间窗口逻辑，但保留常量供模板层缓存使用
// 固定请求时间窗口（90秒）
const REQUEST_TIME_WINDOW = 15 * 1000;
// 请求超时时间（120秒）
const REQUEST_TIMEOUT = 120 * 1000;

// 导出时间窗口常量，供模板层使用
export const REQUEST_TIME_WINDOW_MS = REQUEST_TIME_WINDOW;

// 记录所有发送的请求ID，用于调试
const sentRequestIds: string[] = [];

// 获取所有已发送的请求ID，用于调试
export function getAllSentRequestIds(): string[] {
  return [...sentRequestIds];
}

/**
 * 发送HTTP请求获取理想同学数据 - 异步版本
 * @param text 查询文本
 * @param vin VIN码
 * @param apiUrl API服务器地址，必须从knowledgeSearchTool的schema中获取
 * @returns Promise<理想同学数据JSON>
 */
function fetchLixiangStudentDataAsync(
  text: string, 
  vin: string, 
  apiUrl: string
): Promise<any> {
  return new Promise((resolve, reject) => {
    try {
      const encodedText = encodeURIComponent(text);
      const encodedVin = encodeURIComponent(vin);
      const url = `${apiUrl}?text=${encodedText}&vin=${encodedVin}`;
      
      // 生成唯一的回调ID
      const callbackId = `lixiang_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      sentRequestIds.push(callbackId);
      
      log.i(`[LixiangStudentAPI] 发起新请求，ID: ${callbackId}, URL: ${url}`);
      
      // 注册回调
      const callback = (response: any) => {
        try {
          log.i(`[LixiangStudentAPI] 收到回调数据，当前请求ID: ${callbackId}`);
          
          // 打印响应数据类型和内容
          log.i(`[LixiangStudentAPI] 响应数据类型: ${typeof response}`);
          if (response === null || response === undefined) {
            log.e(`[LixiangStudentAPI] 警告：响应数据为空`);
          } else if (typeof response === 'object') {
            log.i(`[LixiangStudentAPI] 响应数据内容: ${JSON.stringify(response).substring(0, 200)}...`);
          } else if (typeof response === 'string') {
            log.i(`[LixiangStudentAPI] 响应数据内容: ${response.substring(0, 200)}...`);
          }
          
          // 处理响应数据
          let finalData;
          
          try {
            // 首先检查是否是 {code:200, body:"json_string"} 格式
            if (typeof response === 'object' && response !== null && response.code === 200 && response.body) {
              log.i('[LixiangStudentAPI] 检测到标准响应格式 {code:200, body:...}');
              
              // 解析body字段中的JSON字符串
              try {
                finalData = JSON.parse(response.body);
                log.i('[LixiangStudentAPI] body解析成功');
              } catch (e) {
                log.e(`[LixiangStudentAPI] body解析失败: ${e}, 使用原始字符串`);
                finalData = {
                  success: true,
                  code: 0,
                  msg: "解析body失败",
                  data: {
                    generateTextContent: {
                      display: response.body
                    }
                  }
                };
              }
            } else if (typeof response === 'string') {
              // 尝试解析字符串响应
              log.i('[LixiangStudentAPI] 解析字符串响应');
              
              try {
                const parsedResponse = JSON.parse(response);
                
                // 检查解析后的对象是否是 {code:200, body:...} 格式
                if (parsedResponse && parsedResponse.code === 200 && parsedResponse.body) {
                  log.i('[LixiangStudentAPI] 字符串响应解析为 {code:200, body:...} 格式');
                  
                  // 再次解析body字段
                  try {
                    finalData = JSON.parse(parsedResponse.body);
                    log.i('[LixiangStudentAPI] body解析成功');
                  } catch (e) {
                    log.e(`[LixiangStudentAPI] body解析失败: ${e}, 使用原始body字符串`);
                    finalData = {
                      success: true,
                      code: 0,
                      msg: "解析body失败",
                      data: {
                        generateTextContent: {
                          display: parsedResponse.body
                        }
                      }
                    };
                  }
                } else {
                  // 直接使用解析后的对象
                  log.i('[LixiangStudentAPI] 直接使用解析后的对象');
                  finalData = parsedResponse;
                }
              } catch (e) {
                log.e(`[LixiangStudentAPI] 字符串响应解析失败: ${e}, 使用原始字符串`);
                finalData = {
                  success: true,
                  code: 0,
                  msg: "解析响应失败",
                  data: {
                    generateTextContent: {
                      display: response
                    }
                  }
                };
              }
            } else if (typeof response === 'object') {
              // 直接使用对象响应
              log.i('[LixiangStudentAPI] 直接使用对象响应');
              finalData = response;
            } else {
              log.e(`[LixiangStudentAPI] 未知响应类型: ${typeof response}`);
              finalData = {
                success: true,
                code: 0,
                msg: "未知响应类型",
                data: {
                  generateTextContent: {
                    display: String(response)
                  }
                }
              };
            }
            
            // 确保finalData有一个有效的结构
            if (!finalData || typeof finalData !== 'object') {
              log.e('[LixiangStudentAPI] finalData无效，创建默认对象');
              finalData = {
                success: true,
                code: 0,
                msg: "响应数据无效",
                data: {
                  generateTextContent: {
                    display: "糟糕，数据丢失啦"
                  }
                }
              };
            }
            
            // 确保关键字段存在
            if (!finalData.success) finalData.success = true;
            if (!finalData.code && finalData.code !== 0) finalData.code = 0;
            if (!finalData.msg) finalData.msg = "请求成功";
            if (!finalData.data) {
              finalData.data = {
                generateTextContent: {
                  display: "糟糕，数据丢失啦"
                }
              };
            }
            
            log.i(`[LixiangStudentAPI] 最终解析的理想同学数据: ${JSON.stringify(finalData).substring(0, 200)}...`);
            resolve(finalData);
          } catch (parseError) {
            log.e(`[LixiangStudentAPI] 解析响应数据出错: ${parseError}`);
            // 创建一个基本的成功响应
            const fallbackData = {
              success: true,
              code: 0,
              msg: "解析响应数据出错",
              data: {
                generateTextContent: {
                  display: typeof response === 'string' ? response : "糟糕，数据丢失啦"
                }
              }
            };
            resolve(fallbackData);
          }
        } catch (error) {
          log.e(`[LixiangStudentAPI] 处理回调数据错误: ${error}`);
          reject(error);
        }
      };
      
      try {
        // 注册回调
        callbackManager.addHttpCallback(callbackId, callback);
        
        // 发起异步请求
        getHttpDataAsync(url, "", callbackId, callback);
        
        // 设置超时处理
        setTimeout(() => {
          // 移除时间窗口逻辑，不再忽略响应
          log.e('[LixiangStudentAPI] 请求超时:', callbackId);
          reject(new Error('理想同学API请求超时'));
        }, REQUEST_TIMEOUT); // 60秒超时
      } catch (callError) {
        log.e(`[LixiangStudentAPI] 调用API错误: ${callError}`);
        reject(callError);
      }
    } catch (error) {
      log.e(`[LixiangStudentAPI] 请求发起错误: ${error}`);
      reject(error);
    }
  });
}

/**
 * 发送HTTP请求获取理想同学数据 - 原同步版本，保留作为备用
 */
async function fetchLixiangStudentData(text: string, vin: string, apiUrl: string): Promise<any> {
  try {
    const encodedText = encodeURIComponent(text);
    const encodedVin = encodeURIComponent(vin);
    const url = `${apiUrl}?text=${encodedText}&vin=${encodedVin}`;
    
    // 判断是云端还是车端请求
    const isVehicleRequest = apiUrl.includes('crs-hmi');
    
    if (isVehicleRequest) {
      // 车端请求：使用widgetBridge
      log.i('[LixiangStudentAPI] 检测到车端API地址，使用widgetBridge请求');
      
      if (typeof window !== 'undefined' && window.widgetBridge && window.widgetBridge.httpGet) {
        const result = window.widgetBridge.httpGet(url, JSON.stringify(API_HEADERS));
        log.i('[LixiangStudentAPI] lixiang student httpGetter result', result);
        log.i('[LixiangStudentAPI] lixiang student httpGetter result type', typeof result);
        
        if (!result) {
          throw new Error('理想同学API请求失败: 返回结果为空');
        }
        
        // 处理双重JSON格式
        let finalData;
        
        if (typeof result === 'string') {
          log.i('[LixiangStudentAPI] 解析理想同学JSON字符串');
          
          // 首先尝试解析外层JSON
          const parsedResult = JSON.parse(result);
          log.i('[LixiangStudentAPI] 理想同学第一次解析结果:', parsedResult);
          
          // 检查是否包含body字段（新格式：{code:200, body:"json_string", headers:{}}）
          if (parsedResult && typeof parsedResult === 'object' && parsedResult.body && parsedResult.code === 200) {
            log.i('[LixiangStudentAPI] 检测到包含body的格式，解析body字段');
            // 第二次解析body字段中的JSON字符串，这里才是真正的理想同学数据
            finalData = JSON.parse(parsedResult.body);
            log.i('[LixiangStudentAPI] 理想同学第二次解析body结果（最终数据）:', finalData);
          } else {
            // 如果没有body字段，说明是直接的API响应
            log.i('[LixiangStudentAPI] 直接使用第一次解析结果');
            finalData = parsedResult;
          }
        } else if (typeof result === 'object') {
          log.i('[LixiangStudentAPI] 直接返回理想同学对象');
          finalData = result;
        } else {
          throw new Error('理想同学API返回数据类型不正确: ' + typeof result);
        }
        
        log.i('[LixiangStudentAPI] 最终解析的理想同学数据:', finalData);
        
        // 返回理想同学数据（可能包含success、code、data字段的对象，也可能是其他格式）
        return finalData;
      } else {
        throw new Error('当前环境不支持车机HTTP请求，请在车机环境中使用');
      }
    } else {
      // 云端请求：直接发起HTTP请求
      log.i('[LixiangStudentAPI] 检测到云端API地址，使用fetch请求');
      
      const response = await fetch(url, {
        method: 'GET',
        headers: API_HEADERS
      });
      
      if (!response.ok) {
        throw new Error(`理想同学API请求失败: HTTP ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      log.i('[LixiangStudentAPI] 云端API返回数据:', data);
      
      // 直接返回云端API的响应数据
      return data;
    }
  } catch (error) {
    log.e(`[LixiangStudentAPI] 理想同学API请求失败: ${error}`);
    throw error;
  }
}

// 重置请求时间窗口
export function resetRequestTimeWindow() {
  // 移除时间窗口逻辑，不再需要重置
  log.i('[LixiangStudentAPI] 移除时间窗口逻辑，不再需要重置');
}

// 函数重载声明
export function GetLixiangStudentInfo(request: LixiangStudentRequest): Promise<any>;
export function GetLixiangStudentInfo(text: string, vin: string, apiUrl: string): Promise<any>;

/**
 * GetLixiangStudentInfo - 获取理想同学信息接口
 * 重要：apiUrl参数必须传入，应从knowledgeSearchTool的schema中获取
 * @param requestOrText 请求参数对象或查询文本
 * @param vin 当第一个参数为string时，必须传入的VIN码
 * @param apiUrl 当第一个参数为string时，必须传入的API服务器地址
 * @returns Promise<理想同学数据JSON>
 */
export async function GetLixiangStudentInfo(
  requestOrText: LixiangStudentRequest | string,
  vin?: string,
  apiUrl?: string
): Promise<any> {
  try {
    if (typeof requestOrText === 'string') {
      // 直接传查询文本: GetLixiangStudentInfo("今日热点新闻", "WEB1b247b0f111111", "必须的API地址")
      if (!vin) {
        throw new Error('vin参数是必需的，请传入车辆VIN码');
      }
      if (!apiUrl) {
        throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
      }
      
      // 检测是否是车端环境，如果是则使用异步API
      const isVehicleRequest = apiUrl.includes('crs-hmi');
      if (isVehicleRequest) {
        return await fetchLixiangStudentDataAsync(requestOrText, vin, apiUrl);
      } else {
        return await fetchLixiangStudentData(requestOrText, vin, apiUrl);
      }
    } else {
      // 对象参数的方式: GetLixiangStudentInfo({text: "今日热点新闻", vin: "WEB1b247b0f111111", apiUrl: "必须的API地址"})
      const { text, vin: requestVin, apiUrl: requestApiUrl } = requestOrText;
      if (!requestVin) {
        throw new Error('vin参数是必需的，请传入车辆VIN码');
      }
      if (!requestApiUrl) {
        throw new Error('apiUrl参数是必需的，请从knowledgeSearchTool的schema中获取API地址');
      }
      
      // 检测是否是车端环境，如果是则使用异步API
      const isVehicleRequest = requestApiUrl.includes('crs-hmi');
      if (isVehicleRequest) {
        return await fetchLixiangStudentDataAsync(text, requestVin, requestApiUrl);
      } else {
        return await fetchLixiangStudentData(text, requestVin, requestApiUrl);
      }
    }
  } catch (error) {
    log.e(`[LixiangStudentAPI] GetLixiangStudentInfo错误: ${error}`);
    // 返回一个错误响应，触发UI显示错误
    return {
      success: false,
      code: -1,
      msg: `处理请求出错: ${error}`,
      data: {
        generateTextContent: {
          display: "糟糕，数据丢失啦"
        }
      }
    };
  }
} 

// getHttpDataAsync Demo
function getHttpDataAsyncDemo() {
  const callbackId = "lixiangStudentInfo";
  const callback = (response: any) => {
    console.log('[carapi-js-lib][INFO] lixiang student httpGetter result', response);
  }
  getHttpDataAsync("https://www.baidu.com", "", callbackId, callback);
}