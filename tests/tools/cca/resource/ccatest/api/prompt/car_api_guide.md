### 车端接口使用和车端卡片生成规范 

#### 1. 获取API定义
- 编写车端功能前，**必须**先用`knowledgeSearchTool`工具搜索获取API定义，可以传入参数选择召回的API数目。
- 获取定义后,**必须**使用`vehicleControlCardGenerator`工具生成卡片代码，`不要`自行生成，其中`apiImports`需要传入完整的导入语句。
**车控卡片工具使用：**
- **必须调用**`vehicleControlCardGenerator`工具
- **必须**传入三个参数：`title`（卡片标题）、`cardName`（组件名称）、`data`（车控功能配置数组）
- **在传入data参数时先调用knowledgeSearchTool获取实际的api和api定义，不要自行杜撰api**
车控功能配置支持三种类型：显示类（仅显示信息）、开关类（控制开关）、调节类（调节数值）
#### 2. 技术实现
- **库导入**：`import { get_front_hvac_system } from 'carapi-js-lib'`
- **忽略TS**：添加`// @ts-ignore`注释

#### 3. 数据自动刷新
**重要**：车端状态卡片必须实现数据自动刷新，确保显示最新状态，刷新频率需要符和用户要求，如果没有指定默认为60s。

#### 4. API调用规范
**重要**：API返回对象格式，需要从`response.data`中提取实际数据。

#### 5. 代码示例
```typescript
// @ts-ignore
import { get_front_hvac_system } from 'carapi-js-lib'

// ✅ 正确 - 分别获取字段并从data中提取
useEffect(() => {
  const fetchData = async () => {
    const [frontAcSwResult, frontAcAutoResult, frontAcLeftTempResult] = await Promise.all([
      get_front_hvac_system('FrontAcSw'),
      get_front_hvac_system('FrontAcAuto'),
      get_front_hvac_system('FrontAcLeftTemp')
    ])
    
    const newData = {
      FrontAcSw: frontAcSwResult?.success && frontAcSwResult?.data ? frontAcSwResult.data.FrontAcSw : null,
      FrontAcAuto: frontAcAutoResult?.success && frontAcAutoResult?.data ? frontAcAutoResult.data.FrontAcAuto : null,
      FrontAcLeftTemp: frontAcLeftTempResult?.success && frontAcLeftTempResult?.data ? frontAcLeftTempResult.data.FrontAcLeftTemp : null
    }
    
    if (JSON.stringify(newData) !== JSON.stringify(data)) {
      setData(newData)
    }
  }
  fetchData()
  const interval = setInterval(fetchData, 5000)
  return () => clearInterval(interval)
}, [])

// ❌ 错误 - 使用all参数
const result = await get_front_hvac_system('all')

// ❌ 错误 - 未从data中提取
const result = await get_front_hvac_system('FrontAcSw')
setData(result) // 错误：应该从result.data中提取

// ❌ 错误 - REST调用
const response = await fetch('/api/car/front-hvac')
```
#### 6. 开关类数据处理
对所有开关类字段，统一使用类似 `Number(obj[key]) === 1` 判断"开启"，`obj[key] === null` 判断"无功能"。适用于 UI 显示和统计，防止类型不一致问题。

#### 7. 图标使用规则
**【重要】只能使用以下指定的图标名称，严禁使用其他图标名称！**

**可用图标列表（必须严格使用以下名称）：**
- AcSwitch（AC开关）
- AirVolumn（风量）
- CirculationInside（内循环）
- CirculationMode（循环模式）
- AtmosphereLight（氛围灯亮度）
- BackWindowHeating（后窗加热）
- Cold（制冷）
- CirculationOutside（外循环）
- Defrost（除霜）
- FrontWindshieldHeating（除雾前挡风玻璃加热）
- EcoSwitch（节能开关）
- MirrorHeating（后视镜加热）
- SeatVentilation（座椅通风）
- SeatHeating（座椅加热）
- ReadingLight（阅读灯）
- SeatMassage（座椅按摩）
- SteeringwheelAuto（方向盘/座椅加热自动调节）
- Fragrance（香氛）
- SteeringwheelHeating（方向盘加热）
- WindFeet（吹脚）
- WindFace（吹脸）
- SyncSwitch（SYNC开关）
- Switch（空调开关）

**使用要求：**
1. 图标名称必须完全匹配上述列表，区分大小写
2. 不允许使用任何其他图标名称（如Thermometer、Power等）
3. 如果没有合适的图标，优先选择最接近功能的图标，例如香氛开关和香型选择的图标就都选择香氛图标即可
4. 每个功能都必须指定一个图标
