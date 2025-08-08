import React, { useState, useRef } from "react";
import { AsyncIncOrDecButton } from "./asyncComponents";
// @ts-ignore
import { registerListener, set_front_hvac_system, set_rear_hvac_control, set_vehicle_refrigerator_control, get_front_hvac_system, get_rear_hvac_control, get_vehicle_refrigerator_status, callbackManager } from 'carapi-js-lib';
import type { carData } from "./dynamicTemplates";
import { SingleFunctionUnit } from "./dynamicTemplates";

const setMap = {
    "FrontAcWindAuto": (value: number) => set_front_hvac_system("CarControlTpuPlugin_FrontAcAutoFanLevel", value),
    "FrontAcWind": (value: number) => set_front_hvac_system("CarControlTpuPlugin_FrontAcManualFanLevel", value),
    "RearAcWindAuto": (value: number) => set_rear_hvac_control("CarControlTpuPlugin_RearAcAutoFanLevel", value),
    "RearAcWind": (value: number) => set_rear_hvac_control("CarControlTpuPlugin_RearAcManualFanLevel", value),
    "HotTmp": (value: number) => set_vehicle_refrigerator_control("CarExtDeviceTpuPlugin_FridgeTemp", value),
    "CoolTmp": (value: number) => set_vehicle_refrigerator_control("CarExtDeviceTpuPlugin_FridgeTemp", value),
}

const getMap = {
    "FrontAcWindAuto": (callback: (value: string) => void) => {
        get_front_hvac_system("card", "FrontAcWindAuto", callback)
    },
    "FrontAcWind": (callback: (value: string) => void) => {
        get_front_hvac_system("card", "FrontAcWind", callback)
    },
    "RearAcWindAuto": (callback: (value: string) => void) => {
        get_rear_hvac_control("card", "RearAcWindAuto", callback)
    },
    "RearAcWind": (callback: (value: string) => void) => {
        get_rear_hvac_control("card", "RearAcWind", callback)
    },
    "HotTmp": (callback: (value: string) => void) => {
        get_vehicle_refrigerator_status("card", "HotTmp", callback)
    },
    "CoolTmp": (callback: (value: string) => void) => {
        get_vehicle_refrigerator_status("card", "CoolTmp", callback)
    },
}

const rangeMap = {
    "FrontAcWindAuto": [1, 5],
    "FrontAcWind": [1, 9],
    "RearAcWindAuto": [1, 5],
    "RearAcWind": [1, 9],
    "CoolTmp": [0, 7],
    "HotTmp": [35, 50],
}

function setCarDataAndAdjustType(getType: string, firstShow: boolean, setAdjustType: (type: string) => void, setCarData: React.Dispatch<React.SetStateAction<carData>>) {
    switch (getType) {
        case "FrontAcWindAuto":
        case "FrontAcWind":
            // 默认显示手动风量
            if (firstShow) {
                setAdjustType("FrontAcWind");
                setCarData(prev => ({ ...prev, label: "前排风量", unit: "档" }));
                setCarData(prev => getCarDataFromAdjustType("FrontAcWind", prev));
            }
            const callBackFront = (val: any) => {
                console.log("callBackFront val: ", val);
                if (val == "1") {
                    setAdjustType("FrontAcWindAuto");
                    setCarData(prev => getCarDataFromAdjustType("FrontAcWindAuto", prev));
                } else if (val == "0") {
                    setAdjustType("FrontAcWind");
                    setCarData(prev => getCarDataFromAdjustType("FrontAcWind", prev));
                }
            }
            get_front_hvac_system("card", "FrontAcAuto", callBackFront);
            break;
        case "RearAcWindAuto":
        case "RearAcWind":
            if (firstShow) {
                setCarData(prev => ({ ...prev, label: "后排风量", unit: "档" }));
                // 默认显示手动风量
                setAdjustType("RearAcWind");
                setCarData(prev => getCarDataFromAdjustType("RearAcWind", prev));
            }
            const callBackRear = (val: any) => {
                if (val == "1") {
                    setAdjustType("RearAcWindAuto");
                    setCarData(prev => getCarDataFromAdjustType("RearAcWindAuto", prev));
                } else if (val == "0") {
                    setAdjustType("RearAcWind");
                    setCarData(prev => getCarDataFromAdjustType("RearAcWind", prev));
                }
            }
            get_rear_hvac_control("card", "RearAcAuto", callBackRear);
            break;
        case "HotTmp":
        case "CoolTmp":
            setCarData(prev => ({ ...prev, label: "冰箱温度", unit: "℃" }));
            const callBackFridge = (val: any) => {
                if (val === "1" || val === "0") {
                    setAdjustType("CoolTmp");
                    setCarData(prev => getCarDataFromAdjustType("CoolTmp", prev));
                } else if (val === "2") {
                    setAdjustType("HotTmp");
                    setCarData(prev => getCarDataFromAdjustType("HotTmp", prev));
                }
            }
            get_vehicle_refrigerator_status("card", "WorkMode", callBackFridge);
            break;
    }
}

export function OverRideDisplayAdjustOne({ getType }: { getType: string }) {
    const isPlusLoading = useRef<boolean>(false);
    const isMinusLoading = useRef<boolean>(false);
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);
    const pendingVerificationRef = React.useRef<NodeJS.Timeout | null>(null);
    const [value, setValue] = useState<string>("--");

    let [adjustType, setAdjustType] = useState<string>("");
    const [carData, setCarData] = useState<carData>({
        label: "",
        unit: "",
        needAdjust: true,
        adjustStep: 1,
        getFunc: () => {
            return Promise.resolve(0);
        },
    });

    React.useEffect(() => {
        setCarDataAndAdjustType(getType, adjustType === "", setAdjustType, setCarData);
    }, []);

    React.useEffect(() => {
        carData.getFunc((result: any) => {
            console.log("async in OverRideDisplayAdjustOne value result: ", result, "getType: ", getType);
            if (result === null) {
                setValue("--");
            } else {
                setValue(result);
            }
        });
        
        return () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
            }
        };
    }, [adjustType]);
    return (
        <div className="flex flex-col items-center justify-end h-full gap-[185px]">
            {/* 上半部分：label、value、unit 竖直居中 */}
            <div className="flex flex-col items-center justify-center">
                <span className="text-[64px] font-semibold text-gray-600">{carData.label}</span>
                <div className="text-[210px] font-bold text-gray-900 !leading-[300px]">
                    {value}
                </div>
                {value !== "--" && <span className="text-7xl text-data-unit !leading-[1.4] mt-[-20px]">{carData.unit}</span>}
            </div>
            {/* 下半部分：两个按钮 水平居中 间隔151px */}
            <div className="flex flex-row items-center justify-center gap-[151px] mb-[107px]">
                <AsyncIncOrDecButton
                    data={carData}
                    isIncrease={true}
                    step={1}
                    style={{ width: "224px", height: "224px" }}
                    className="[&_svg]:h-[110px] [&_span]:h-[110px]"
                    value={Number(value)}
                    onValueChange={(val) => {
                        setValue(String(val));
                    }}
                    onLoadingChange={(val) => {
                        isPlusLoading.current = val;
                    }}
                    pendingVerificationRef={pendingVerificationRef}
                />
                <AsyncIncOrDecButton
                    data={carData}
                    isIncrease={false}
                    step={1}
                    style={{ width: "224px", height: "224px" }}
                    className="[&_svg]:h-[110px] [&_span]:h-[110px]"
                    value={Number(value)}
                    onValueChange={(val) => {
                        setValue(String(val));
                    }}
                    onLoadingChange={(val) => {
                        isMinusLoading.current = val;
                    }}
                    pendingVerificationRef={pendingVerificationRef}
                />
            </div>
        </div>
    );
}

export function OverRideDisplayAdjustTwo({ getType, inList }: { getType: string, inList: boolean }) {
    const isPlusLoading = useRef<boolean>(false);
    const isMinusLoading = useRef<boolean>(false);
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);
    const pendingVerificationRef = React.useRef<NodeJS.Timeout | null>(null);
    const [value, setValue] = useState<string>("--");

    let [adjustType, setAdjustType] = useState<string>("");
    const [carData, setCarData] = useState<carData>({
        label: "",
        unit: "",
        needAdjust: true,
        adjustStep: 1,
        getFunc: () => {
            return Promise.resolve(0);
        },
    });

    React.useEffect(() => {
        setCarDataAndAdjustType(getType, adjustType === "", setAdjustType, setCarData);
    }, []);

    React.useEffect(() => {
        carData.getFunc((result: any) => {
            console.log("async in OverRideDisplayAdjustTwo value result: ", result, "getType: ", getType);
            if (result === null) {
                setValue("--");
            } else {
                setValue(result);
            }
        });
        return () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
            }
        };
    }, [adjustType]);
    return (
        <SingleFunctionUnit variant={inList ? "inList" : "moreItems"} className={inList ? "bg-[#FFFFFF]/0 py-[60px]" : "p-[35px] !pb-[25px] !h-[510px]"}>
            {/* 第一行：label靠左 */}
            <div className="w-full text-left">
                <span className={`${!inList ? "text-[48px] font-semibold text-gray-600 leading-none" : "font-semibold text-gray-600 leading-none text-[36px]"}`}>{carData.label}</span>
            </div>
            {/* 第二行：左侧value+unit baseline对齐，右侧两个按钮 */}
            <div className="flex w-full items-baseline justify-between">
                {/* 左侧：value+unit baseline对齐 */}
                <div className="flex items-baseline gap-[10px]">
                    <div className={inList ? "text-[110px] font-bold text-gray-900 leading-none" : "text-[160px] font-bold text-gray-900 leading-[1.25]"}>{value}</div>
                    {value !== "--" && <span className={inList ? "text-[51.29px] text-data-unit leading-none" : "text-7xl text-data-unit leading-[1.4]"}>{carData.unit}</span>}
                </div>
                {/* 右侧：两个按钮，间隔45px */}
                <div className="flex gap-[45px]">
                    <AsyncIncOrDecButton
                        data={carData}
                        isIncrease={true}
                        step={1}
                        style={{ width: "130px", height: "130px" }}
                        className="[&_svg]:h-[72px] [&_span]:h-[72px]"
                        value={Number(value)}
                        onValueChange={(val) => {
                            setValue(String(val));
                        }}
                        onLoadingChange={(val) => {
                            isPlusLoading.current = val;
                        }}
                        pendingVerificationRef={pendingVerificationRef}
                    />
                    <AsyncIncOrDecButton
                        data={carData}
                        isIncrease={false}
                        step={1}
                        style={{ width: "130px", height: "130px" }}
                        className="[&_svg]:h-[72px] [&_span]:h-[72px]"
                        value={Number(value)}
                        onValueChange={(val) => {
                            setValue(String(val));
                        }}
                        onLoadingChange={(val) => {
                            isMinusLoading.current = val;
                        }}
                        pendingVerificationRef={pendingVerificationRef}
                    />
                </div>
            </div>
        </SingleFunctionUnit>
    );
}

export function OverRideDisplayAdjustMore({ getType }: { getType: string }) {
    const isPlusLoading = useRef<boolean>(false);
    const isMinusLoading = useRef<boolean>(false);
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);
    const pendingVerificationRef = React.useRef<NodeJS.Timeout | null>(null);
    const [value, setValue] = useState<string>("--");

    let [adjustType, setAdjustType] = useState<string>("");
    const [carData, setCarData] = useState<carData>({
        label: "",
        unit: "",
        needAdjust: true,
        adjustStep: 1,
        getFunc: () => {
            return Promise.resolve(0);
        },
    });

    React.useEffect(() => {
        setCarDataAndAdjustType(getType, adjustType === "", setAdjustType, setCarData);
    }, []);

    React.useEffect(() => {
        carData.getFunc((result: any) => {
            console.log("async in OverRideDisplayAdjustMore value result: ", result, "getType: ", getType);
            if (result === null) {
                setValue("--");
            } else {
                setValue(result);
            }
        });
    }, [adjustType]);
    return (
        <div className="flex flex-col justify-between h-[510px] p-[30px] pt-[35px] bg-slate-50 rounded-[20px]">
            {/* 第一部分：label、value+unit */}
            <span className="font-semibold text-gray-600 leading-none text-[32px] mb-[59px]">{carData.label}</span>
            <div className="flex items-baseline mb-[65px]">
            <div className="flex items-baseline gap-[10px]">
                    <div className="font-bold text-gray-900 leading-none text-[100px]">{value}</div>
                    {value !== "--" && <span className="text-data-unit ml-[15px] text-[50.4px]">{carData.unit}</span>}
                </div>
            </div>
            {/* 第二部分：两个按钮分列左右 */}
            <div className="flex w-full justify-between">
                <AsyncIncOrDecButton
                    data={carData}
                    isIncrease={true}
                    step={1}
                    style={{ width: "130px", height: "130px" }}
                    className="[&_svg]:h-[72px] [&_span]:h-[72px]"
                    value={Number(value)}
                    onValueChange={(val) => {
                        setValue(String(val));
                    }}
                    onLoadingChange={(val) => {
                        isPlusLoading.current = val;
                    }}
                    pendingVerificationRef={pendingVerificationRef}
                />
                <AsyncIncOrDecButton
                    data={carData}
                    isIncrease={false}
                    step={1}
                    style={{ width: "130px", height: "130px" }}
                    className="[&_svg]:h-[72px] [&_span]:h-[72px]"
                    value={Number(value)}
                    onValueChange={(val) => {
                        setValue(String(val));
                    }}
                    onLoadingChange={(val) => {
                        isMinusLoading.current = val;
                    }}
                    pendingVerificationRef={pendingVerificationRef}
                />
            </div>
        </div>
    );
}

function getCarDataFromAdjustType(adjustType: string, originCarData: carData) {
    let carData = originCarData;
    carData.setFunc = (setMap as any)[adjustType];
    carData.getFunc = (getMap as any)[adjustType];
    const range = (rangeMap as any)[adjustType];
    carData.valueRange = { min: range[0], max: range[1] };
    return carData;
}