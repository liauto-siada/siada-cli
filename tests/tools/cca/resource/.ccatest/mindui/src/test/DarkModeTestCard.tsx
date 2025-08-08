import React, { useState, useEffect } from 'react';
import { Sun, Moon, Monitor, Smartphone } from 'lucide-react';

const DarkModeTestCard = () => {
  const [isDark, setIsDark] = useState(false);
  const [systemPreference, setSystemPreference] = useState<'light' | 'dark' | 'no-preference'>('light');
  const [isAndroid, setIsAndroid] = useState(false);
  const [userAgent, setUserAgent] = useState('');

  // 检测系统颜色模式偏好
  useEffect(() => {
    // 检测用户代理字符串，判断是否为Android环境
    const ua = navigator.userAgent;
    setUserAgent(ua);
    setIsAndroid(/Android/i.test(ua));

    // 检测系统颜色模式偏好
    const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const lightModeQuery = window.matchMedia('(prefers-color-scheme: light)');

    const updateSystemPreference = () => {
      if (darkModeQuery.matches) {
        setSystemPreference('dark');
        setIsDark(true);
      } else if (lightModeQuery.matches) {
        setSystemPreference('light');
        setIsDark(false);
      } else {
        setSystemPreference('no-preference');
      }
    };

    // 初始化检测
    updateSystemPreference();

    // 监听系统颜色模式变化
    const handleChange = () => updateSystemPreference();
    darkModeQuery.addEventListener('change', handleChange);
    lightModeQuery.addEventListener('change', handleChange);

    return () => {
      darkModeQuery.removeEventListener('change', handleChange);
      lightModeQuery.removeEventListener('change', handleChange);
    };
  }, []);

  // 应用暗色模式到document
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  // 手动切换模式
  const toggleMode = () => {
    setIsDark(!isDark);
  };

  // 跟随系统模式
  const followSystem = () => {
    if (systemPreference === 'dark') {
      setIsDark(true);
    } else if (systemPreference === 'light') {
      setIsDark(false);
    }
  };

  return (
    <div className="w-full max-w-2xl mx-auto p-8 bg-white dark:bg-slate-900 rounded-2xl shadow-lg transition-all duration-300">
      {/* 标题 */}
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-gray-800 dark:text-white mb-2">
          Android 车机模式测试
        </h1>
        <p className="text-lg text-gray-600 dark:text-gray-300">
          白天/黑夜模式切换测试
        </p>
      </div>

      {/* 当前状态显示 */}
      <div className="bg-gray-50 dark:bg-slate-800 rounded-xl p-6 mb-8">
        <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-4 flex items-center gap-2">
          <Monitor className="w-6 h-6" />
          当前状态
        </h2>
        
        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-gray-700 dark:text-gray-300">当前模式:</span>
            <div className="flex items-center gap-2">
              {isDark ? (
                <>
                  <Moon className="w-5 h-5 text-blue-500" />
                  <span className="text-blue-500 font-medium">深色模式</span>
                </>
              ) : (
                <>
                  <Sun className="w-5 h-5 text-yellow-500" />
                  <span className="text-yellow-500 font-medium">浅色模式</span>
                </>
              )}
            </div>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-gray-700 dark:text-gray-300">系统偏好:</span>
            <span className="font-medium text-gray-800 dark:text-white">
              {systemPreference === 'dark' ? '深色' :
               systemPreference === 'light' ? '浅色' : '无偏好'}
            </span>
          </div>
          
          <div className="flex justify-between items-center">
            <span className="text-gray-700 dark:text-gray-300">运行环境:</span>
            <div className="flex items-center gap-2">
              <Smartphone className="w-5 h-5" />
              <span className="font-medium text-gray-800 dark:text-white">
                {isAndroid ? 'Android 车机' : '其他设备'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 控制按钮 */}
      <div className="space-y-4 mb-8">
        <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-4">
          模式控制
        </h2>
        
        <div className="flex flex-col gap-3">
          <button
            onClick={toggleMode}
            className="flex items-center justify-center gap-3 px-6 py-4 bg-blue-500 hover:bg-blue-600 text-white rounded-xl transition-colors duration-200 font-medium text-lg"
          >
            {isDark ? <Sun className="w-6 h-6" /> : <Moon className="w-6 h-6" />}
            切换到{isDark ? '浅色' : '深色'}模式
          </button>
          
          <button
            onClick={followSystem}
            className="flex items-center justify-center gap-3 px-6 py-4 bg-gray-500 hover:bg-gray-600 text-white rounded-xl transition-colors duration-200 font-medium text-lg"
          >
            <Monitor className="w-6 h-6" />
            跟随系统设置
          </button>
        </div>
      </div>

      {/* 测试色彩显示 */}
      <div className="space-y-4">
        <h2 className="text-2xl font-semibold text-gray-800 dark:text-white mb-4">
          色彩测试
        </h2>
        
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-red-100 dark:bg-red-900 p-4 rounded-lg text-center">
            <div className="w-8 h-8 bg-red-500 rounded-full mx-auto mb-2"></div>
            <span className="text-red-800 dark:text-red-200 font-medium">红色</span>
          </div>
          
          <div className="bg-green-100 dark:bg-green-900 p-4 rounded-lg text-center">
            <div className="w-8 h-8 bg-green-500 rounded-full mx-auto mb-2"></div>
            <span className="text-green-800 dark:text-green-200 font-medium">绿色</span>
          </div>
          
          <div className="bg-blue-100 dark:bg-blue-900 p-4 rounded-lg text-center">
            <div className="w-8 h-8 bg-blue-500 rounded-full mx-auto mb-2"></div>
            <span className="text-blue-800 dark:text-blue-200 font-medium">蓝色</span>
          </div>
          
          <div className="bg-yellow-100 dark:bg-yellow-900 p-4 rounded-lg text-center">
            <div className="w-8 h-8 bg-yellow-500 rounded-full mx-auto mb-2"></div>
            <span className="text-yellow-800 dark:text-yellow-200 font-medium">黄色</span>
          </div>
        </div>
      </div>

      {/* 设备信息 */}
      <div className="mt-8 p-4 bg-gray-50 dark:bg-slate-800 rounded-xl">
        <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">
          设备信息
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 break-all">
          UserAgent: {userAgent}
        </p>
      </div>
    </div>
  );
};

export default DarkModeTestCard; 