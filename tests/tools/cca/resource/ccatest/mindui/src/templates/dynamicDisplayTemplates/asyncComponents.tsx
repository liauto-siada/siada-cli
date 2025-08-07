import { Button, type ButtonProps } from "@/components/ui/button";
import React from "react";
import type { carData } from "./dynamicTemplates";
// @ts-ignore
import { getMeaningfulData } from "../../carapi_js/carApiGetter";
import { triggerGetForType } from "../../carapi_js/stateGetters";

import {
    AcSwitch,
    AirVolumn,
    CirculationInside,
    CirculationMode,
    AtmosphereLight,
    BackWindowHeating,
    Cold,
    CirculationOutside,
    Defrost,
    FrontWindshieldHeating,
    EcoSwitch,
    MirrorHeating,
    SeatVentilation,
    SeatHeating,
    ReadingLight,
    SeatMassage,
    SteeringwheelAuto,
    Fragrance,
    SteeringwheelHeating,
    WindFeet,
    WindFace,
    SyncSwitch,
    Switch,
    Plus,
    Minus,
    Car,
} from '@/components/icons/icons/index';

export const iconsMap = {
    AcSwitch: AcSwitch,
    EcoSwitch: EcoSwitch,
    SyncSwitch: SyncSwitch,
    AirVolumn: AirVolumn,
    CirculationInside: CirculationInside,
    CirculationMode: CirculationMode,
    AtmosphereLight: AtmosphereLight,
    BackWindowHeating: BackWindowHeating,
    Cold: Cold,
    CirculationOutside: CirculationOutside,
    Defrost: Defrost,
    FrontWindshieldHeating: FrontWindshieldHeating,
    MirrorHeating: MirrorHeating,
    SeatVentilation: SeatVentilation,
    SeatHeating: SeatHeating,
    ReadingLight: ReadingLight,
    SeatMassage: SeatMassage,
    SteeringwheelAuto: SteeringwheelAuto,
    Fragrance: Fragrance,
    SteeringwheelHeating: SteeringwheelHeating,
    WindFeet: WindFeet,
    WindFace: WindFace,
    Switch: Switch,
    Car: Car,
};

export interface AsyncIncOrDecProps extends ButtonProps {
    data: carData;
    isIncrease: boolean;
    step: number;
    value: number;
    onValueChange: (value: number) => void;
    onLoadingChange?: (loading: boolean) => void;
    pendingVerificationRef: React.RefObject<NodeJS.Timeout | null>;
}

function getNextValueFromMap(currentKey: string, mapping: Map<number, string>, isIncrease: boolean) {
    const keys = Array.from(mapping.keys());
    const idx = keys.indexOf(Number(currentKey));
    if (idx === -1) return 0; // 当前key不存在
    
    let nextIdx: number;
    if (isIncrease) {
        nextIdx = idx + 1;
        if (nextIdx >= keys.length) {
            return Number(currentKey); // 超出范围，返回原值
        }
    } else {
        nextIdx = idx - 1;
        if (nextIdx < 0) {
            return Number(currentKey); // 超出范围，返回原值
        }
    }
    
    const adjKey = keys[nextIdx];
    return Number(adjKey);
}

export function AsyncIncOrDecButton({ data, isIncrease, step, className, value, onValueChange, onLoadingChange, pendingVerificationRef, ...buttonProps }: AsyncIncOrDecProps) {
    // 使用 useRef 来跟踪最新的请求ID，用于取消过期的请求
    const requestIdRef = React.useRef<number>(0);

    return (
        <Button
            className={className}
            variant="secondary"
            {...buttonProps}
            icon={isIncrease ? <Plus /> : <Minus />}
            onClick={() => {
                console.log('onclick ', isIncrease ? "increase" : "decrease", " button,label: ", data.label);
                let nextValue: number;
                if (data.valueMapping) {
                    nextValue = getNextValueFromMap(String(value), data.valueMapping, isIncrease);
                    if (nextValue == value) {
                        return;
                    }
                } else {
                    nextValue = Number(value) + (isIncrease ? step : -step);
                }
                if (isNaN(nextValue)) {
                    console.log("nextValue is NaN, return");
                    return;
                }
                console.log("nextValue: ", nextValue, "value: ", value, "step: ", step, "isIncrease: ", isIncrease);
                if (!data.setFunc) return;
                if (data.valueRange) {
                    if ((data.valueRange.min !== undefined && nextValue < data.valueRange.min) || (data.valueRange.max !== undefined && nextValue > data.valueRange.max)) {
                        console.log("nextValue is out of range: ", nextValue);
                        return;
                    }
                }

                // 立即更新UI，提供即时反馈
                onValueChange(nextValue);
                
                // 通知上层开始loading
                onLoadingChange?.(true);
                
                // 设置请求ID，用于标识当前请求
                const currentRequestId = ++requestIdRef.current;
                
                // 执行设置操作
                data.setFunc(nextValue);
                
                // 清除之前的验证定时器
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
                    onLoadingChange?.(false);
                }, 2000);
            }}
        />
    );
}

export function getDisplayValue(data: carData, result: string) {
    let displayValue: string;
    if (data.valueMapping && data.setFunc) {
        displayValue = data.valueMapping.get(Number(result)) ?? "";
    } else if (data.getType) {
        displayValue = getMeaningfulData(data.getType, result);
        
    } else {
        displayValue = String(result);
    }
    return displayValue;
}

export function DisplayTimeValue(totalSeconds: number, className: string, unitClassName: string) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    
    if (isNaN(hours) || isNaN(minutes)) {
        return <span className={`${className} leading-none`}>{`--`}</span>;
    }
    return <div>
        <span className={`${className} leading-none`}>{`${hours}`}</span>
        <span className={`${unitClassName} leading-none m-[10px]`}>{`h`}</span>
        <span className={`${className} leading-none`}>{`${minutes}`}</span>
        <span className={`${unitClassName} leading-none ml-[10px]`}>{`min`}</span>
    </div>
}

export function AsyncValue({ data, className, refreshFrequency, needsUnit, modifyLabel, unitClassName }: { data: carData; className?: string, refreshFrequency?: number, needsUnit: (value: boolean) => void, modifyLabel?: (label: string) => void , unitClassName?: string}) {
    const [value, setValue] = React.useState<string>("--");
    const [shouldShowUnit, setShouldShowUnit] = React.useState<boolean>(true);
    const [currentLabel, setCurrentLabel] = React.useState<string>(data.label);
    // 由于模型能力不稳定，默认刷新频率为2秒
    let realRefreshFrequency = refreshFrequency ?? 2000

    if (value == "--") {
        needsUnit(false);
    }

    React.useEffect(() => {
        data.getFunc((result: any) => {
            console.log("async value in AsyncValue result: ", result, "getType: ", data.getType);
            let displayValue = getDisplayValue(data, result as string);
            let showUnit = true;
            let newLabel = data.label;
            
            if (isNaN(Number(displayValue))) {
                if (data.getType && ["CltcPureEvMileage", "WltcPureEvMileage", "CltcReevMileage", "WltcReevMileage"].includes(data.getType)) {
                    showUnit = true;
                    displayValue = String(result).replace(/KM$/i, '');
                } else if (data.getType && data.getType === "PowerPercent") {
                    showUnit = true;
                    displayValue = String(result).replace(/%$/i, '');
                } else {
                    showUnit = false;
                }
            }
            if (data.getType && data.getType === "DischargeStatus") {
                let current = Number(result);
                if (current < 0) {
                    newLabel = "充电"+data.label;
                } else {
                    newLabel = "放电"+data.label;
                }
                showUnit = true;
                displayValue = Math.abs(current).toString();
            }
            if (!isNaN(Number(displayValue))) {
                const numValue = Number(displayValue);
                // 如果是小数，保留一位小数；如果是整数，保持不变
                if (numValue % 1 !== 0) {
                    displayValue = numValue.toFixed(1);
                }
            }
            if (displayValue == null) {
                displayValue  = "--";
            }
            if (displayValue === "--") {
                showUnit = false;
            }
            if (data.getType === "RemainTime" || data.getType === "ChargeRemainTime" || data.getType === "ArrivalTime") {
                showUnit = false;
            }
            
            // 批量更新状态，避免多次渲染
            setValue(displayValue);
            setShouldShowUnit(showUnit);
            setCurrentLabel(newLabel);
            
            // 在状态更新后通知父组件
            needsUnit(showUnit);
            modifyLabel?.(newLabel);
        });
    }, []);

    if (value != "--") {
        if (data.getType === "ChargeRemainTime") {
            const totalMinutes = Number(value);
            if (totalMinutes === 65535) {
                return <span className={`${className} leading-none`}>{`未充电`}</span>;
            }
            return DisplayTimeValue(totalMinutes * 60, className ?? "", unitClassName ?? "");
        }
        if (data.getType === "RemainTime") {
            const totalSeconds = Number(value);
            if (totalSeconds === 0) {
                return <span className={`${className} leading-none`}>{`已到达`}</span>;
            }
            return DisplayTimeValue(totalSeconds, className ?? "", unitClassName ?? "");
        }
    }
    return <span className={`${className} leading-none`}>{value}</span>;
}


export function AsyncValue1({ data, className, refreshFrequency, needsUnit, value, onValueChange }: { data: carData; className?: string, refreshFrequency?: number, needsUnit: (value: boolean) => void, value: number, onValueChange: (value: number) => void }) {
    // 由于模型能力不稳定，默认刷新频率为2秒
    let realRefreshFrequency = refreshFrequency ?? 2000
    const [displayValue, setDisplayValue] = React.useState<string>("--");
    
    React.useEffect(() => {
        let interval: NodeJS.Timeout | undefined;
        async function updateDisplayValue() {
            // 每次重绘前刷新unit，避免之前没值后面有值导致unit不显示
            // 下面判断逻辑中只有false需要设置，true不需要单独设置
            let showUnit = true;
            let newDisplayValue = getDisplayValue(data, String(value));
            if (isNaN(Number(newDisplayValue))) {
                if (data.getType && ["CltcPureEvMileage", "WltcPureEvMileage", "CltcReevMileage", "WltcReevMileage"].includes(data.getType)) {
                    newDisplayValue = String(value).replace(/KM$/i, '');
                } else if (data.getType && data.getType === "PowerPercent") {
                    newDisplayValue = String(value).replace(/%$/i, '');
                } else {
                    showUnit = false;
                }
            }
            if (!isNaN(Number(newDisplayValue))) {
                const numValue = Number(newDisplayValue);
                // 如果是小数，保留一位小数；如果是整数，保持不变
                if (numValue % 1 !== 0) {
                    newDisplayValue = numValue.toFixed(1);
                }
            }
            if (newDisplayValue == null) {
                newDisplayValue = "--";
            }
            if (newDisplayValue === "--") {
                showUnit = false;
            }
            setDisplayValue(newDisplayValue);
            
            // 在状态更新后通知父组件
            needsUnit(showUnit);
        }
        updateDisplayValue();
    }, [value]);

    return <span className={`${className} leading-none`}>{displayValue}</span>;
}

export interface AsyncSwitchProps extends ButtonProps {
    data: carData;
    switchValue: boolean;
    onValueChange: (value: boolean) => void;
    onLoadingChange?: (loading: boolean) => void;
}

export function AsyncSwitch({ data, icon, className, switchValue, onValueChange, onLoadingChange, ...buttonProps }: AsyncSwitchProps) {
    const requestIdRef = React.useRef<number>(0);
    const pendingVerificationRef = React.useRef<NodeJS.Timeout | null>(null);
    let Comp = data.iconSrc ? iconsMap[data.iconSrc as keyof typeof iconsMap] : Switch

    return (
        <Button
            className={className}
            {...buttonProps}
            icon={<Comp />}
            isToggled={switchValue}
            onClick={() => {
                console.log("on click switch, label: ", data.label, "value before click: ", switchValue);
                const nextValue = !switchValue;
                
                // 立即更新UI，提供即时反馈
                onValueChange(nextValue);
                
                // 通知上层开始loading
                onLoadingChange?.(true);
                
                // 设置请求ID，用于标识当前请求
                const currentRequestId = ++requestIdRef.current;
                
                // 执行设置操作
                if (data.getType === "Door") {
                    data.setFunc && data.setFunc(nextValue ? 1 : 2);
                } else {
                    data.setFunc && data.setFunc(nextValue ? 1 : 0);
                }
                
                // 清除之前的验证定时器
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
                    onLoadingChange?.(false);
                }, 2000);
            }}
        >
        </Button>
    );
}

export function AsyncLabelShowToggled({ className, value }: { className: string, value: boolean }) {
    return <span className={`${className} ${value ? "text-blue-700" : "text-gray-400"}`}>{value ? "已开启" : "已关闭"}</span>;
}