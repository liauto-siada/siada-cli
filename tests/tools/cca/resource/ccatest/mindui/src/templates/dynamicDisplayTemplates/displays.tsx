import { SingleFunctionUnit, type carData, getValueFontSize, getUnitFontSize, getIconSize, getLabelFontSize } from "./dynamicTemplates";
import { AsyncValue, iconsMap } from "./asyncComponents";
import { useState } from "react";

function getIconComponent(iconSrc?: string, className?: string) {
    if (!iconSrc) return null;
    const Comp = iconsMap && iconsMap[iconSrc as keyof typeof iconsMap];
    if (Comp) {
        return <Comp className={className} color="var(--color-car-icon)" />;
    } else {
        return <img src={iconSrc} alt="icon" className={className} />;
    }
}

export function OneDisplay({ data }: { data: carData }) {
    const [needsUnit, setNeedsUnit] = useState(true);
    const [label, setLabel] = useState(data.label);
    return (
        <div className="flex flex-col items-center justify-between bg-slate-50 h-full rounded-[20px] pt-[218px] pb-[282px]">
            <div className="flex flex-row items-center justify-center gap-[10p]">
                {getIconComponent(data.iconSrc, "size-[88.24px]")}
                <span className="text-[64px] font-semibold text-gray-600"> {label} </span>
            </div>
            <div className="flex flex-col items-center justify-center">
                <AsyncValue data={data} className="text-[210px] font-bold text-gray-900 !leading-[1.4]" refreshFrequency={data.refreshFrequency} needsUnit={setNeedsUnit} modifyLabel={setLabel} unitClassName="text-7xl text-data-unit !leading-[1.4]" />
                {needsUnit && <span className="text-7xl text-data-unit !leading-[1.4]"> {getRealUnit(data.getType!) ?? data.unit} </span>}
            </div>
        </div>
    );
}

export function TwoDisplay({ data }: { data: carData }) {
    const [needsUnit, setNeedsUnit] = useState(true);
    const [label, setLabel] = useState(data.label);

    return (
        <div className="flex flex-col items-center justify-between bg-slate-50 h-full rounded-[20px] pt-[112px] pb-[60px]">
            <div className="flex flex-row items-center justify-center gap-[10px]">
                {getIconComponent(data.iconSrc, "size-[72px]")}
                <span className="text-[48px] font-semibold text-gray-600 leading-none"> {label} </span>
            </div>
            <div className="flex flex-row items-baseline justify-center gap-[12px]">
                <AsyncValue data={data} className="text-[160px] font-bold text-gray-900 leading-[1.25]" refreshFrequency={data.refreshFrequency} needsUnit={setNeedsUnit} modifyLabel={setLabel} unitClassName="text-7xl text-data-unit !leading-[1.4]" />
                {needsUnit && <span className="text-7xl text-data-unit leading-[1.4]"> {getRealUnit(data.getType!) ?? data.unit} </span>}
            </div>
        </div>
    );
}

export function MoreDisplay({ data, dataCount, isOddLastRow }: { data: carData, dataCount: number, isOddLastRow: boolean }) {
    const valueFontSize = getValueFontSize(dataCount, isOddLastRow);
    const unitFontSize = getUnitFontSize(dataCount);
    const iconSize = getIconSize(dataCount);
    const labelFontSize = getLabelFontSize(dataCount);
    const height = dataCount >= 5 ? "h-[329px]" : "h-[510px]";
    const [needsUnit, setNeedsUnit] = useState(true);
    const [label, setLabel] = useState(data.label);
    const valueLimit = isOddLastRow ? "" : "max-w-[300px] overflow-hidden";
    return <div className={height}>
    <SingleFunctionUnit variant="moreItems" className={`${dataCount >= 4 ? "!p-[30px]" : "!p-[40px]"}`}>
        {getIconComponent(data.iconSrc, `${iconSize}`)}
        <div className="flex flex-col items-start justify-between">
            <span className={`font-semibold text-gray-600 leading-none ${labelFontSize}`}> {label} </span>
            <div className="flex flex-row items-baseline mt-[20px] leading-none">
                <AsyncValue data={data} className={`font-bold text-gray-900 leading-none ${valueLimit} ${valueFontSize} leading-none`} refreshFrequency={data.refreshFrequency} needsUnit={setNeedsUnit} modifyLabel={setLabel} unitClassName={`text-data-unit ${unitFontSize}`} />
                {needsUnit && <span className={`text-data-unit ${unitFontSize} ml-[10px]`}> {getRealUnit(data.getType!) ?? data.unit} </span>}
            </div>
        </div>
    </SingleFunctionUnit>
    </div>
}

export function makeDisplayInList(data: carData[]) {
    return data.map((item, index) => {
        const isOddLastRow = data.length % 2 === 1 && index === data.length - 1;
        // 都使用小尺寸
        return <MoreDisplay data={item} dataCount={5} isOddLastRow={isOddLastRow} />
    })
}

export function getRealUnit(type: string) {
    if (["CltcPureEvMileage", "WltcPureEvMileage", "CltcReevMileage", "WltcReevMileage"].includes(type)) {
        return "KM";
    } else if (type === "PowerPercent") {
        return "%";
    } else {
        return null;
    }
}