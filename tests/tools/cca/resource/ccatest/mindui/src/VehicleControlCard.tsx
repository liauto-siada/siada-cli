import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { DynamicTemplates } from './templates/dynamicDisplayTemplates/dynamicTemplates'

// 车控卡片组件定义
const VehicleControlCard = () => {
    const [airConditionerState, setAirConditionerState] = useState(false);
    const [heaterState, setHeaterState] = useState(false);
    const [lightState, setLightState] = useState(false);
    const [windowState, setWindowState] = useState(false);
    const [doorState, setDoorState] = useState(false);

    return (
        <DynamicTemplates data={[
            {
              label: "空调",
              getFunc: () => Promise.resolve(airConditionerState),
              needAdjust: false,
              setFunc: (value: boolean | number) => {
                setAirConditionerState(value as boolean);
              },
            },
            {
              label: "暖风",
              getFunc: () => Promise.resolve(heaterState),
              needAdjust: false,
              setFunc: (value: boolean | number) => {
                setHeaterState(value as boolean);
              },
            },
            // {
            //   label: "灯光",
            //   getFunc: () => Promise.resolve(lightState),
            //   needAdjust: false,
            //   setFunc: (value: boolean | number) => {
            //     setLightState(value as boolean);
            //   },
            // },
            // {
            //   label: "车窗",
            //   getFunc: () => Promise.resolve(windowState),
            //   needAdjust: false,
            //   setFunc: (value: boolean | number) => {
            //     setWindowState(value as boolean);
            //   },
            // },
            // {
            //   label: "车门",
            //   getFunc: () => Promise.resolve(doorState),
            //   needAdjust: false,
            //   setFunc: (value: boolean | number) => {
            //     setDoorState(value as boolean);
            //   },
            // },
            // {
            //   label: "车内温度",
            //   getFunc: () => Promise.resolve(20),
            //   needAdjust: false,
            //   unit: "℃",
            // },
            // {
            //   label: "车外温度",
            //   getFunc: () => Promise.resolve(30),
            //   needAdjust: false,
            //   unit: "℃",
            // },
            // {
            //   label: "后排温度",
            //   getFunc: () => Promise.resolve(22),
            //   needAdjust: false,
            //   unit: "℃",
            // },
            // {
            //   label: "前排温度",
            //   getFunc: () => Promise.resolve(22),
            //   needAdjust: false,
            //   unit: "℃",
            // },
            {
              label: "后排温度",
              getFunc: () => Promise.resolve(22),
              needAdjust: false,
              unit: "℃",
            },
            {
              label: "前排温度",
              getFunc: () => Promise.resolve(22),
              needAdjust: false,
              unit: "℃",
            },
            {
              label: "后排温度",
              getFunc: () => Promise.resolve(22),
              needAdjust: false,
              unit: "℃",
            },
            // {
            //   label: "前排温度",
            //   getFunc: () => Promise.resolve(22),
            //   needAdjust: false,
            //   unit: "℃",
            // },
            // {
            //   label: "后排温度",
            //   getFunc: () => Promise.resolve(22),
            //   needAdjust: false,
            //   unit: "℃",
            // },
            // {
            //   label: "前排温度",
            //   getFunc: () => Promise.resolve(22),
            //   needAdjust: false,
            //   unit: "℃",
            // }
          ]} />
    );
};

export default VehicleControlCard


// App应用
const App = () => {
  return (
    <div className="w-[933px] h-[1360px] bg-[#D5DDE7] rounded-[20px] py-[60px] relative">
      {/* 标题区域 */}
      <div className="px-[60px] mb-[100px]">
        <h1 className="text-6xl font-bold text-gray-800">车控卡片</h1>
      </div>

      {/* 内容区域 */}
      <div className="px-[30px]" style={{ height: 'calc(100% - 120px)' }}>
          <VehicleControlCard />
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
) 