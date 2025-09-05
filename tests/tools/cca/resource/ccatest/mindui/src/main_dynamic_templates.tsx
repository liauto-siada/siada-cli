import { StrictMode, useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { ScrollArea } from './components/ui/scroll-area'
import { DynamicTemplates } from './templates/dynamicDisplayTemplates/dynamicTemplates'
// @ts-ignore
import { get_seat_massage_control, callbackManager, get_front_hvac_system } from 'carapi-js-lib'

const App = () => {
    const [airConditionerState, setAirConditionerState] = useState(false);
    const [heaterState, setHeaterState] = useState(1);
    const [lightState, setLightState] = useState(1);
    const [windowState, setWindowState] = useState(0);
    const [doorState, setDoorState] = useState(0);
    const [airConditionerValue, setAirConditionerValue] = useState(20);
    const [speedValue, setSpeedValue] = useState(80);
    const [insideTemperatureValue, setInsideTemperatureValue] = useState(20);
    const [insideHumidityValue, setInsideHumidityValue] = useState(40);
    const [powerModeValue, setPowerModeValue] = useState(2);
    const [windDirectionValue, setWindDirectionValue] = useState(3);
    let temperatureValue = 20;
    let cardId = Symbol("座椅按摩")
    useEffect(() => {
      const handleBeforeUnload = (event: BeforeUnloadEvent) => {
        callbackManager.unregisterCardListener(cardId);
      };
      window.addEventListener('beforeunload', handleBeforeUnload);
      return () => {
        window.removeEventListener('beforeunload', handleBeforeUnload);
      };
    }, []);
  return (
    <div className="w-[933px] h-[1360px] bg-slate-200 rounded-[20px] py-[60px] relative">
      {/* 标题区域 */}
      <div className="px-[60px] mb-[138px]">
        <h1 className="text-[52px] font-bold text-gray-950 leading-none">标题</h1>
      </div>

      {/* 内容区域 */}
      <div className="flex-1 pl-[60px] pr-[20px] min-h-0">
        <ScrollArea className="h-full w-full pr-[40px]">
        <div className="h-[1049px]">
          <DynamicTemplates data={[
            {
                label: "动力模式",
                getFunc: (callback: (value: string) => void) => {
                    get_seat_massage_control(cardId, "Switch_FL", callback);
                },
                needAdjust: true,
                setFunc: (value: boolean | number) => {
                    setPowerModeValue(value as number);
                },
                adjustStep: 1,
                getType: "Switch_FL",
                valueMapping: new Map([
                    [0, "舒适"],
                    [1, "标准"],
                    [2, "运动"],
                    // [3, "高性能"],
                    // [4, "节能"],
                    // [5, "后排舒适"],
                ]),
            },
            {
              label: "前排吹风方向",
              getFunc: (callback: (value: string) => void) => {
                get_front_hvac_system("FrontAcWindDirection", callback)
              },
              needAdjust: true,
              setFunc: (value: boolean | number) => {
                  setWindDirectionValue(value as number);
              },
              adjustStep: 1,
              getType: "FrontAcWindDirection",
              valueMapping: new Map([
                  [1, "吹脸"],
                  [2, "吹脚&吹脸"],
                  [3, "吹脚"],
                  [4, "吹脚&除霜"],
                  [5, "除霜"],
                  [6, "吹脸&除霜"],
                  [7, "吹脸&吹脚&除霜"],
              ]),
          },
          //   {
          //       label: "空调温度",
          //       getFunc: (callback: (value: string) => void) => {
          //           callback(String(airConditionerValue))
          //       },
          //       needAdjust: true,
          //       setFunc: (value: boolean | number) => {
          //           setAirConditionerValue(value as number);
          //       },
          //       adjustStep: 1,
          //       unit: "℃",
          //   },
          //   {
          //       label: "车速",
          //       getFunc: (callback: (value: string) => void) => {
          //           callback(String(speedValue))
          //       },
          //       needAdjust: true,
          //       setFunc: (value: boolean | number) => {
          //           setSpeedValue(value as number);
          //       },
          //       adjustStep: 10,
          //       unit: "km/h",
          //   },
          //   {
          //       label: "车内温度",
          //       getFunc: (callback: (value: string) => void) => {
          //           callback(String(insideTemperatureValue))
          //       },
          //       setFunc: (value: boolean | number) => {
          //           setInsideTemperatureValue(value as number);
          //       },
          //       needAdjust: true,
          //       adjustStep: 1,
          //       unit: "℃",
          //   },
          //   {
          //       label: "车内湿度",
          //       getFunc: (callback: (value: string) => void) => {
          //           callback(String(insideHumidityValue))
          //       },
          //       setFunc: (value: boolean | number) => {
          //           setInsideHumidityValue(value as number);
          //       },
          //       needAdjust: true,
          //       adjustStep: 5,
          //       unit: "%",
          //   },
          //   {
          //     label: "车内湿度",
          //     getFunc: (callback: (value: string) => void) => {
          //       callback(String(insideHumidityValue))
          //     },
          //     setFunc: (value: boolean | number) => {
          //         setInsideHumidityValue(value as number);
          //     },
          //     needAdjust: true,
          //     adjustStep: 5,
          //     unit: "%",
          // },
            // controls:
            {
              label: "空调",
              getFunc: (callback: (value: string) => void) => {
                callback(String(airConditionerState))
              },
              needAdjust: false,
              setFunc: (value: boolean | number) => {
                setAirConditionerState(value as boolean);
              },
              iconSrc: "AcSwitch",
            },
            {
              label: "暖风",
              getFunc: (callback: (value: string) => void) => {
                callback(String(heaterState))
              },
              needAdjust: false,
              setFunc: (value: boolean | number) => {
                setHeaterState(value as number);
              },
              iconSrc: "EcoSwitch",
            },
            {
              label: "灯光",
              getFunc: (callback: (value: string) => void) => {
                callback(String(lightState))
              },
              needAdjust: false,
              setFunc: (value: boolean | number) => {
                setLightState(value as number);
              },
            },
            {
              label: "车窗",
              getFunc: (callback: (value: string) => void) => {
                callback(String(windowState))
              },
              needAdjust: false,
              setFunc: (value: boolean | number) => {
                setWindowState(value as number);
              },
              iconSrc: "Cold",
            },
            {
              label: "车门",
              getFunc: (callback: (value: string) => void) => {
                callback(String(doorState))
              },
              needAdjust: false,
              setFunc: (value: boolean | number) => {
                setDoorState(value as number);
              },
            },
            {
              label: "车窗",
              getFunc: (callback: (value: string) => void) => {
                callback(String(windowState))
              },
              needAdjust: false,
              setFunc: (value: boolean | number) => {
                setWindowState(value as number);
              },
              iconSrc: "Cold",
            },
            {
              label: "车门",
              getFunc: (callback: (value: string) => void) => {
                callback(String(doorState))
              },
              needAdjust: false,
              setFunc: (value: boolean | number) => {
                setDoorState(value as number);
              },
            },
            // displays:
            {
              label: "充电状态",
              iconSrc: "Switch",
              getFunc: (callback: (value: string) => void) => {
                callback(String(1))
              },
              getType: "ChargeStatus",
              needAdjust: false,
              valueMapping: new Map([
                [0, "无状态"],
                [1, "充电枪已连接"],
                [2, "电池预热"],
                [3, "充电中"],
                [4, "电池保温"],
                [5, "充电停止"],
                [6, "充电暂停"],
                [7, "充电错误"],
                [15, "充电枪拔出"],
                [16, "预约充电等待中"],
                [17, "充电完成"]
              ])
            },
            {
              label: "剩余导航时长",
              iconSrc: "Switch",
              getFunc: (callback: (value: string) => void) => {
                callback(String(94532))
              },
              getType: "RemainTime",
              needAdjust: false,
              unit: "分钟",
              refreshFrequency: 5000,
              valueMapping: new Map([
                [65535, "无效"]
              ])
            },
            {
              label: "剩余充电时长",
              iconSrc: "Switch",
              getFunc: (callback: (value: string) => void) => {
                callback(String(946))
              },
              getType: "ChargeRemainTime",
              needAdjust: false,
              unit: "分钟",
              refreshFrequency: 5000,
              valueMapping: new Map([
                [65535, "无效"]
              ])
            },
            {
              label: "二氧化碳浓度",
              getFunc: (callback: (value: string) => void) => {
                callback(String(-1))
              },
              needAdjust: false,
              iconSrc: "Defrost",
              getType: "AcAirCo2Value",
            },
            {
              label: "副驾按摩模式",
              getFunc: (callback: (value: string) => void) => {
                callback(String(402))
              },
              needAdjust: false,
              iconSrc: "Defrost",
              getType: "Mode_FR",
            },
            {
              label: "二排左按摩模式",
              getFunc: (callback: (value: string) => void) => {
                callback(String(101))
              },
              needAdjust: false,
              iconSrc: "Defrost",
              getType: "Mode_SecL",
            },
            {
              label: "二排右按摩模式",
              getFunc: (callback: (value: string) => void) => {
                callback(String(202))
              },
              needAdjust: false,
              iconSrc: "Defrost",
              getType: "Mode_SecR",
            },
            {
              label: "车内温度",
              getFunc: (callback: (value: string) => void) => {
                callback(String(temperatureValue++))
              },
              needAdjust: false,
              unit: "℃",
              iconSrc: "Defrost",
              getType: "AcAirCo2Value",
            },
            {
              label: "海拔高度",
              getType: "Altitude",
              getFunc: (callback: (value: string) => void) => {
                callback(String("22222222222222222"))
              },
              needAdjust: false,
              unit: "m",
              iconSrc: "AtmosphereLight",
            },
            {
              label: "后排温度",
              getFunc: (callback: (value: string) => void) => {
                callback(String(22))
              },
              getType: "RearTemp",
              needAdjust: false,
              unit: "℃",
              iconSrc: "Cold"
            },
            {
              label: "前排温度",
              getFunc: (callback: (value: string) => void) => {
                callback(String(22))
              },
              getType: "FrontTemp",
              needAdjust: false,
              unit: "℃",
              iconSrc: "AtmosphereLight",
            },
            {
              label: "后排温度",
              getFunc: (callback: (value: string) => void) => {
                callback(String(22))
              },
              getType: "RearTemp",
              needAdjust: false,
              unit: "℃",
              iconSrc: "AtmosphereLight",
            },
            {
              label: "风向设置",
              getFunc: (callback: (value: string) => void) => {
                callback(String(0))
              },
              getType: "ReadingLight_FL",
              needAdjust: false,
              iconSrc: "AtmosphereLight",
              unit: "℃",
            },
            {
              label: "前排温度",
              getFunc: (callback: (value: string) => void) => {
                callback(String(22))
              },
              needAdjust: false,
              unit: "℃",
              getType: "FrontTemp",
              iconSrc: "AtmosphereLight",
            },
            {
              label: "后排温度",
              getFunc: (callback: (value: string) => void) => {
                callback(String(22))
              },
              needAdjust: false,
              unit: "℃",
              getType: "RearTemp",
              iconSrc: "AtmosphereLight",
            },
            {
              label: "前排温度",
              getFunc: (callback: (value: string) => void) => {
                callback(String(22))
              },
              needAdjust: false,
              getType: "FrontTemp",
              unit: "℃",
            },
            {
              label: "后排温度",
              getFunc: (callback: (value: string) => void) => {
                callback(String(22))
              },
              getType: "RearTemp",
              needAdjust: false,
              unit: "℃",
            },
            {
              label: "车速",
              getFunc: (callback: (value: string) => void) => {
                callback(String(80))
              },
              getType: "Speed",
              needAdjust: false,
              unit: "km/h",
            },
            {
              label: "动力电池电流",
              iconSrc: "Switch",
              getFunc: (callback: (value: string) => void) => {
                callback(String(180))
              },
              getType: "DischargeStatus",
              needAdjust: false,
              unit: "A",
              refreshFrequency: 3000,
            },
          ]} />
          </div>
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