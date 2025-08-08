import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import SampleComponentCard from './comppreview/SampleComponentCard'
import { ScrollArea } from './components/ui/scroll-area'
import List from './templates/ListTemplates'
import IconComponentCard from './comppreview/IconComponentCard'

const App = () => {
  return (
    <div className="w-[933px] h-[1360px] bg-slate-200 rounded-[20px] py-[60px] relative">
      {/* 标题区域 */}
      <div className="px-[60px] mb-[100px]">
        <h1 className="text-[52px] leading-none font-bold text-gray-950">标题</h1>
      </div>

      {/* 内容区域 - 左右都保持60px边距，滚动条包含在右边距内 */}
      <div className="pl-[60px] pr-[30px]" style={{ height: 'calc(100% - 152px)' }}>
        <div className="relative h-full">
          <ScrollArea className="h-full w-full">
            <div className="pr-[35px]">
              {/* <FinancialNewsCard /> */}
              <IconComponentCard />
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
)