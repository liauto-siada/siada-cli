import { useLayoutEffect, useRef, useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { zhCN } from "date-fns/locale";
import {
  DayPicker,
  type DayButtonProps,
  type WeekdayProps,
} from "react-day-picker";
import { SolarDay } from "tyme4ts";
import React from "react";
import "./calendar.css";

const getLunarDay = (date: Date): string => {
  const solarDay = SolarDay.fromYmd(
    date.getFullYear(),
    date.getMonth() + 1,
    date.getDate(),
  );
  const lunarDay = solarDay.getLunarDay();
  return lunarDay.getName();
};

export interface CalendarProps {
  type?: "simple" | "lunar";
  selected?: Date;
  onSelect?: (date: Date | undefined) => void;
  className?: string;
  showOutsideDays?: boolean;
  weekStartsOn?: 0 | 1 | 2 | 3 | 4 | 5 | 6;
}

export default function Calendar({
  type = "simple",
  showOutsideDays = false,
  selected: controlledSelected,
  onSelect,
  weekStartsOn = 1,
}: CalendarProps) {
  const displayLunar = type === "lunar";
  const [currentDate, setCurrentDate] = useState(new Date());

  // 内部自管理 selected
  const [uncontrolledSelected, setUncontrolledSelected] = useState<Date | undefined>(controlledSelected);

  // 外部 selected 变化时同步
  useEffect(() => {
    if (controlledSelected !== undefined) {
      setUncontrolledSelected(controlledSelected);
    }
  }, [controlledSelected]);

  // useEffect(() => {
  //   const updateDate = () => {
  //     const now = new Date();
  //     if (now.toDateString() !== currentDate.toDateString()) {
  //       setCurrentDate(now);
  //     }
  //   };
  //   const scheduleNextMidnight = () => {
  //     const now = new Date();
  //     const tomorrow = new Date(now);
  //     tomorrow.setDate(tomorrow.getDate() + 1);
  //     tomorrow.setHours(0, 0, 0, 0);
  //     const timeToMidnight = tomorrow.getTime() - now.getTime();
  //     return setTimeout(() => {
  //       setCurrentDate(new Date());
  //       scheduleNextMidnight();
  //     }, timeToMidnight);
  //   };
  //   updateDate();
  //   const midnightTimer = scheduleNextMidnight();
  //   const backupTimer = setInterval(updateDate, 10000);
  //   return () => {
  //     clearTimeout(midnightTimer);
  //     clearInterval(backupTimer);
  //   };
  // }, [currentDate]);

  // 只测量一次外层容器尺寸
  const ref = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState<{ width: number; height: number } | null>(null);
  useLayoutEffect(() => {
    const container = ref.current;
    if (!container) return;
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0]) {
        const { width, height } = entries[0].contentRect;
        setDims({ width, height });
      }
    });
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  // 统一计算 cellSize（仅在 dims 存在时）
  const cellSize = dims ? {
    width: dims.width * 0.14,
    height: dims.height * 0.13,
  } : null;

  // 只在选中的日期变化时才触发
  const handleSelect = (date: Date | undefined) => {
    if (date?.toDateString() === uncontrolledSelected?.toDateString()) return;

    // TODO: a temporary solution to update the selected date
    setCurrentDate(date || new Date());

    setUncontrolledSelected(date);
    onSelect?.(date);
  };

  // 在获取到尺寸前，返回占位元素
  if (!dims || !cellSize) {
    return (
      <div
        ref={ref}
        className="flex h-full w-full flex-col items-center justify-between"
      >
        {/* 占位元素，保持容器大小但不显示内容，避免闪烁 */}
      </div>
    );
  }

  return (
    <div
      ref={ref}
      className="flex h-full w-full flex-col items-center justify-between calendar-fade-in"
    >
      <Label displayLunar={displayLunar} currentDate={currentDate} />
      <DayPicker
        mode="single"
        selected={uncontrolledSelected}
        onSelect={handleSelect}
        showOutsideDays={showOutsideDays}
        locale={zhCN}
        weekStartsOn={weekStartsOn}
        components={{
          CaptionLabel: () => <></>,
          Chevron: () => <></>,
          Weekday: (props) => WeekDay(props, cellSize),
          DayButton: (props) => <MemoDayButton {...props} displayLunar={displayLunar} cellSize={cellSize} />,
        }}
      />
    </div>
  );
}

interface LabelProps {
  className?: string;
  displayLunar: boolean;
  currentDate: Date;
}

const Label = ({ className, displayLunar, currentDate }: LabelProps) => {
  const ref = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState<{ width: number; height: number } | null>(null);

  const year = currentDate.getFullYear();
  const month = String(currentDate.getMonth() + 1).padStart(2, "0");
  const day = String(currentDate.getDate()).padStart(2, "0");

  const lunarDay = SolarDay.fromYmd(year, month, day).getLunarDay();
  const lunarMonthName = lunarDay.getLunarMonth().getName();
  const lunarDayName = lunarDay.getName();

  useLayoutEffect(() => {
    const container = ref.current;
    if (!container) return;
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0]) {
        const { width, height } = entries[0].contentRect;
        setDims({ width, height });
      }
    });
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  // 在获取到尺寸前，返回占位元素
  if (!dims) {
    return (
      <div
        ref={ref}
        className={cn(
          className,
          "flex w-full flex-col pl-4 font-bold text-gray-950",
        )}
      >
        {/* 保持空间但不显示内容 */}
        <span style={{ visibility: 'hidden' }}>
          {displayLunar && "占位"}
          {year}/{month}/{day}
        </span>
      </div>
    );
  }

  const fontSize = dims.width * 0.075;

  return (
    <div
      ref={ref}
      style={{ fontSize: fontSize }}
      className={cn(
        className,
        "flex w-full flex-col pl-4 font-bold text-gray-950",
      )}
    >
      {displayLunar && (
        <span>
          {lunarMonthName}
          {lunarDayName}
        </span>
      )}
      <span>
        {year}/{month}/{day}
      </span>
    </div>
  );
};

const WeekDay = (
  props: WeekdayProps,
  cellSize: { width: number; height: number },
) => {
  const { children, ...restProps } = props;
  const fontSize = cellSize.height * 0.25;

  return (
    <th
      {...restProps}
      style={{ fontSize: fontSize }}
      className={cn("py-8 text-center font-medium text-[var(--weekday-text)]")}
    >
      {children}
    </th>
  );
};

const DayButton = (
  props: DayButtonProps & { displayLunar: boolean; cellSize: { width: number; height: number } },
) => {
  const { day, modifiers, displayLunar, cellSize, ...restProps } = props;
  const date = day.date;
  const dayNumber = date.getDate();

  // 用 cellSize 统一设置宽高和字体，参数与最初一致
  const buttonSize = Math.min(cellSize.width, cellSize.height);
  const numFontSize = buttonSize * 0.33;
  const lunarFontSize = buttonSize * 0.2;
  const cornerSize = displayLunar ? buttonSize * 0.17 : buttonSize / 2;

  const buttonProps = {
    ...restProps,
    className: cn(
      "flex flex-col items-center justify-center",
      "font-bold text-[var(--day-text-unselected)]",
      modifiers.today && "text-[var(--day-text-today)]",
      modifiers.selected && "bg-[var(--day-bg-selected)] text-[var(--day-text-selected)]",
      "rounded-full transition-colors duration-150",
    ),
  };

  return (
    <button
      {...buttonProps}
      style={{
        width: displayLunar ? cellSize.width : buttonSize,
        height: displayLunar ? cellSize.height : buttonSize,
        borderRadius: cornerSize,
      }}
    >
      <span style={{ fontSize: numFontSize }}>{dayNumber}</span>
      {displayLunar && (
        <span
          style={{ fontSize: lunarFontSize }}
          className={cn(
            "text-[var(--day-lunar-text-unselected)]",
            modifiers.selected && "text-[var(--day-lunar-text-selected)]",
          )}
        >
          {getLunarDay(date)}
        </span>
      )}
    </button>
  );
};

const MemoDayButton = React.memo(DayButton);

Calendar.displayName = "Calendar";

export function CalendarExample() {
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(new Date());
  // 只在日期变化时 setState
  const handleSelect = (date: Date | undefined) => {
    if (date?.toDateString() === selectedDate?.toDateString()) return;
    setSelectedDate(date);
  };
  return (
    <div className="flex flex-col items-center justify-center p-2 gap-20">
      <div className="flex w-[500px] h-[600px] items-center">
        <Calendar
          type="simple"
          selected={selectedDate}
          onSelect={handleSelect}
        />
      </div>
      <div className="flex w-[500px] h-[600px] items-center">
        <Calendar
          type="lunar"
          selected={selectedDate}
          onSelect={handleSelect}
          weekStartsOn={0}
        />
      </div>
    </div>
  );
}
