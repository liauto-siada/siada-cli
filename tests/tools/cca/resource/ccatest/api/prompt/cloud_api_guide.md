## 云端API使用指南

**适用场景：黄历、日历、汇率、星座、股票、交通限行、每日单词、古诗词查询**

### 使用步骤

#### 1. 获取API定义
```typescript
api_knowledge_search({ query: "黄历查询API almanacQueryTool" })
// 从返回的schema中提取apiUrl参数（必传）
```

#### 2. 搜索卡片模板
```typescript
card_template_search({ query: "黄历卡片" })
```

#### 3. 数据替换规则
如果找到对应模板：
- **仅替换数据**：只能替换模板中的数据内容
- **保持UI布局**：不得修改UI布局、样式、组件结构
- **保持数据数量**：不得增加或减少数据项数量

### 组件结构规范

**⚠️ 组件命名与结构：**
- **主组件命名**：必须使用与文件名相符的组件名（如`PoetryCard.tsx`中导出`PoetryCard`）
- **避免App命名**：不要将主组件命名为`App`，因为模板中已有`App`组件
- **正确导出**：必须使用`export default 组件名`导出主组件
- **组件结构**：主组件应为无参数组件，内部可包含子组件
- **根元素宽度**：主组件根元素宽度应设为`w-[813px]`，适配模板
- **不要包含**：不要包含外层容器、标题区域、滚动区域，这些由模板提供

**✅ 正确的组件结构示例：**
```typescript
// 在PoetryCard.tsx文件中
const PoetryCard = () => {  // 主组件名与文件名相符
  const [data, setData] = useState(...);  // 状态管理
  
  useEffect(() => {
    // API调用逻辑
  }, []);
  
  return (
    <div className="w-[813px] p-0 rounded-[20px]">
      {/* 内容区域 */}
    </div>
  );
};

export default PoetryCard;  // 正确导出主组件
```

### 数据处理规范

**⚠️ 默认数据处理：**
- **使用空数据**：初始状态使用空值（`""`、`[]`、`{}`、`0`等），不要使用假数据
- **保留字段结构**：保持数据结构完整，只将内容设为空
- **禁用加载提示**：不要显示"正在加载"、"加载中"等提示文字
- **直接过渡**：从空数据状态直接过渡到API返回数据，无需中间状态

**✅ 正确的默认数据示例：**
```typescript
// 字符串类型字段
const [text, setText] = useState<string>("");

// 数组类型字段
const [items, setItems] = useState<Item[]>([]);

// 对象类型字段 - 保留结构
const [data, setData] = useState<DataType>({
  title: "",
  description: "",
  value: 0,
  items: []
});

// 有默认结构要求的数组
const [poetryList, setPoetryList] = useState<PoetryProps[]>([
  {
    id: "",
    title: "",
    author: "",
    content: [""]
  }
]);
```

### API调用规范

**⚠️ 强制要求：必须使用carapi-js-lib中定义的接口，严禁直接使用fetch调用！**

#### 正确的调用方式：
```typescript
import { GetAlmanacInfo, GetCalendarInfo, GetExchangeRateInfo, 
         GetHoroscopeInfo, GetStockInfo, GetTrafficRestrictionInfo,
         GetWordInfo, GetPoetryInfo } from 'carapi-js-lib';

// ✅ 正确：使用封装好的接口
const result = await GetAlmanacInfo({
  refText: "查询今天的黄历",
  apiUrl: apiUrlFromKnowledgeSearch  // 必传
});

// ✅ 正确：每日单词接口
const wordResult = await GetWordInfo({
  vector: "帮我生成苹果的单词",
  apiUrl: apiUrlFromKnowledgeSearch,  // 必传
  topK: 2
});

// ✅ 正确：古诗词接口
const poetryResult = await GetPoetryInfo({
  vector: "帮我生成经典古诗词",
  apiUrl: apiUrlFromKnowledgeSearch,  // 必传
  topK: 2
});
```

#### 错误的调用方式：
```typescript
// ❌ 错误：严禁直接使用fetch
const response = await fetch(apiUrl, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ refText: '查询今天黄历', apiUrl: apiUrl })
});
```

### 重要提醒
- **接口封装**：carapi-js-lib已正确处理请求方法、头部、参数编码等细节
- **统一标准**：使用封装接口确保所有API调用的一致性和可靠性
- **错误处理**：封装接口包含完善的错误处理和类型检查
- **必传参数**：`apiUrl` 参数必须从 `api_knowledge_search` 的schema中获取
- **模板匹配**：找到模板时严格按模板设计，只替换数据
- **默认数据**：始终使用空数据作为默认值，不要使用"正在加载"等提示
- **组件命名**：组件名必须与文件名相符，不要使用与模板冲突的名称
- **股票**：股票上涨时使用红色，下跌时使用绿色