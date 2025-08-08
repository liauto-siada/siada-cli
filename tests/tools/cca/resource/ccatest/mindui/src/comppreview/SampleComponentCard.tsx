import React, { useState } from "react";

// 修改的组件导入
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Progress } from "@/components/ui/progress";
import { Checkbox } from "@/components/ui/checkbox";

// 新增的组件导入
import { IconButton } from "@/components/ui/iconbutton";
import { BrightnessSlider } from "@/components/mindui/sliderbar";
import { HorizontalSelector } from "@/components/mindui/horizontal-selector";
import { Image } from "@/components/mindui/image";
import { Loading } from "@/components/mindui/loading";
import { AreaChartsExample } from "@/components/mindui/area-chart";
import { Badge } from "@/components/ui/badge";
import ShowingBox from "@/gesture_animation/ShowingBox";

// 图标导入
import {
  Settings,
  Home,
  Search,
  Thermometer,
  ThermometerSnowflake,
  ThermometerSun,
} from "lucide-react";

import {
  Cold
} from '@/components/icons/icons/index';

import { PieChartExample } from "@/components/mindui/pie-chart";

import type { CheckedState } from "@radix-ui/react-checkbox";
import { HorizontalMultiBarChartExample, HorizontalSingleBarChartExample, VerticalMultiBarChartExample, VerticalSingleBarChartExample } from "@/components/mindui/bar-chart";
import { MultiLineChartExample, SingleLineChartExample } from "@/components/mindui/line-chart";
import { GearGaugeExample, SpeedGaugeExample } from "@/components/mindui/gauge";
import { RadialBarChartExample } from "@/components/mindui/radial-bar-chart";
import { CalendarExample } from "@/components/mindui/calendar";
import TextLink from "@/components/mindui/textLink";
import Bubble from "@/components/mindui/bubble";
import { TimelineDemo } from "@/components/mindui/timeline";
import TapBox from "@/gesture_animation/GestureBox";

const SampleComponentCard = () => {
  // 状态管理
  const [inputText, setInputText] = useState("");
  const [searchText, setSearchText] = useState("");
  const [selectedOption, setSelectedOption] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [enabled2, setEnabled2] = useState(false);
  const [brightness, setBrightness] = useState([50]);
  const [temperature, setTemperature] = useState([25]);
  const [currentTab, setCurrentTab] = useState("all");
  const [currentTab2, setCurrentTab2] = useState("all");
  const [isToggled1, setIsToggled1] = useState(false);
  const [isToggled2, setIsToggled2] = useState(true);
  const [progress, setProgress] = useState(13);
  const [isVisible, setIsVisible] = useState(false);
  const [useEmphasis, setUseEmphasis] = useState(false);

  // 进度条演示函数
  const startProgressDemo = () => {
    setProgress(13); // 重置进度
    const timer1 = setTimeout(() => setProgress(65), 500);
    const timer2 = setTimeout(() => setProgress(100), 1500);

    // 清理定时器的函数会在组件卸载时自动调用
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
    };
  };

  const tabOptions = [
    { label: "全部", value: "all" },
    { label: "设置", value: "settings" },
    { label: "显示", value: "display" },
    { label: "声音", value: "audio" },
    { label: "通知", value: "notifications" },
  ];
  
  const [checked, setChecked] = React.useState<CheckedState>('indeterminate');

  return (
    <div>
      <TapBox>
      <div className="mb-16 text-center">
          <h1 className="mb-4 text-7xl font-bold text-gray-800">组件展示</h1>
        <p className="text-4xl text-gray-800/60">
          改版原生组件与自定义组件展示页面
        </p>
      </div>
      </TapBox>
      {/* 按钮组件展示 */}
      <Section title="按钮组件">
        <div className="grid grid-cols-1 gap-12">
          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              按钮变体
            </h3>
            <div className="flex flex-wrap gap-6">
              <Button variant="activated" icon={<Cold />}>
                激活按钮
              </Button>
              <Button variant="primary" icon={<Cold />}>
                主要按钮
              </Button>
              <Button variant="secondary" icon={<Cold />}>
                次要按钮
              </Button>
              <Button variant="warning" icon={<Cold />}>
                警示按钮
              </Button>
              <Button variant="ghost" icon={<Cold />}>
                幽灵按钮
              </Button>
              <Button variant="text" icon={<Cold />}>
                文本按钮
              </Button>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              禁用状态
            </h3>
            <div className="flex flex-wrap gap-6">
              <Button variant="activated" disabled icon={<Cold />}>
                激活按钮
              </Button>
              <Button variant="primary" disabled icon={<Cold />}>
                主要按钮
              </Button>
              <Button variant="secondary" disabled icon={<Cold />}>
                次要按钮
              </Button>
              <Button variant="warning" disabled icon={<Cold />}>
                警示按钮
              </Button>
              <Button variant="ghost" disabled icon={<Cold />}>
                幽灵按钮
              </Button>
              <Button variant="text" disabled icon={<Cold />}>
                文本按钮
              </Button>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              加载状态
            </h3>
            <div className="flex flex-wrap gap-6">
              <Button variant="activated" loading icon={<Cold />}>
                激活按钮
              </Button>
              <Button variant="primary" loading icon={<Cold />}>
                主要按钮
              </Button>
              <Button variant="secondary" loading icon={<Cold />}>
                次要按钮
              </Button>
              <Button variant="warning" loading icon={<Cold />}>
                警示按钮
              </Button>
              <Button variant="ghost" loading icon={<Cold />}>
                幽灵按钮
              </Button>
              <Button variant="text" loading icon={<Cold />}>
                文本按钮
              </Button>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              按钮尺寸
            </h3>
            <div className="flex flex-wrap items-end gap-6">
              <Button size="xs" icon={<Cold />}>
                超小按钮
              </Button>
              <Button size="sm" icon={<Cold />}>
                小按钮
              </Button>
              <Button size="md" icon={<Cold />}>
                中等按钮
              </Button>
              <Button size="lg" icon={<Cold />}>
                大按钮
              </Button>
              <Button size="xl" icon={<Cold />}>
                超大按钮
              </Button>
              <Button size="xl" style={{ width: "600px" }} icon={<Cold />}>
                自定义长度按钮
              </Button>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              图标按钮
            </h3>
            <div className="space-y-6">
              <div className="flex items-end gap-3">
                <Button size="xs" icon={<Cold />} />
                <Button size="sm" icon={<Cold />} />
                <Button size="md" icon={<Cold />} />
                <Button size="lg" icon={<Cold />} />
                <Button size="xl" icon={<Cold />} />
              </div>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              开关按钮
            </h3>
            <div className="space-y-6">
              <div className="flex items-end gap-3">
                <Button
                  isToggled={isToggled1}
                  onClick={() => setIsToggled1(!isToggled1)}
                >
                  默认关闭
                </Button>
                <Button
                  isToggled={isToggled2}
                  onClick={() => setIsToggled2(!isToggled2)}
                >
                  默认开启
                </Button>
              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* 表单组件展示 */}
      <Section title="表单组件">
        <div className="grid grid-cols-1 gap-12">
          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              输入框
            </h3>
            <div className="max-w-xl space-y-8">
              <div>
                <p className="mb-4 text-3xl text-gray-800/60">默认输入框</p>
                <Input
                  variant="default"
                  type="text"
                  placeholder="请输入内容"
                  value={inputText}
                  inputSize="md"
                  onChange={(e) => setInputText(e.target.value)}
                  className="w-full"
                />
              </div>
              <div>
                <p className="mb-4 text-3xl text-gray-800/60">搜索输入框</p>
                <Input
                  variant="search"
                  type="text"
                  placeholder="搜索内容"
                  value={searchText}
                  inputSize="md"
                  onChange={(e) => setSearchText(e.target.value)}
                  className="w-full"
                />
              </div>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              选择器
            </h3>
            <div className="max-w-md">
              <Select value={selectedOption} onValueChange={setSelectedOption}>
                <SelectTrigger size="md">
                  <SelectValue placeholder="请选择选项" />
                </SelectTrigger>
                <SelectContent size="md">
                  <SelectGroup>
                    <SelectItem size="md" value="option1">
                      选项一
                    </SelectItem>
                    <SelectSeparator />
                    <SelectItem size="md" value="option2">
                      选项二
                    </SelectItem>
                    <SelectItem size="md" value="option3">
                      选项三
                    </SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              <p className="mt-4 text-3xl text-gray-800/60">
                当前选择: {selectedOption || "未选择"}
              </p>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              开关组件
            </h3>
            <div className="flex flex-wrap gap-10">
              <div className="flex flex-col items-center">
                <p className="mb-4 text-3xl text-gray-800/60">默认状态</p>
                <Switch
                  checked={enabled}
                  onCheckedChange={setEnabled}
                  size="md"
                />
                <p className="mt-3 text-3xl text-gray-800/60">
                  状态: {enabled ? "开启" : "关闭"}
                </p>
              </div>
              <div className="flex flex-col items-center">
                <p className="mb-4 text-3xl text-gray-800/60">禁用开启</p>
                <Switch checked={true} disabled />
              </div>
              <div className="flex flex-col items-center">
                <p className="mb-4 text-3xl text-gray-800/60">禁用关闭</p>
                <Switch checked={false} disabled />
              </div>
              <div className="flex flex-col items-center">
                <p className="mb-4 text-3xl text-gray-800/60">加载状态</p>
                <Switch checked={true} loading />
              </div>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              滑动条
            </h3>
            <div className="max-w-2xl space-y-12">
              <div>
                <p className="mb-4 text-3xl text-gray-800/60">精确模式</p>
                <BrightnessSlider
                  mode="precise"
                  size="md"
                  value={temperature}
                  formatLabel={(value) => `${value}°C`}
                  onValueChange={setTemperature}
                  iconStart={
                    <ThermometerSnowflake size={28} className="text-blue-500" />
                  }
                  iconEnd={
                    <ThermometerSun size={28} className="text-red-500" />
                  }
                />
                <p className="mt-3 text-3xl text-gray-800/60">
                  当前温度: {temperature[0]}°C
                </p>
              </div>
              <div>
                <p className="mb-4 text-3xl text-gray-800/60">模糊模式</p>
                <BrightnessSlider
                  mode="blur"
                  size="md"
                  value={brightness}
                  onValueChange={setBrightness}
                  iconStart={
                    <Thermometer size={28} className="text-blue-500" />
                  }
                />
                <p className="mt-3 text-3xl text-gray-800/60">
                  当前亮度: {brightness[0]}%
                </p>
              </div>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              进度条
            </h3>
            <div className="max-w-2xl space-y-12">
              <div className="space-y-6">
                <Progress value={progress} />
                <Progress
                  value={progress}
                  variant="green"
                  className="h-[30px] w-[700px]"
                />
                <p className="mt-3 text-3xl text-gray-800/60">
                  当前进度: {progress}%
                </p>
                <Button variant="primary" size="xs" onClick={startProgressDemo}>
                  开始演示
                </Button>
              </div>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              加载状态
            </h3>
            <div className="space-y-6">
              <Loading />
            </div>
          </div>
        </div>
      </Section>

      {/* 布局组件展示 */}
      <Section title="布局组件">
        <div className="space-y-12">
          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              分割线
            </h3>
            <div className="space-y-10">
              <div>
                <p className="mb-4 text-3xl text-gray-800/60">水平场景分割线</p>
                <Separator />
              </div>
              <div>
                <p className="mb-4 text-3xl text-gray-800/60">垂直场景分割线</p>
                <div className="flex h-40 items-center">
                  <span className="mr-8 text-4xl text-gray-800/90">
                    左侧内容
                  </span>
                  <Separator orientation="vertical" />
                  <span className="ml-8 text-4xl text-gray-800/90">
                    右侧内容
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              水平选择器
            </h3>
            <div className="max-w-2xl">
              <HorizontalSelector
                options={tabOptions}
                value={currentTab}
                onChange={setCurrentTab}
                size="md"
              />
              <div className="mt-6 p-6">
                <p className="text-4xl text-gray-800/90">
                  当前选择:{" "}
                  <span className="font-bold">
                    {tabOptions.find((opt) => opt.value === currentTab)?.label}
                  </span>
                </p>
              </div>
            </div>
          </div>
          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              checkbox
            </h3>
            <div>
              <Checkbox
                checked={checked}
                onCheckedChange={setChecked}
                id="my-checkbox"
              />
              <label htmlFor="my-checkbox" className="ml-2">
                是否选中: {checked ? "是" : "否"}
              </label>
            </div>
          </div>
          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              标签
            </h3>
            <div className="flex flex-wrap gap-6">
              <Badge variant="highlight" color="hot" size="large">
                HOT
              </Badge>
              <Badge variant="highlight" color="vip" size="large">
                VIP
              </Badge>
              <Badge variant="highlight" color="self" size="large">
                自制
              </Badge>
            </div>
            <div className="flex flex-wrap gap-6">
              <Badge>
                标签说明
              </Badge>
              <Badge variant="weak">
                实事热点
              </Badge>
              <Badge variant="normal">
                实事热点
              </Badge>
            </div>
          </div>
          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              链接
            </h3>
            <TextLink content="点击我访问百度" href="https://www.baidu.com" className="text-4xl text-gray-800/90" />
          </div>
          <div>
            <h3 className="mb-8 text-5xl font-medium text-gray-800/90">
              气泡
            </h3>
            <Bubble content="太空为什么不适合人类居住？" />
          </div>
        </div>
      </Section>

      {/* 使用场景示例 */}
      <Section title="使用场景示例">
        <div className="p-8">
          <div className="mb-10 flex items-center justify-between">
            <h3 className="text-6xl font-bold text-gray-800">系统设置</h3>
            <Button size="sm" icon={<Settings />} />
          </div>

          <div className="space-y-10">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="mb-2 text-5xl font-medium text-gray-800/90">
                  功能开关
                </h4>
                <p className="text-3xl text-gray-800/40">
                  {enabled2 ? "关闭后将停用此功能" : "启用后将开启此功能"}
                </p>
              </div>
              <Switch
                checked={enabled2}
                onCheckedChange={setEnabled2}
                size="md"
              />
            </div>

            <Separator />

            <div>
              <h4 className="mb-6 text-5xl font-medium text-gray-800/90">
                屏幕亮度
              </h4>
              <BrightnessSlider
                mode="precise"
                size="sm"
                value={brightness}
                onValueChange={setBrightness}
                formatLabel={(value) => `${value}%`}
              />
            </div>

            <Separator />

            <div>
              <h4 className="mb-6 text-5xl font-medium text-gray-800/90">
                通知设置
              </h4>
              <HorizontalSelector
                options={[
                  { label: "全部通知", value: "all", tag: true },
                  { label: "仅重要", value: "important" },
                  { label: "无通知", value: "none", icon: "House" },
                ]}
                value={currentTab2}
                onChange={setCurrentTab2}
                size="sm"
                color="primary"
              />
            </div>

            <div className="h-[80px] w-[200px] border-2 border-dashed border-gray-300">
              <Image url="https://picsum.photos/400/300" fit="standard" />
            </div>

            <div className="h-[80px] w-[200px] border-2 border-dashed border-gray-300">
              <Image url="https://picsum.photos/400/600" fit="natural" />
            </div>

            <div className="h-[300px] w-[600px]">
              <AreaChartsExample />
            </div>
            
            <div className="h-[120px] w-[200px]">
              <AreaChartsExample />
            </div>
  
            <PieChartExample />
            <VerticalMultiBarChartExample />
            <VerticalSingleBarChartExample />
            <HorizontalMultiBarChartExample />
            <HorizontalSingleBarChartExample />
            <SingleLineChartExample />
            <MultiLineChartExample />

            <SpeedGaugeExample />
            <GearGaugeExample />

            <RadialBarChartExample />

            <CalendarExample />

            <TimelineDemo />

            <div className="flex gap-4 w-full">
              <Button onClick={() => setIsVisible(!isVisible)}>
                切换显示
              </Button>
              <Button onClick={() => setUseEmphasis(!useEmphasis)}>
                切换强调动画: {useEmphasis ? '开启' : '关闭'}
              </Button>
              <ShowingBox 
                showing={isVisible}
                emphasisAnimation={useEmphasis}
                className="relative p-8 bg-white rounded-lg"
              >
                <div>
                  弹窗
                </div>
              </ShowingBox>
            </div>
          </div>
        </div>
      </Section>
    </div>
  );
};

// 辅助组件：分区容器
const Section = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) => (
  <section className="mb-16 p-8">
    <h2 className="mb-10 border-b border-gray-200 pb-4 text-6xl font-bold text-gray-800">
      {title}
    </h2>
    {children}
  </section>
);

export default SampleComponentCard;
