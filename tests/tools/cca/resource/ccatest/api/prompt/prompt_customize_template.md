### 2.5 模板使用规范

模板指的是容器内的UI内容，标题、滚动条等在外层容器已经提供，模板只提供内容区的UI。
在根据用户的指令生成前端ReactJS的UI代码的过程中，如果是命中了模板，就要强制按照模板的布局和样式实现，只更换数据。
当需要生成国际新闻或科技新闻卡片时，无论用户是否使用搜狗搜索，都调用NewsTool工具获取新闻数据，必须有图片、标题、标签、来源、链接，必须根据加入以下代码方式加入图片：
```typescript
import 外交部领事司提醒 from '@/image/外交部领事司提醒.jpg';
import 俄美首脑通话无进展 from '@/image/俄美首脑通话无进展.jpg';
```
请注意import的图片用international_news_data.json和tech_news_data.json中的图片名称，并确保图片存放在@/image目录下。

#### 资讯模板

所有资讯类的模板都是列表，下面我给你一个列表和多个Item模板的代码，只要是资讯类的强制使用下面的列表模板实现，但是只使用其中的一个Item，具体使用哪个Item需要根据你获取的数据，你来分析哪个最合适，就选一个Item然后填充数据，不允许使用item中示例/mock数据，你必须选择并且仅选择其中的一个Item，所有标签和样式完全使用此Item模板，只更换数据。下面的模板代码是让你用来强制使用这些布局层级和样式的，确保完全使用模板的布局和演示，但是使用其中一个Item，去掉其他Item的代码。所有资讯类卡片用到Badge标签的全部只能用`variant="normal" color="weak" size="small"`这种样式，不允许使用任何其他样式。
确保新闻类卡片都使用以下给定的模版样式，禁止自行添加其他组件。

#### 列表和Item模板的代码如下：

```typescript
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Image } from "@/components/mindui/image";

const List = () => {
  return (
    <div className="flex flex-col"> 
      {
        Array.from({ length: 5 }).map((_, idx, arr) => (
          <div key={idx}>
            <ListItemTitle />
            {idx !== arr.length - 1 && <Separator />}
          </div>
        ))
      }
    </div>
  );
} 

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
    <div className="flex h-full w-[813px] flex-col my-[68px] ">
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
    imageUrl: "https://picsum.photos/480/270",
    tag: "科技",
    date: "2小时前",
  };
  return (
    <a 
      key={idx}
      href={item.link} 
      target="_blank" 
      rel="noopener noreferrer"
      className="block no-underline hover:bg-gray-50 transition-colors rounded-lg"
    >
      <div className="flex h-full w-full">
        <div className="my-[50px]  flex flex-row items-center">
          <div className="flex w-[300px] flex-shrink-0 flex-col items-center justify-center">
            <Image url={templateDate.imageUrl}/>
          </div>
          <div className="ml-[26px] flex min-w-0 flex-1 flex-col">
            <div className="text-3xl leading-[52px] font-bold break-words text-gray-950">
              {templateDate.title}
            </div>
            <div className="mt-[25px] flex flex-row items-center h-[48px]">
              <Badge variant="normal" color="weak" size="small">
                {templateDate.tag}
              </Badge>
              <div className="mx-[15px] h-[6px] w-[6px] rounded-full bg-gray-400" />
              <div className="text-xl text-gray-700">{templateDate.date}</div>
            </div>
          </div>
        </div>
      </div>
    </a>
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
    <div className="flex h-full w-full flex-col my-[70px]">
      <div className="text-5xl leading-[72px] font-bold text-gray-950">{templateDate.title}</div>
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

---


