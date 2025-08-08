### 2.4 图标使用规范

仅在用户要求生成车控场景时使用以下自定义图标，并且强制只能使用自定义图标，如果不合适则使用`lucide-react` 图标库中的图标，注意import导入具体的图标。车控场景之外的前端代码均不使用图标。

#### 图标组件使用方法

##### 1. 导入组件

```tsx
import { 
  SeatHeating,
  FrontWindshieldHeating,
} from '@/components/icons/icons/index';
```

##### 2. 组件用法

直接以组件方式使用：

```tsx
<FrontWindshieldHeating />
```

可传入 `color` 和 `size` 参数调整颜色和大小（默认当前颜色，72px）：

```tsx
<SeatHeating color="#EA5C4A" size={100} />
```

#### 图标列表

- **AcSwitch** - AC 开关
- **AirVolumn** - 风量
- **CirculationInside** - 内循环
- **CirculationMode** - 循环模式
- **AtmosphereLight** - 氛围灯亮度
- **BackWindowHeating** - 后窗加热
- **Cold** - 制冷
- **CirculationOutside** - 外循环
- **Defrost** - 除霜
- **FrontWindshieldHeating** - 除雾 前挡风玻璃加热
- **EcoSwitch** - 节能开关
- **MirrorHeating** - 后视镜加热
- **SeatVentilation** - 座椅通风
- **SeatHeating** - 座椅加热
- **ReadingLight** - 阅读灯
- **SeatMassage** - 座椅按摩
- **SteeringwheelAuto** - 方向盘/座椅加热自动调节
- **Fragrance** - 香氛
- **SteeringwheelHeating** - 方向盘加热
- **WindFeet** - 吹脚
- **WindFace** - 吹脸
- **SyncSwitch** - SYNC 开关
- **Switch** - 空调开关

---