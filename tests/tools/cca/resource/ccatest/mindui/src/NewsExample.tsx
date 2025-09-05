import { StrictMode, useState, useMemo } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { NewsTemplates } from "./templates/newsTemplates/newsTemplates";
import { ScrollArea } from '@/components/ui/scroll-area'
import { GetLixiangStudentInfo } from "./carapi_js/CloudAPI/LixiangStudentAPI";

// 新闻卡片组件定义
const NewsCard = () => {
    const data = useMemo(() => ({
        text: "国际新闻",
        vin: "WEB1b247b0f111111",
        apiUrl: "https://crs-mindcloud-service-testtwo.inner.chj.cloud/api/v1/tool/lixiang/student/bidStreamingDialogue"
    }), []);

    return (
        <NewsTemplates 
            data={data}
        />
    );
};

export default NewsCard

// App应用
const App = () => {
  return (
    <div className="w-[933px] h-[1360px] bg-slate-200 rounded-[20px] py-[60px] relative">
      {/* 标题区域 */}
        <h1 className="px-[60px] text-[52px] leading-none font-bold text-gray-950 mb-[138px]">新闻卡片</h1>

      {/* 内容区域 */}
      <div className="pl-[60px] pr-[20px] h-[1050px]">
        <ScrollArea className="h-full w-full">
            <NewsCard />
        </ScrollArea>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
)