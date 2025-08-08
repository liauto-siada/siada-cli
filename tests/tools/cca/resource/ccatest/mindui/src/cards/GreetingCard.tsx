import React from 'react'
import { Button } from "@/components/ui/button"
import { IconButton } from "@/components/ui/iconbutton"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from '@/components/ui/scroll-area'

import { DateTime } from 'luxon';

interface GreetingData {
  timeGreeting: string;
  dateGreeting: string;
  timeOfDay: string;
  currentTime: string;
  currentDate: string;
  timezone: string;
}

const GreetingCard = () => {
  const [greetingData, setGreetingData] = useState<GreetingData>({
    timeGreeting: "",
    dateGreeting: "",
    timeOfDay: "",
    currentTime: "",
    currentDate: "",
    timezone: ""
  });

  // 时间相关问候语库
  const timeGreetings = {
    morning: [
      "早安，今天也要元气满满哦！",
      "早上好，新的一天开始了！",
      "清晨好，愿您今天心情愉快！",
      "早安，阳光正好，出发吧！",
      "美好的早晨，祝您一天顺利！"
    ],
    noon: [
      "午安，午餐吃了吗？",
      "中午好，记得按时吃饭哦！",
      "午安时光，稍作休息吧！",
      "正午好，注意劳逸结合！",
      "中午好，保持活力！"
    ],
    afternoon: [
      "下午好，注意休息~",
      "午后时光，保持精神饱满！",
      "下午好，继续加油！",
      "下午时光，记得喝水哦！",
      "午后好，愿您工作顺利！"
    ],
    evening: [
      "晚上好，回家路上注意安全！",
      "夜幕降临，一路平安！",
      "晚安时光，小心驾驶！",
      "夜晚好，愿您安全到家！",
      "傍晚好，注意行车安全！"
    ]
  };

  // 日期相关问候语库
  const dateGreetings = {
    weekday: [
      "工作日加油！",
      "新的工作日，继续努力！",
      "工作日快乐，保持状态！",
      "工作日顺利，加油冲鸭！",
      "忙碌的工作日，要注意休息哦！"
    ],
    weekend: [
      "周末愉快！",
      "美好的周末时光！",
      "周末好，享受休闲时光！",
      "愉快的周末，放松一下吧！",
      "周末快乐，尽情享受！"
    ],
    holiday: [
      "节日快乐！",
      "美好的节日时光！",
      "节日愉快，享受假期！",
      "快乐的节日，放松心情！",
      "节日好，愿您开心快乐！"
    ]
  };

  // 获取随机问候语
  const getRandomGreeting = (greetingArray: string[]) => {
    return greetingArray[Math.floor(Math.random() * greetingArray.length)];
  };

  // 判断时间段
  const getTimeOfDay = (hour: number) => {
    if (hour >= 5 && hour < 11) return 'morning';
    if (hour >= 11 && hour < 14) return 'noon';
    if (hour >= 14 && hour < 18) return 'afternoon';
    return 'evening';
  };

  // 判断日期类型
  const getDateType = (date: DateTime) => {
    const dayOfWeek = date.weekday;
    // 简化的节假日判断（可根据实际需求扩展）
    const month = date.month;
    const day = date.day;

    // 简单的节假日判断
    if ((month === 1 && day === 1) || // 元旦
        (month === 5 && day === 1) || // 劳动节
        (month === 10 && day === 1) || // 国庆节
        (month === 12 && day === 25)) { // 圣诞节
      return 'holiday';
    }

    // 周末判断 (1-5为工作日，6-7为周末)
    if (dayOfWeek >= 6) {
      return 'weekend';
    }

    return 'weekday';
  };

  // 获取UTC偏移格式
  const getUTCOffset = (date: DateTime) => {
    const offset = date.offset;
    const hours = Math.abs(Math.floor(offset / 60));
    const sign = offset >= 0 ? '+' : '-';
    return `UTC${sign}${hours.toString().padStart(2, '0')}`;
  };

  useEffect(() => {
    const updateGreeting = () => {
      const now = DateTime.now();
      const hour = now.hour;
      const timeOfDay = getTimeOfDay(hour);
      const dateType = getDateType(now);

      const timeGreeting = getRandomGreeting(timeGreetings[timeOfDay]);
      const dateGreeting = getRandomGreeting(dateGreetings[dateType]);

      setGreetingData({
        timeGreeting,
        dateGreeting,
        timeOfDay,
        currentTime: now.toFormat('HH:mm:ss'),
        currentDate: now.toFormat('yyyy年MM月dd日 cccc'),
        timezone: getUTCOffset(now)
      });
    };

    // 初始更新
    updateGreeting();

    // 设置定时器，每秒更新，使用 setTimeout 对齐到整秒
    const scheduleNextUpdate = () => {
      const delay = 1000 - (Date.now() % 1000);
      setTimeout(() => {
        updateGreeting();
        scheduleNextUpdate();
      }, delay);
    };

    scheduleNextUpdate();
  }, []);

  // 根据时间段返回相应的图标和颜色
  const getTimeIcon = () => {
    switch (greetingData.timeOfDay) {
      case 'morning':
        return '🌅';
      case 'noon':
        return '☀️';
      case 'afternoon':
        return '🌤️';
      case 'evening':
        return '🌙';
      default:
        return '⏰';
    }
  };

  const getTimeColor = () => {
    switch (greetingData.timeOfDay) {
      case 'morning':
        return 'text-orange-700';
      case 'noon':
        return 'text-yellow-600';
      case 'afternoon':
        return 'text-blue-700';
      case 'evening':
        return 'text-indigo-700';
      default:
        return 'text-gray-600';
    }
  };

  return (
    <div className="w-[813px] p-0 rounded-[20px]">
      {/* 主问候区域 */}
      <div className="bg-slate-50 rounded-[20px] p-[50px] mb-[30px] flex flex-col items-start">
        <div className="text-6xl font-semibold text-gray-950 mb-[30px]">智能问候</div>

        {/* 时间图标和问候语 */}
        <div className="flex items-center mb-[40px]">
          <div className="text-8xl mr-[30px]">{getTimeIcon()}</div>
          <div className="flex flex-col">
            <div className={`text-5xl font-semibold ${getTimeColor()} mb-[10px]`}>
              {greetingData.timeGreeting}
            </div>
            <div className="text-4xl text-gray-600">
              {greetingData.dateGreeting}
            </div>
          </div>
        </div>
      </div>

      {/* 时间信息区域 */}
      <div className="bg-slate-50 rounded-[20px] p-[50px] flex flex-col items-start">
        <div className="text-6xl font-semibold text-gray-950 mb-[30px]">当前时间</div>

        <div className="flex items-center justify-between w-full">
          <div className="flex flex-col">
            <div className="text-7xl font-bold text-gray-900 mb-[10px]">
              {greetingData.currentTime}
            </div>
            <div className="text-4xl text-gray-600">
              {greetingData.currentDate}
            </div>
          </div>

          <div className="text-right">
            <div className="text-3xl text-gray-600 mb-[10px]">时区</div>
            <div className="text-4xl font-semibold text-gray-900">
              {greetingData.timezone}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GreetingCard;


import { StrictMode, useRef, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'

const App = () => {
  return (
    <div className="w-[933px] h-[1360px] bg-slate-200 rounded-[20px] py-[60px] relative">
      {/* 标题区域 */}
      <div className="px-[52px] mb-[100px]">
        <h1 className="text-8xl font-bold text-gray-800">智能问候</h1>
      </div>

      {/* 内容区域 - 左右都保持60px边距，滚动条包含在右边距内，底部保持50px安全距离 */}
      <div className="pl-[60px] pr-[30px] pb-[50px]" style={{ height: 'calc(100% - 120px)' }}>
        <div className="relative h-full">
          <ScrollArea className="h-full w-full">
            <div className="pr-[35px]">
              <GreetingCard />
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  )
}

const rootElement = document.getElementById('root')
if (rootElement) {
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>
  )
}