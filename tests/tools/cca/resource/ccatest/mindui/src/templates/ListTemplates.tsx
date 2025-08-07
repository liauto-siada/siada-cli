import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Image } from "@/components/mindui/image";

const List = () => {
  return (
    <div className="flex flex-col">
      {Array.from({ length: 5 }).map((_, idx, arr) => (
        <div key={idx}>
          <ListItemTitleWithImageTagDate />
          {idx !== arr.length - 1 && <Separator />}
        </div>
      ))}
    </div>
  );
};

export default List;

const ListItemTitle = () => {
  return (
    <div className="py-[79px] text-5xl leading-[72px] font-bold text-gray-900">
      01 乌空军称俄军向乌境内发射352架无人机和16枚导弹
    </div>
  );
};

const ListItemTitleAndSubTitle = () => {
  return (
    <div className="flex flex-col gap-y-[25px] py-[74px]">
      <p className="text-5xl font-bold text-gray-900">列表标题</p>
      <p className="flex items-center text-3xl text-gray-600">
        作者
        <span className="mx-[10px] inline-block h-[8px] w-[8px] rounded-full bg-gray-200"></span>
        副标题内容
      </p>
    </div>
  );
};

const ListItemTitleAndUList = () => {
  return (
    <div className="py-[44px]">
      <p className="pb-[40px] text-5xl font-bold text-gray-900">列表标题</p>
      <div className="flex flex-col gap-y-[15px] text-3xl text-gray-600">
        <p className="flex items-center">
          <span className="mr-[22px] inline-block h-[10px] w-[10px] rounded-full bg-gray-900"></span>
          Claude 3.7 Sonnet 发布增强版推理能力
        </p>
        <p className="flex items-center">
          <span className="mr-[22px] inline-block h-[10px] w-[10px] rounded-full bg-gray-900"></span>
          AI 监管法案获多国支持
        </p>
        <p className="flex items-center">
          <span className="mr-[22px] inline-block h-[10px] w-[10px] rounded-full bg-gray-900"></span>
          量子计算突破加速 AI 训练
        </p>
      </div>
    </div>
  );
};

const ListItemTitleDetailWithTagAuthorSubtitle = () => {
  const templateDate = {
    title: "Claude 3.7 发布增强版推理能力",
    description: "拉萨的标志性建筑拉萨的标志性建筑拉萨的标志性建筑",
    tag: "科技",
    author: "作者",
    subtitle: "副标题内容",
  };
  return (
    <div className="my-[68px] flex h-full w-[813px] flex-col">
      <div className="truncate text-5xl font-bold text-gray-900">
        {templateDate.title}
      </div>
      <div className="mt-[25px] truncate text-3xl text-gray-600">
        {templateDate.description}
      </div>
      <div className="mt-[40px] flex flex-row items-center">
        <Badge variant="normal" color="weak" size="small">
          {templateDate.tag}
        </Badge>
        <div className="mx-2.5 h-2 w-2 rounded-full bg-gray-950 opacity-20" />
        <div className="text-2xl text-gray-600">{templateDate.author}</div>
        <div className="mx-2.5 h-2 w-2 rounded-full bg-gray-950 opacity-20" />
        <div className="text-2xl text-gray-600">{templateDate.subtitle}</div>
      </div>
    </div>
  );
};

const ListItemTitleWithImageTagDate = () => {
  const templateDate = {
    title: "人工智能在医疗领域取得重大突破，AI诊断系统准确率达99%",
    imageUrl: "https://picsum.photos/480/600",
    tag: "科技",
    date: "2小时前",
  };
  return (
    <div className="flex h-full w-full">
      <div className="my-[50px] flex flex-row items-center">
        <div className="flex w-[300px] flex-shrink-0 flex-col items-center justify-center">
          <Image url={templateDate.imageUrl} />
        </div>
        <div className="ml-[26px] flex min-w-0 flex-1 flex-col">
          <div className="text-3xl leading-[52px] font-bold break-words text-gray-950">
            {templateDate.title}
          </div>
          <div className="mt-[25px] flex h-[48px] flex-row items-center">
            <Badge variant="normal" color="weak" size="small">
              {templateDate.tag}
            </Badge>
            <div className="mx-[15px] h-[6px] w-[6px] rounded-full bg-gray-400" />
            <div className="text-xl text-gray-700">{templateDate.date}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

const ListItemTitleWithAuthorSubtitle = () => {
  const templateDate = {
    title: "乌空军称俄军向乌军境内发射352架无人机和16枚导弹",
    tag: "科技",
    author: "作者",
    subtitle: "副标题内容",
  };
  return (
    <div className="my-[70px] flex h-full w-full flex-col">
      <div className="text-5xl leading-[72px] font-bold text-gray-950">
        {templateDate.title}
      </div>
      <div className="mt-[30px] flex flex-row items-center">
        <Badge variant="normal" color="weak" size="small">
          {templateDate.tag}
        </Badge>
        <div className="mx-2.5 h-2 w-2 rounded-full bg-gray-950 opacity-20" />
        <div className="text-3xl text-gray-600">{templateDate.author}</div>
        <div className="mx-2.5 h-2 w-2 rounded-full bg-gray-950 opacity-20" />
        <div className="text-3xl text-gray-600">{templateDate.subtitle}</div>
      </div>
    </div>
  );
};

export {
  ListItemTitle,
  ListItemTitleAndSubTitle,
  ListItemTitleAndUList,
  ListItemTitleDetailWithTagAuthorSubtitle,
  ListItemTitleWithImageTagDate,
  ListItemTitleWithAuthorSubtitle,
};
