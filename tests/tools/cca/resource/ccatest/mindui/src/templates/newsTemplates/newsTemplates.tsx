import { useState, useEffect, useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from '@/components/ui/scroll-area'
import { GetLixiangStudentInfo, resetRequestTimeWindow, getAllSentRequestIds } from "../../carapi_js/CloudAPI/LixiangStudentAPI";
import { Markdown } from "../../components/mindui/markdown/markdown";
import * as log from "../../carapi_js/log.js";
import callbackManager from "../../carapi_js/callbackManager.js";

// 新闻数据接口
export interface NewsItem {
  id: string;
  title: string;
  content: string;
  category: string;
}


// 传入的数据接口
export interface NewsData {
  text: string; // 用户查询文本
  vin: string; // VIN码
  apiUrl: string; // API地址
}

// 新闻模板组件接口
export interface NewsTemplatesProps {
  data: NewsData; // 传入的数据对象
}

// 缓存数据接口
interface CacheData {
  timestamp: number;
  data: any;
  newsData?: NewsItem[];
  displayText?: string;
  useStructData: boolean;
}

// 缓存过期时间（15秒）
const CACHE_EXPIRY_TIME = 15 * 1000;

// 全局缓存对象
const responseCache: Record<string, CacheData> = {};

// 截断文本的函数
function truncateText(text: string, maxLength: number = 100): string {
  if (text.length <= maxLength) {
    return text;
  }
  return text.substring(0, maxLength) + '...';
}

// 新闻卡片组件
function NewsCardItem({ news }: { news: NewsItem }) {
  // const truncatedContent = truncateText(news.content, 45);
  return (
    <Card className="w-full border-0 shadow-none bg-transparent">
      <CardContent className="p-0">
        <div className="my-[68px] flex h-full w-[813px] flex-col">
          {/* 新闻标题 */}
          <div className="truncate text-5xl font-bold text-gray-900">
            {news.title}
          </div>
          
          {/* 新闻内容 */}
          <div className="mt-[25px] text-3xl text-gray-600">
            {/* {truncatedContent} */}
            {news.content}
          </div>
          
          {/* 标签 */}
          <div className="mt-[40px] flex flex-row items-center">
            <Badge variant="normal" color="weak" size="small">
              {news.category}
            </Badge>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}


// 新闻模板组件
export function NewsTemplates({ data }: NewsTemplatesProps) {
  const [newsData, setNewsData] = useState<NewsItem[]>([]);
  const [displayText, setDisplayText] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [useStructData, setUseStructData] = useState(false);
  
  // 跟踪请求状态
  const requestCountRef = useRef(0);
  
  // 添加渲染计数器
  const renderCountRef = useRef(0);
  renderCountRef.current += 1;
  
  console.log('[DEBUG] NewsTemplates渲染次数:', renderCountRef.current);
  console.log('[DEBUG] data对象详情:', JSON.stringify(data));
  console.log('[DEBUG] 当前时间:', new Date().toISOString());

  useEffect(() => {
    console.log('[DEBUG] useEffect触发 - 第', renderCountRef.current, '次渲染');
    console.log('[DEBUG] data详细信息:', {
      text: data.text,
      vin: data.vin,
      apiUrl: data.apiUrl
    });
    console.log('[DEBUG] 当前时间:', new Date().toISOString());
    
    // 如果是第一次渲染，重置请求时间窗口
    if (renderCountRef.current === 1) {
      resetRequestTimeWindow();
      // 重置回调处理状态
      if (callbackManager && callbackManager.resetCallbackState) {
        callbackManager.resetCallbackState();
        console.log('[DEBUG] 首次渲染，重置回调处理状态');
      }
      console.log('[DEBUG] 首次渲染，重置请求时间窗口');
    }
    
    // 生成缓存键
    const cacheKey = `news_${data.text}_${data.vin}_${data.apiUrl}`;
    console.log('[DEBUG] 缓存键:', cacheKey);
    
    // 检查缓存是否有效
    const cachedData = responseCache[cacheKey];
    const now = Date.now();
    
    if (cachedData && (now - cachedData.timestamp < CACHE_EXPIRY_TIME)) {
      console.log('[DEBUG] 使用缓存数据，缓存时间:', new Date(cachedData.timestamp).toISOString());
      console.log('[DEBUG] 缓存剩余有效期:', Math.round((CACHE_EXPIRY_TIME - (now - cachedData.timestamp)) / 1000), '秒');
      
      // 使用缓存数据
      if (cachedData.useStructData && cachedData.newsData) {
        setUseStructData(true);
        setNewsData(cachedData.newsData);
      } else if (cachedData.displayText) {
        setUseStructData(false);
        setDisplayText(cachedData.displayText);
      }
      
      setLoading(false);
      return; // 使用缓存数据，不再发起请求
    } else if (cachedData) {
      console.log('[DEBUG] 缓存已过期，重新请求数据');
      // 清除过期缓存
      delete responseCache[cacheKey];
    } else {
      console.log('[DEBUG] 无缓存数据，发起新请求');
    }
    
    // 增加请求计数
    const currentRequestCount = ++requestCountRef.current;
    console.log(`[DEBUG] 发起第 ${currentRequestCount} 个请求`);
    
    const fetchNewsData = async () => {
      try {
        console.log(`[DEBUG] 开始请求数据 (请求 #${currentRequestCount})`);
        setLoading(true);
        setError('');
        
        // 记录请求前的ID
        const beforeRequestIds = getAllSentRequestIds ? getAllSentRequestIds() : [];
        
        const response = await GetLixiangStudentInfo({
          text: data.text,
          vin: data.vin,
          apiUrl: data.apiUrl
        });
        
        // 记录请求后的ID，找出新增的ID
        const afterRequestIds = getAllSentRequestIds ? getAllSentRequestIds() : [];
        const newRequestIds = afterRequestIds.filter(id => !beforeRequestIds.includes(id));
        
        console.log(`[DEBUG] 接口调用完成 (请求 #${currentRequestCount})，response类型:`, typeof response);
        
        // 记录响应信息
        const responseInfo = typeof response === 'object' ? 
          JSON.stringify(response).substring(0, 200) + '...' : 
          String(response).substring(0, 200) + '...';
        
        handleResponse(response, cacheKey);
        
      } catch (err: any) {
        // 不再需要处理时间窗口内非第一个请求的错误，因为LixiangStudentAPI不再忽略响应
        console.error(`[DEBUG] 请求 #${currentRequestCount} 失败:`, err);
        setError('糟糕，数据丢失啦');
        setLoading(false);
        
        // 清除缓存
        delete responseCache[cacheKey];
        console.log('[DEBUG] 请求失败，清除缓存:', cacheKey);
      }
    };

    const handleResponse = (response: any, cacheKey: string) => {
      try {
        console.log('[DEBUG] 处理响应数据:', response);
        
        // 检查响应是否为空
        if (!response) {
          console.error('[DEBUG] 响应数据为空');
          setError('糟糕，数据丢失啦');
          setLoading(false);
          delete responseCache[cacheKey];
          return;
        }
        
        // 检查是否是特殊错误情况：body为空且存在error字段
        if ((response.body === "" || !response.body) && response.error) {
          console.error('[DEBUG] 检测到API错误:', response.error);
          setError('糟糕，数据丢失啦');
          setLoading(false);
          delete responseCache[cacheKey];
          return;
        }
        
        // 检查是否是 {code:200, body:"json_string"} 格式
        if (typeof response === 'object' && response.code === 200 && response.body) {
          console.log('[DEBUG] 检测到 {code:200, body:...} 格式的响应');
          
          try {
            // 解析body字段
            const parsedBody = JSON.parse(response.body);
            console.log('[DEBUG] body解析成功:', parsedBody);
            
            // 使用解析后的body作为实际响应
            response = parsedBody;
          } catch (e) {
            console.error('[DEBUG] body解析失败:', e);
            setError('糟糕，数据丢失啦');
            setLoading(false);
            delete responseCache[cacheKey];
            return;
          }
        }
        
        // 处理标准响应格式
        if (response.success && response.data) {
          // 检查是否是特殊错误情况：即使success为true，但存在error字段或code为负数
          if (response.error || (typeof response.code === 'number' && response.code < 0)) {
            console.error('[DEBUG] 检测到特殊错误情况:', response.error || `错误码 ${response.code}`);
            setError('糟糕，数据丢失啦');
            delete responseCache[cacheKey];
            return;
          }
          
          // 检查是否包含特定错误信息
          if (response.data.generateTextContent?.display === "未能获取有效数据" ||
              response.data.generateTextContent?.display === "获取数据过程中出现错误，请稍后再试。") {
            console.error('[DEBUG] 检测到错误提示信息');
            setError('糟糕，数据丢失啦');
            delete responseCache[cacheKey];
            return;
          }
          
          // 检查是否有struct_block_contents
          if (response.data.struct_block_contents && response.data.struct_block_contents.length > 0) {
            console.log('[DEBUG] 使用struct_block_contents解析成新闻卡片');
            // 使用struct_block_contents解析成新闻卡片
            try {
              const parsedNewsItems = parseStructBlockContents(response.data.struct_block_contents);
              
              // 更新状态
              setUseStructData(true);
              setNewsData(parsedNewsItems);
              
              // 更新缓存
              responseCache[cacheKey] = {
                timestamp: Date.now(),
                data: response,
                newsData: parsedNewsItems,
                useStructData: true
              };
              
              console.log('[DEBUG] 更新UI (结构化数据)');
            } catch (parseError) {
              console.error('[DEBUG] 解析struct_block_contents失败:', parseError);
              setError('糟糕，数据丢失啦');
              delete responseCache[cacheKey];
            }
          } else if (response.data.generateTextContent?.display) {
            console.log('[DEBUG] 使用generateTextContent.display显示文本内容');
            // 直接使用display字段的完整内容，用Markdown渲染
            const displayText = response.data.generateTextContent.display;
            
            // 清理特殊标签，保留markdown格式
            const cleanText = displayText
              .replace(/<\|br\|>/g, '\n')  // 将换行标签转换为换行符
              .trim();
            
            // 更新状态
            setUseStructData(false);
            setDisplayText(cleanText);
            
            // 更新缓存
            responseCache[cacheKey] = {
              timestamp: Date.now(),
              data: response,
              displayText: cleanText,
              useStructData: false
            };
            
            console.log('[DEBUG] 更新UI (文本数据)');
          } else {
            // 尝试从其他字段获取内容
            console.log('[DEBUG] 未找到标准内容字段，尝试从其他字段获取');
            
            let content = '';
            
            if (response.data.content) {
              content = response.data.content;
            } else if (typeof response.data === 'string') {
              content = response.data;
            } else if (response.msg) {
              content = response.msg;
            } else if (typeof response === 'string') {
              content = response;
            } else {
              content = '糟糕，数据丢失啦';
            }
            
            // 更新状态
            setUseStructData(false);
            setDisplayText(content);
            
            // 更新缓存
            responseCache[cacheKey] = {
              timestamp: Date.now(),
              data: response,
              displayText: content,
              useStructData: false
            };
            
            console.log('[DEBUG] 更新UI (其他字段内容)');
          }
        } else {
          // 处理非标准响应或错误响应
          console.log('[DEBUG] 非标准响应格式或错误响应，尝试提取有用信息');
          
          // 如果response.success明确为false，则设置错误状态
          if (response.success === false) {
            console.error('[DEBUG] 响应表明请求失败:', response.msg || '未知错误');
            setError('糟糕，数据丢失啦');
            delete responseCache[cacheKey];
            return;
          }
          
          let errorMsg = '';
          let content = '';
          
          if (response.msg) {
            errorMsg = response.msg;
          }
          
          if (typeof response === 'string') {
            content = response;
          } else if (typeof response === 'object') {
            content = JSON.stringify(response, null, 2);
          } else {
            content = String(response);
          }
          
          if (errorMsg) {
            setError('糟糕，数据丢失啦');
            delete responseCache[cacheKey];
          }
          
          // 更新状态
          setUseStructData(false);
          setDisplayText(content);
          
          // 更新缓存
          responseCache[cacheKey] = {
            timestamp: Date.now(),
            data: response,
            displayText: content,
            useStructData: false
          };
          
          console.log('[DEBUG] 更新UI (非标准响应)');
        }
      } catch (handleError) {
        console.error('[DEBUG] 处理响应数据出错:', handleError);
        setError('糟糕，数据丢失啦');
        delete responseCache[cacheKey];
      } finally {
        // 设置加载完成
        setLoading(false);
      }
    };

    fetchNewsData();
    
    // 清理函数
    return () => {
      // 组件卸载时的清理工作
    };
  }, [data]); // 依赖于data，当data变化时重新请求

  // 解析struct_block_contents
  const parseStructBlockContents = (blockContents: any[]): NewsItem[] => {
    try {
      const newsItems: NewsItem[] = [];
      let currentCategory = '新闻';

      blockContents.forEach((block: any) => {
        if (block.block_name === 'custom_card' && block.content) {
          try {
            const content = JSON.parse(block.content);
            const newsItem: NewsItem = {
              id: `news-${Date.now()}-${Math.random()}`,
              title: content.title || '未知标题',
              content: content.content || '未知内容',
              category: currentCategory
            };
            newsItems.push(newsItem);
          } catch (error) {
            console.error('解析内容失败:', error);
          }
        } else if (block.block_name === 'text_card') {
          // 更新当前分类
          currentCategory = block.content || block.spoken || '新闻';
        }
      });

      return newsItems;
    } catch (error) {
      console.error('解析struct_block_contents失败:', error);
      return [];
    }
  };

  // 渲染加载状态
  if (loading) {
    return (
      <div className="w-full h-[1050px] flex items-center justify-center">
        <div className="text-4xl text-gray-600">正在加载...</div>
      </div>
    );
  }

  // 渲染错误状态
  if (error) {
    return (
      <div className="w-full h-[1050px] flex flex-col items-center justify-center">
        <div className="text-4xl text-gray-600 mb-4">糟糕，数据丢失啦</div>
      </div>
    );
  }

  // 如果有struct_block_contents，显示新闻卡片
  if (useStructData && newsData.length > 0) {
    return (
      <div className="w-full h-[1050px] overflow-y-auto">
        <ScrollArea className="h-full w-full">
          {newsData.map((item, idx) => (
            <div key={item.id}>
              <NewsCardItem news={item} />
              {idx !== newsData.length - 1 && <Separator className="flex w-[813px] flex-col"/>}
            </div>
          ))}
        </ScrollArea>
      </div>
    );
  }

  // 如果没有struct_block_contents，使用Markdown显示display内容
  if (!useStructData && displayText) {
    return (
      <div className="w-full h-[1050px] flex flex-col">
        <ScrollArea className="h-full w-full">
          <div className="flex w-[813px] flex-col">
            <Markdown content={displayText} />
          </div>
        </ScrollArea>
      </div>
    );
  }

  // 如果没有数据
  return (
    <div className="w-full h-[1050px] flex flex-col items-center justify-center">
      <div className="text-4xl text-gray-600 mb-4">糟糕，数据丢失啦</div>
    </div>
  );
}


// 导出默认组件
export default NewsTemplates;