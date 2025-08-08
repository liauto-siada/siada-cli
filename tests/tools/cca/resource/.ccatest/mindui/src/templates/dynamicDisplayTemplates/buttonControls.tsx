import { AsyncLabelShowToggled, AsyncSwitch } from "./asyncComponents";
import { SingleFunctionUnit, type carData } from "./dynamicTemplates";
import React, { useRef } from "react";

export function OneButtonControl({ data }: { data: carData }) {
    const [value, setValue] = React.useState<boolean>(false);
    const isLoading = useRef<boolean>(false);
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);

    React.useEffect(() => {
        data.getFunc((result: any) => {
            setValue(Number(result) === 1);
            console.log("async switch result: ", result, "getType: ", data.getType, "value: ", value);
        });
    }, []);
    
    return (
        <SingleFunctionUnit variant="oneItem">
            <AsyncSwitch 
                data={data} 
                size="xl" 
                style={{ width: "388px", height: "388px" }} 
                className="[&_svg]:h-[160px] [&_svg]:w-[160px] [&_span]:h-[160px]" 
                switchValue={value} 
                onValueChange={setValue}
                onLoadingChange={(val) => {
                    isLoading.current = val;
                }}
            />
            <div className="flex flex-col items-center justify-center">
                <span className="text-[80px] font-bold text-gray-900 leading-none"> {data.label} </span>
                <AsyncLabelShowToggled className="mt-[40px] font-semibold text-[42px] leading-none" value={value} />
            </div>
        </SingleFunctionUnit>
    );
}

export function TwoButtonControl({ data }: { data: carData }) {
    const [value, setValue] = React.useState<boolean>(false);
    const isLoading = useRef<boolean>(false);
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);

    React.useEffect(() => {
        data.getFunc((result: any) => {
            setValue(Number(result) === 1);
            console.log("async switch result: ", result, "getType: ", data.getType, "value: ", value);
        });
    }, []);
    
    return (
        <SingleFunctionUnit variant="twoItems">
            <AsyncSwitch 
                data={data} 
                size="xl" 
                style={{ width: "250px", height: "250px" }} 
                className="[&_svg]:h-[110px] [&_svg]:w-[110px] [&_span]:h-[100px]"
                switchValue={value}
                onValueChange={setValue}
                onLoadingChange={(val) => {
                    isLoading.current = val;
                }}
            />
            <div className="flex flex-col items-center justify-center">
                <span className="text-[62px] font-bold text-gray-900"> {data.label} </span>
                <AsyncLabelShowToggled className="mt-[20px] font-semibold text-[36px] leading-none" value={value} />
            </div>
        </SingleFunctionUnit>
    );
}

export function MoreButtonControl({ data, dataCount }: { data: carData, dataCount: number }) {
    const [value, setValue] = React.useState<boolean>(false);
    const isLoading = useRef<boolean>(false);
    const intervalRef = React.useRef<NodeJS.Timeout | null>(null);
    
    let buttonSize = dataCount < 5 ? "164px" : "120px";
    let labelFontSize = dataCount < 5 ? "text-[62px]" : "text-[38px]";
    let toggledFontSize = dataCount < 5 ? "36px" : "28px";
    let labelGap = dataCount < 5 ? "mt-[30px]" : "mt-[14px]";
    const height = dataCount >= 5 ? "h-[329px]" : "h-[510px]";

    React.useEffect(() => {
        data.getFunc((result: any) => {
            setValue(Number(result) === 1);
            console.log("async switch result: ", result, "getType: ", data.getType, "value: ", value);
        });
    }, []);

    return (
        <div className={height}>
    <SingleFunctionUnit variant="moreItems" className={`${dataCount >= 4 ? "!p-[30px]" : "!p-[40px]"}`}>
            <AsyncSwitch 
                data={data} 
                size="xl" 
                style={{ width: buttonSize, height: buttonSize }} 
                className="[&_svg]:h-[72px] [&_svg]:w-[72px] [&_span]:h-[72px]"
                switchValue={value}
                onValueChange={setValue}
                onLoadingChange={(val) => {
                    isLoading.current = val;
                }}
            />
            <div className="flex flex-col items-start justify-between">
                <span className={`${labelFontSize} font-bold text-gray-900 leading-none`}> {data.label} </span>
                <AsyncLabelShowToggled className={`${labelGap} font-semibold text-[${toggledFontSize}] leading-none`} value={value} />
            </div>
        </SingleFunctionUnit>
        </div>
    );
}