import { getUnitFontSize, getValueFontSize, SingleFunctionUnit } from "./dynamicTemplates";
import { AsyncIncOrDecButton, AsyncValue, getDisplayValue, AsyncValue1 } from "./asyncComponents";
import type { carData } from "./dynamicTemplates";
// import "./dynamicTemplates.css";
import React, { useRef, useState } from "react";
import { HorizontalSelector } from "@/components/mindui/horizontal-selector";
import type { Option } from "@/components/mindui/horizontal-selector";
import { Separator } from "@/components/ui/separator";
// @ts-ignore
import { get_seat_massage_mode, registerListener, callbackManager, triggerGetForType } from "carapi-js-lib";

export function OneItemAdjustments({ data }: { data: carData }) {
    const step = data.adjustStep ?? 1;
    const [needsUnit, setNeedsUnit] = useState(true);
    const [value, setValue] = useState<number>(0);
    const isPlusLoading = useRef<boolean>(false);
    const isMinusLoading = useRef<boolean>(false);
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);
    const pendingVerificationRef = React.useRef<NodeJS.Timeout | null>(null);

    React.useEffect(() => {
        data.getFunc((value) => {
            console.log("async value in OneItemAdjustments result: ", value, "getType: ", data.getType);
            // if (isPlusLoading.current || isMinusLoading.current) return;
            setValue(Number(value));
        });
    }, [isMinusLoading.current, isPlusLoading.current]);
    return (
        <div className="flex flex-col items-center justify-end h-full gap-[185px]">
            {/* 上半部分：label、value、unit 竖直居中 */}
            <div className="flex flex-col items-center justify-center">
                <span className="text-[64px] font-semibold text-gray-600">{data.label}</span>
                <AsyncValue1 data={data} className="text-[210px] font-bold text-gray-900 !leading-[300px]" needsUnit={setNeedsUnit} value={value} onValueChange={setValue} />
                {needsUnit && <span className="text-7xl text-data-unit !leading-[1.4] mt-[-20px]">{data.unit}</span>}
            </div>
            {/* 下半部分：两个按钮 水平居中 间隔151px */}
            <div className="flex flex-row items-center justify-center gap-[151px] mb-[107px]">
                <AsyncIncOrDecButton
                    data={data}
                    isIncrease={true}
                    step={step}
                    style={{ width: "224px", height: "224px" }}
                    className="[&_svg]:h-[110px] [&_span]:h-[110px]"
                    value={value}
                    onValueChange={setValue}
                    onLoadingChange={(val) => {
                        isPlusLoading.current = val;
                    }}
                    pendingVerificationRef={pendingVerificationRef}
                />
                <AsyncIncOrDecButton
                    data={data}
                    isIncrease={false}
                    step={step}
                    style={{ width: "224px", height: "224px" }}
                    className="[&_svg]:h-[110px] [&_span]:h-[110px]"
                    value={value}
                    onValueChange={setValue}
                    onLoadingChange={(val) => {
                        isMinusLoading.current = val;
                    }}
                    pendingVerificationRef={pendingVerificationRef}
                />
            </div>
        </div>
    );
}

export function TwoItemAdjustments({ data, inList }: { data: carData, inList?: boolean }) {
    const step = data.adjustStep ?? 1;
    const [needsUnit, setNeedsUnit] = useState(true);
    const [value, setValue] = useState<number>(0);
    const isPlusLoading = useRef<boolean>(false);
    const isMinusLoading = useRef<boolean>(false);
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);
    const pendingVerificationRef = React.useRef<NodeJS.Timeout | null>(null);


    React.useEffect(() => {
        data.getFunc((value) => {
            console.log("async value in TwoItemAdjustments result: ", value, "getType: ", data.getType);
            // if (isPlusLoading.current || isMinusLoading.current) return;
            setValue(Number(value));
        });
    }, []);
    return (
        <SingleFunctionUnit variant={inList ? "inList" : "moreItems"} className={inList ? "bg-[#FFFFFF]/0 py-[60px]" : "p-[35px] !pb-[25px] !h-[510px]"}>
            {/* 第一行：label靠左 */}
            <div className="w-full text-left">
                <span className={`${!inList ? "text-[48px] font-semibold text-gray-600 leading-none" : "font-semibold text-gray-600 leading-none text-[36px]"}`}>{data.label}</span>
            </div>
            {/* 第二行：左侧value+unit baseline对齐，右侧两个按钮 */}
            <div className="flex w-full items-baseline justify-between">
                {/* 左侧：value+unit baseline对齐 */}
                <div className="flex items-baseline gap-[10px]">
                    <AsyncValue1 data={data} className={inList ? "text-[110px] font-bold text-gray-900 leading-none" : "text-[160px] font-bold text-gray-900 leading-[1.25]"} refreshFrequency={2000} needsUnit={setNeedsUnit} value={value} onValueChange={setValue} />
                    {needsUnit && <span className={inList ? "text-[51.29px] text-data-unit leading-none" : "text-7xl text-data-unit leading-[1.4]"}>{data.unit}</span>}
                </div>
                {/* 右侧：两个按钮，间隔45px */}
                <div className="flex gap-[45px]">
                    <AsyncIncOrDecButton
                        data={data}
                        isIncrease={true}
                        step={step}
                        style={{ width: "130px", height: "130px" }}
                        className="[&_svg]:h-[72px] [&_span]:h-[72px]"
                        value={value}
                        onValueChange={setValue}
                        onLoadingChange={(val) => {
                            isPlusLoading.current = val;
                        }}
                        pendingVerificationRef={pendingVerificationRef}
                    />
                    <AsyncIncOrDecButton
                        data={data}
                        isIncrease={false}
                        step={step}
                        style={{ width: "130px", height: "130px" }}
                        className="[&_svg]:h-[72px] [&_span]:h-[72px]"
                        value={value}
                        onValueChange={setValue}
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

export function MoreItemAdjustments({ data }: { data: carData }) {
    const step = data.adjustStep ?? 1;
    const valueFontSize = "text-[100px]"
    const unitFontSize = "text-[50.4px]"
    const [needsUnit, setNeedsUnit] = useState(true);
    const [value, setValue] = useState<number>(0);
    const isPlusLoading = useRef<boolean>(false);
    const isMinusLoading = useRef<boolean>(false);
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);
    const pendingVerificationRef = React.useRef<NodeJS.Timeout | null>(null);
    

    React.useEffect(() => {
        data.getFunc((value) => {
            console.log("async value in MoreItemAdjustments result: ", value, "getType: ", data.getType);
            if (isPlusLoading.current || isMinusLoading.current) {
                console.log("isPlusLoading :", isPlusLoading.current, "isMinusLoading :", isMinusLoading.current);
                return;
            }
            setValue(Number(value));
        });
    }, []);
    return (
        <div className="flex flex-col justify-between h-[510px] p-[30px] pt-[35px] bg-slate-50 rounded-[20px]">
            {/* 第一部分：label、value+unit */}
            <span className="font-semibold text-gray-600 leading-none text-[32px] mb-[59px]">{data.label}</span>
            <div className="flex items-baseline mb-[65px]">
                <AsyncValue1 data={data} className={`font-bold text-gray-900 leading-none ${valueFontSize}`} needsUnit={setNeedsUnit} value={value} onValueChange={setValue} />
                {needsUnit && <span className={`text-data-unit ${unitFontSize} ml-[15px]`}>{data.unit}</span>}
            </div>
            {/* 第二部分：两个按钮分列左右 */}
            <div className="flex w-full justify-between">
                <AsyncIncOrDecButton
                    data={data}
                    isIncrease={true}
                    step={step}
                    style={{ width: "130px", height: "130px" }}
                    className="[&_svg]:h-[72px] [&_span]:h-[72px]"
                    value={value}
                    onValueChange={setValue}
                    onLoadingChange={(val) => {
                        isPlusLoading.current = val;
                    }}
                    pendingVerificationRef={pendingVerificationRef}
                />
                <AsyncIncOrDecButton
                    data={data}
                    isIncrease={false}
                    step={step}
                    style={{ width: "130px", height: "130px" }}
                    className="[&_svg]:h-[72px] [&_span]:h-[72px]"
                    value={value}
                    onValueChange={setValue}
                    onLoadingChange={(val) => {
                        isPlusLoading.current = val;
                    }}
                    pendingVerificationRef={pendingVerificationRef}
                />
            </div>
        </div>
    );
}

export function makeMultiGearAdjustmentsRows(data: carData[], inList: boolean) {
    return data.map((item, index) => {
        return <MultiGearAdjustments data={item} inList={inList} />
    })
}

export function MultiLineAdjustments({ data, inList }: { data: carData, inList?: boolean }) {
    if (!data.valueMapping) return null;

    // 特殊处理座椅按摩模式调节
    let realMapping = data.valueMapping;
    const [massType, setMassType] = React.useState<number>(0);
    if (data.getType.includes("Mode_")) {
        let typeKey = "Type_" + data.getType.split("_")[1];
        let registerKey = "CreateAgent.CarControl.Massage.Status_" + data.getType.split("_")[1];
        get_seat_massage_mode(typeKey);
        registerListener("card", registerKey);
        callbackManager.addCallback(registerKey, (statusValue) => {
            let status = JSON.parse(statusValue);
            setMassType(Number(status.massType));
        });
    }
    
    // 根据 massType 过滤 valueMapping
    if (data.getType.includes("Mode_") && data.valueMapping) {
        let tmpMassType = massType == 0 ? 2 : massType;
        const filteredMapping = new Map<number, string>();
        
        data.valueMapping.forEach((value, key) => {
            // 根据 massType 过滤对应的键值对
            // massType=1: 保留 10X 的键值对，key只保留个位
            // massType=2: 保留 20X 的键值对，key只保留个位  
            // massType=3: 保留 30X 的键值对，key只保留个位
            
            const prefix = tmpMassType * 100;
            const suffix = key % 100;
            
            if (key >= prefix && key < prefix + 100) {
                // 只保留个位数作为新的key
                filteredMapping.set(suffix, value);
            }
        });
        
        realMapping = filteredMapping;
    }

    const options = Array.from(realMapping.entries()).map(([key, value]) => ({
        label: value,
        value: key
    }));
    const [selected, setSelected] = React.useState<number | string>(options[0]?.value ?? "");
    // 使用 useRef 来跟踪最新的请求ID，用于取消过期的请求
    const requestIdRef = React.useRef<number>(0);
    const pendingVerificationRef = React.useRef<NodeJS.Timeout | null>(null);
    const isLoading = useRef<boolean>(false);

    React.useEffect(() => {
        data.getFunc((value) => {
            console.log("async value in MultiLineAdjustments result: ", value, "getType: ", data.getType);
            setSelected(String(value));
        }); 
    }, []);

    // 每行最多3个
    const rows = [];
    for (let i = 0; i < options.length; i += 3) {
        const row = options.slice(i, i + 3);
        rows.push(row);
    }

    // 自定义按钮样式
    const baseBtn = "w-[255px] h-[120px] flex items-center justify-center rounded-[20px] cursor-pointer select-none text-[32px] transition-all duration-150 border-2 border-gray-200";
    const activeBtn = "bg-gray-950 text-white dark:text-[#222732]";
    const inactiveBtn = "bg-transparent text-gray-600";

    return (
        <div className={`flex flex-col items-start w-full ${inList ? "my-[60px]" : ""}`}>
            <span className="text-gray-600 leading-none text-[36px] mb-[50px] ">{data.label}</span>
            <div className="flex flex-wrap w-full">
                {options.map((opt, index) => (
                    <div key={opt.value} className={`${index % 3 !== 2 ? 'mr-[19px]' : ''} ${index >= 3 ? 'mt-[30px]' : ''}`}>
                        <div
                            className={
                                baseBtn +
                                (String(selected) === String(opt.value)
                                    ? " " + activeBtn
                                    : " " + inactiveBtn)
                            }
                            onClick={() => {
                                console.log("on click, label: ", data.label, "value: ", opt.value);
                                setSelected(opt.value);
                                isLoading.current = true;
                                // 设置请求ID，用于标识当前请求
                                const currentRequestId = ++requestIdRef.current;

                                if (data.setFunc) data.setFunc(Number(opt.value));

                                if (pendingVerificationRef.current) {
                                    clearTimeout(pendingVerificationRef.current);
                                }
                                
                                // 延迟验证设置结果
                                pendingVerificationRef.current = setTimeout(() => {
                                    // 检查是否还是最新的请求
                                    if (currentRequestId !== requestIdRef.current) {
                                        console.log('请求已过期，跳过验证');
                                        return;
                                    }
                                    
                                    triggerGetForType(data.getType);
                                    isLoading.current = false;
                                }, 2000);
                            }}
                        >
                            {opt.label}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

export function MultiGearAdjustments({ data, inList }: { data: carData, inList?: boolean }) {
    if (data.valueMapping && data.valueMapping.size >3) {
        return <MultiLineAdjustments data={data} inList={inList} />
    }
    let options: Option[] = [];
    if (data.valueMapping) {
        options = Array.from(data.valueMapping.entries()).map(([key, value]) => ({
            label: value,
            value: key.toString()
        }));
    }
    const [value, setValue] = React.useState<string>("");
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);
    const isLoading = useRef<boolean>(false);
    const pendingVerificationRef = React.useRef<NodeJS.Timeout | null>(null);
    const requestIdRef = React.useRef<number>(0);


    React.useEffect(() => {
        data.getFunc((value) => {
            console.log("async value in MultiGearAdjustments result: ", value, "getType: ", data.getType);
            setValue(String(value));
        });
    }, []);
    
    return <SingleFunctionUnit variant={"inList"} className={"bg-[#FFFFFF]/0 py-[60px]"}>
        <span className="font-semibold text-gray-600 leading-none text-[36px] ">{data.label}</span>
        <HorizontalSelector 
            size="lg" 
            color="primary"  
            options={options} 
            value={value} 
            onChange={(newValue) => {
                console.log("on change, label: ", data.label, "value: ", newValue);
                if (!data.setFunc) return;
                // 立即更新UI，提供即时反馈
                setValue(newValue);
                // 执行设置操作
                data.setFunc(Number(newValue));
                isLoading.current = true;
                const currentRequestId = ++requestIdRef.current;
                
                if (pendingVerificationRef.current) {
                    clearTimeout(pendingVerificationRef.current);
                }
                
                // 延迟验证设置结果
                pendingVerificationRef.current = setTimeout(() => {
                    // 检查是否还是最新的请求
                    if (currentRequestId !== requestIdRef.current) {
                        console.log('请求已过期，跳过验证');
                        return;
                    }
                    
                    triggerGetForType(data.getType);
                    isLoading.current = false;
                }, 2000);
            }}
        />
    </SingleFunctionUnit>
}
