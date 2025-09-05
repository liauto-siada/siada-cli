import React, { useState, useRef } from "react";
import { cn } from "../../lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
// import "./dynamicTemplates.css";
import { BaseList, ListWithFlexChildren } from "../lists/baseLists";
import {
    OneItemAdjustments,
    TwoItemAdjustments,
    MoreItemAdjustments,
    makeMultiGearAdjustmentsRows
} from "./adjustments";
import { AsyncSwitch, AsyncValue } from "./asyncComponents";
import { MoreButtonControl, OneButtonControl, TwoButtonControl } from "./buttonControls";
import { MoreDisplay, OneDisplay, TwoDisplay, makeDisplayInList, getRealUnit } from "./displays";
import { OverRideDisplayAdjustOne, OverRideDisplayAdjustTwo, OverRideDisplayAdjustMore } from "./specialItems";

export interface carData {
    label: string;
    iconSrc?: string;
    setFunc?: (value: boolean | number) => void;
    getFunc: (callback: (value: string) => void) => void;
    getType?: string;
    needAdjust: boolean;
    adjustStep?: number;
    unit?: string;
    refreshFrequency?: number; // 显示类刷新频率，单位毫秒
    // valueMapping和valueRange只能存在一个，如果都存在，优先使用valueMapping
    valueMapping?: Map<number, string>;
    valueRange?: {
        min?: number; // 如果为空，则不限制最小值
        max?: number; // 如果为空，则不限制最大值
    };
}

function renderSpecialType(
    getType: string, 
    frontAcExist: boolean, 
    rearAcExist: boolean, 
    fridgeExist: boolean,
    setFrontAcExist: (value: boolean) => void,
    setRearAcExist: (value: boolean) => void,
    setFridgeExist: (value: boolean) => void,
    Component: React.ComponentType<any>,
    inList: boolean = false
) {
    if (getType === "FrontAcWindAuto" || getType === "FrontAcWind") {
        if (!frontAcExist) {
            setFrontAcExist(true);
            return inList ? <Component getType={getType} inList={inList} /> : <Component getType={getType} />;
        } else {
            return <div/>;
        }
    } else if (getType === "RearAcWindAuto" || getType === "RearAcWind") {
        if (!rearAcExist) {
            setRearAcExist(true);
            return inList ? <Component getType={getType} inList={inList} /> : <Component getType={getType} />;
        } else {
            return <div/>;
        }
    } else if (getType === "HotTmp" || getType === "CoolTmp") {
        if (!fridgeExist) {
            setFridgeExist(true);
            return inList ? <Component getType={getType} inList={inList} /> : <Component getType={getType} />;
        } else {
            return <div/>;
        }
    }
    return null;
}

function classifyData(data: carData[]) {
    const dataMap = new Map<string, carData[]>();
    let controls: carData[] = [];
    let displays: carData[] = [];
    let adjusts: carData[] = [];
    let multiGearAdjusts: carData[] = [];

    data.forEach(item => {
        if (!item.setFunc) {
            displays.push(item);
        } else if (item.needAdjust && item.valueMapping && !item.label.includes("风量") && !Array.from(item.valueMapping.entries()).toString().includes("档")) {
            // 按摩强度不显示关闭项
            let tmpItem = item;
            if (item.getType.includes("Strength_")) {
                tmpItem.valueMapping.delete(0);
            }
            // 枚举类的调整项使用横向选择器，风量和档位具有连续调节能力，仍旧使用格子
            multiGearAdjusts.push(tmpItem);
        } else if (item.needAdjust) {
            adjusts.push(item);
        } else {
            controls.push(item);
        }
    });
    if (adjusts.length > 0) {
        dataMap.set("adjusts", adjusts);
    }
    if (controls.length > 0) {
        dataMap.set("controls", controls);
    }
    if (displays.length > 0) {
        dataMap.set("displays", displays);
    }
    if (multiGearAdjusts.length > 0) {
        dataMap.set("multiGearAdjusts", multiGearAdjusts);
    }
    return dataMap;
}

export function DynamicTemplates({ data }: { data: carData[] }) {
    let classifiedData = classifyData(data);
    if (classifiedData.size == 1) {
        return SingleTypeTemplates(classifiedData.keys().next().value!, classifiedData.values().next().value!, false);
    } else {
        return <BaseList children={makeListChildren(classifiedData)} />
    }
}

function makeAdjustmentsRows(data: carData[]) {
    let frontAcExist = false;
    let rearAcExist = false;
    let fridgeExist = false;
    return data.map((item, index) => {
        const specialResult = renderSpecialType(item.getType!, frontAcExist, rearAcExist, fridgeExist, 
            (value: boolean) => { frontAcExist = value; },
            (value: boolean) => { rearAcExist = value; },
            (value: boolean) => { fridgeExist = value; },
            OverRideDisplayAdjustTwo,
            true
        );
        if (specialResult) {
            return specialResult;
        }
        return <TwoItemAdjustments inList={true} data={item} />
    })
}

function makeListChildren(map: Map<string, carData[]>) {
    const [needsUnit, setNeedsUnit] = useState({ value: true });
    let rows: React.ReactElement[] = [];
    map.forEach((value, key) => {
        switch (key) {
            case "adjusts":
                rows = rows.concat(makeAdjustmentsRows(value));
                break;
            case "multiGearAdjusts":
                rows = rows.concat(makeMultiGearAdjustmentsRows(value, true));
                break;
            case "controls":
                rows = rows.concat(makeButtonRows(value));
                break;
            case "displays":
                const hasLaterViews = map.get("multiGearAdjusts") != undefined;
                if (value.length == 1) {
                    const [label, setLabel] = useState(value[0].label);
                    rows.push(
                        <div className="flex flex-col h-[350px] w-full gap-[30px] justify-between items-start px-[20px]">
                            <span className="text-[36px] text-gray-600 mt-[60px] font-semibold"> {label} </span>
                            <div className="flex flex-row items-baseline justify-center mb-[46px]">
                                <AsyncValue data={value[0]} className="text-[110px] text-gray-900 font-bold leading-none" refreshFrequency={2000} needsUnit={(value: boolean) => setNeedsUnit({ value })} modifyLabel={setLabel} unitClassName="text-[51.29px] text-data-unit" />
                                {needsUnit.value && <span className="text-[51.29px] text-data-unit ml-[30px]"> {getRealUnit(value[0].getType!) ?? value[0].unit} </span>}
                            </div>
                        </div>
                    )
                } else {
                    rows.push(<div>
                        <div className="font-semibold text-4xl text-gray-600 mt-[64px]">
                            车辆信息
                        </div>
                        <div className={`flex flex-col w-full justify-between items-start ${hasLaterViews ? "mt-[30px] mb-[60px]" : "mt-[30px]"}`}>
                            {placeChildren(makeDisplayInList(value), true)}
                        </div>
                    </div>);
                }
                break;
            default:
                break;
        }
    });
    return rows;
}

function makeButtonRows(data: carData[]) {
    const rows: React.ReactElement[] = [];
    let modifiedData = data.map(item => {
        if (item.iconSrc) {
            if (item.iconSrc === "SyncSwitch" && item.label.toLocaleLowerCase().includes("sync")) {
                item.iconSrc = "";
            } else if (item.iconSrc === "EcoSwitch" && item.label.toLocaleLowerCase().includes("eco")) {
                item.iconSrc = "";
            } else if (item.iconSrc === "AcSwitch" && item.label.toLocaleLowerCase().includes("a/c")) {
                item.iconSrc = "";
            }
        }
        return item;
    });
    let threeInALines: carData[] = [];
    let twoInALines: carData[] = [];
    // 文字太长的两个一行，其余的三个一行
    for (let i = 0; i < modifiedData.length; i += 1) {
        if (!modifiedData[i].iconSrc || modifiedData[i].iconSrc === "") {
            threeInALines.push(modifiedData[i]);
        } else if (modifiedData[i].label.length > 3) {
            twoInALines.push(modifiedData[i]);
        } else {
            threeInALines.push(modifiedData[i]);
        }
    }
    const groups: carData[][] = [];
    for (let i = 0; i < threeInALines.length; i += 3) {
        groups.push(threeInALines.slice(i, i + 3));
    }
    if (groups.length > 0 && groups[groups.length - 1].length === 1 && twoInALines.length > 0) {
        groups[groups.length - 1].push(twoInALines[0]);
        twoInALines.shift();
    }
    for (let i = 0; i < twoInALines.length; i += 2) {
        groups.push(twoInALines.slice(i, i + 2));
    }
    groups.forEach((group, idx) => {
        
        // 动态宽度
        rows.push(
            <div key={idx} className="h-[351px] flex flex-col justify-between">
                <div className="font-semibold text-4xl text-gray-600 mt-[64px]">
                    车辆控制
                </div>
                <div
                    className="flex justify-between items-center w-full h-full"
                >
                    {group.map((item, idx) => {
                        let modifiedItem = item;
                        
                        return (
                            <ButtonRowItem
                                key={item.label + idx}
                                data={modifiedItem}
                                width={group.length < 3 ? "386px" : "255px"}
                            />
                        );
                    })}
                </div>
            </div>
        );
    });
    return rows;
}

// 新增的组件，用于处理单个按钮的状态管理
function ButtonRowItem({ data, width }: { data: carData, width: string }) {
    const [value, setValue] = React.useState<boolean>(false);
    const isLoading = useRef<boolean>(false);
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);

    React.useEffect(() => {
        data.getFunc((result: any) => {
            setValue(Number(result) === 1);
            console.log("async in ButtonRowItem switch result: ", result, "getType: ", data.getType, "value: ", value);
        });
    }, []);

    return (
        <AsyncSwitch
            data={data}
            size="lg"
            style={{ width: width }}
            switchValue={value}
            onValueChange={setValue}
            onLoadingChange={(val) => {
                isLoading.current = val;
            }}
        >
            {data.label.endsWith("开关") ? data.label.slice(0, -2) : data.label}
        </AsyncSwitch>
    );
}

function SingleTypeTemplates(type: string, data: carData[], isInList: boolean) {
    if (type === "multiGearAdjusts") {
        return <ListWithFlexChildren children={makeMultiGearAdjustmentsRows(data, isInList)} />
    }
    const children = makeSigleTypeChildren(type, data);
    return placeChildren(children, isInList);
}


function makeSigleTypeChildren(type: string, data: carData[]) {
    const childrenCount = data.length;
    let frontAcExist = false;
    let rearAcExist = false;
    let fridgeExist = false;
    switch (childrenCount) {
        // 一个功能和两个功能的时候比较特殊，其他逻辑可复用
        case 1:
            const data0 = data[0]
            switch (type) {
                case "adjusts":
                    const specialResult = renderSpecialType(data0.getType!, frontAcExist, rearAcExist, fridgeExist, 
                        (value: boolean) => { frontAcExist = value; },
                        (value: boolean) => { rearAcExist = value; },
                        (value: boolean) => { fridgeExist = value; },
                        OverRideDisplayAdjustOne,
                        false
                    );
                    if (specialResult) {
                        return specialResult;
                    }
                    return <OneItemAdjustments data={data0} />
                case "controls":
                    return <OneButtonControl data={data0} />
                case "displays":
                    return <OneDisplay data={data0} />
                default: // 非法字段
                    return <div />;
            }
        case 2:
            switch (type) {
                case "adjusts":
                    return data.map((item, index) => {
                        const specialResult = renderSpecialType(item.getType!, frontAcExist, rearAcExist, fridgeExist, 
                            (value: boolean) => { frontAcExist = value; },
                            (value: boolean) => { rearAcExist = value; },
                            (value: boolean) => { fridgeExist = value; },
                            OverRideDisplayAdjustTwo,
                            false
                        );
                        if (specialResult) {
                            return specialResult;
                        }
                        return <TwoItemAdjustments data={item} />
                    })
                case "controls":
                    return data.map((item, index) => {
                        return <TwoButtonControl data={item} />
                    })
                case "displays":
                    return data.map((item, index) => {
                        return <TwoDisplay data={item} />
                    })
                default: // 非法字段
                    return <div />;
            }
        default:
            switch (type) {
                case "adjusts":
                    return data.map((item, index) => {
                        let isOddLastRow = index === data.length - 1 && data.length % 2 != 0;
                        if (isOddLastRow) {
                            const specialResult = renderSpecialType(item.getType!, frontAcExist, rearAcExist, fridgeExist, 
                                (value: boolean) => { frontAcExist = value; },
                                (value: boolean) => { rearAcExist = value; },
                                (value: boolean) => { fridgeExist = value; },
                                OverRideDisplayAdjustTwo,
                                false
                            );
                            if (specialResult) {
                                return specialResult;
                            }
                            return <TwoItemAdjustments data={item} />
                        } else {
                            const specialResult = renderSpecialType(item.getType!, frontAcExist, rearAcExist, fridgeExist, 
                                (value: boolean) => { frontAcExist = value; },
                                (value: boolean) => { rearAcExist = value; },
                                (value: boolean) => { fridgeExist = value; },
                                OverRideDisplayAdjustMore,
                                false
                            );
                            if (specialResult) {
                                return specialResult;
                            }
                            return <MoreItemAdjustments data={item} />
                        }
                    });
                case "controls":
                    return data.map((item, index) => {
                        return <MoreButtonControl data={item} dataCount={data.length} />
                    })
                case "displays":
                    return data.map((item, index) => {
                        let isOddLastRow = index === data.length - 1 && data.length % 2 != 0;
                        return <MoreDisplay data={item} dataCount={data.length} isOddLastRow={isOddLastRow} />
                    })
                default: // 非法字段
                    return <div />;
            }
    }
}

function placeChildren(children: React.ReactElement | React.ReactElement[], inList: boolean) {
    // 如果是数组直接返回，否则包成数组
    if (!Array.isArray(children)) {
        return children;
    } else if (children.length > 2 || inList) {
        const rows = [];
        for (let i = 0; i < children.length; i += 2) {
            // 如果是最后一个且为奇数，单独一行
            if (i === children.length - 1) {
                rows.push(
                    <div className={cn("flex w-full mb-[30px] last:mb-0", !inList && "h-full")}>
                        <div className="flex-1 w-full h-full">{children[i]}</div>
                    </div>
                );
            } else {
                rows.push(
                    <div className={cn("flex w-full gap-[30px] mb-[30px] last:mb-0", !inList && "h-full")}>
                        <div className="flex-1 w-[392px] h-full">{children[i]}</div>
                        <div className="flex-1 w-[392px] h-full">{children[i + 1]}</div>
                    </div>
                );
            }
        }
        return <div className={cn("flex flex-col h-full w-full", inList && "mt-[30px]")}>{rows}</div>;
    } else if (children.length == 2) {
        return (
            <div className="flex flex-col h-full w-full gap-[30px]">
                <div className="flex-1 w-full">{children[0]}</div>
                <div className="flex-1 w-full">{children[1]}</div>
            </div>
        );
    }
}

const singleElementVariants = cva(
    "", // 基础类名
    {
        variants: {
            variant: {
                oneItem: "flex flex-col items-center justify-center gap-[90px] rounded-[20px] h-full w-full",
                twoItems: "flex flex-col items-center justify-center gap-[38px] bg-slate-50 rounded-[20px] h-full w-full leading-none p-[35px] !pb-[25px]",
                moreItems: "flex flex-col justify-between items-start bg-slate-50 rounded-[20px] h-full",
                // 当前只用于列表中的显示类
                inList: "flex flex-col justify-between gap-[38px] bg-slate-50 rounded-[20px] h-[316px] w-full p-[20px] leading-none",

            }
        },
        defaultVariants: {
            variant: "oneItem",
        },
    }
);

export interface SingleFunctionUnitProps
    extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof singleElementVariants> { }

export function SingleFunctionUnit({
    children,
    className,
    variant = "moreItems",
    ...props
}: SingleFunctionUnitProps) {
    return (
        <div className={cn(singleElementVariants({ variant }), className)} {...props}>
            {children}
        </div>
    );
}

export function getValueFontSize(dataCount: number, isOddLastRow: boolean) {
    if (dataCount == 1) {
        return "text-[210px]";
    } else if (dataCount == 2) {
        return "text-[160px]";
    } else {
        if (isOddLastRow) {
            return "text-[100px]";
        } else {
            return "text-[80px]";
        }
    }
}

export function getUnitFontSize(dataCount: number) {
    if (dataCount <= 2) {
        return "text-[72px]";
    } else if (dataCount <= 4) {
        return "text-[50.4px]";
    } else if (dataCount > 4) {
        return "text-[36px]";
    }
}

export function getIconSize(dataCount: number) {
    if (dataCount <= 2) {
        return "w-[72px] h-[72px]";
    } else if (dataCount <= 4) {
        return "size-[90px]";
    } else if (dataCount > 4) {
        return "size-[64px]";
    }
}

export function getLabelFontSize(dataCount: number) {
    if (dataCount == 1) {
        return "text-[64px]";
    } else if (dataCount == 2) {
        return "text-[48px]";
    } else if (dataCount <= 4) {
        return "text-[36px]";
    } else if (dataCount > 4) {
        return "text-[32px]";
    }
}