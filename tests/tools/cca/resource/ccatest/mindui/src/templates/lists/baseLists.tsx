import { Separator } from "@/components/ui/separator";
import React from "react";

// @ts-ignore
import clockGray from "../../assets/clock-gray.svg"
import { cn } from "@/lib/utils";

// 193061/191029 两个列表样式相同
export default function List193061() {
    const tags = [1, 2, 3, 4, 5]
    return (<div className="w-full h-full">
        {tags.map((item, idx) => (
            <React.Fragment key={item}>
                <h1 className="text-6xl font-bold text-gray-900 mb-[52px]">列表标题{item}</h1>
                {idx !== tags.length - 1 && (
                    <Separator color="scenic-light" className="mb-[52px]"/>
                )}
            </React.Fragment>
        ))}
    </div>);
}

export function List193059() {
    const tags = [1, 2, 3, 4, 5]
    return (<div className="w-full h-full">
        {tags.map((item, idx) => (
            <React.Fragment key={item}>
                <div className="flex items-center text-6xl font-bold text-gray-900 mb-[52px]">
                    <img src={clockGray} alt="clock" className="size-52.5px mr-[17.5px]" />
                    <h1>列表标题{item}</h1>
                </div>
                {idx !== tags.length - 1 && (
                    <Separator color="scenic-light" className="mb-[52px]"/>
                )}
            </React.Fragment>
        ))}
    </div>);
}

export function BaseList({children, className, ...props}: React.ComponentProps<"div">) {
    if (!children) {
        return null;
    }
    return (
        <div className={cn("w-full h-full", className)} {...props}>
            {React.Children.map(children, (item, idx) => (
                <React.Fragment key={idx}>
                    {item}
                    {idx !== React.Children.count(children) - 1 && (
                        <Separator color="scenic-light"/>
                    )}
                </React.Fragment>
            ))}
        </div>
    );
}

export function ListWithFlexChildren({children, className, ...props}: React.ComponentProps<"div">) {
    if (!children) {
        return null;
    }
    return (
        <div className={cn("w-full h-full", className)} {...props}>
            {React.Children.map(children, (item, idx) => (
                <React.Fragment key={idx}>
                    {item}
                    {idx !== React.Children.count(children) - 1 && (
                        <Separator color="scenic-light" className="my-[60px]"/>
                    )}
                </React.Fragment>
            ))}
        </div>
    );
}