# 车辆控制接口整合方案

## 接口分类说明

基于原有的64个小接口，按照功能模块进行整合，形成合理粒度的接口分类，实现接口间的解耦和功能聚合。

---

## 1. 车辆环境监测接口 (Vehicle Environment Monitoring API)

### 接口描述
获取车辆内外部环境数据，包括温度、湿度、空气质量等环境指标

### 功能说明
- 提供车内外温度监测
- 空气质量检测（PM2.5、CO2等）
- 环境舒适度评估

### 包含的原始接口 (6个)
1. 车内温度 - `Vehicle.VehInfo.CarControl.Hvac.ACIncarTemp`
2. 车内后排温度 - `Vehicle.VehInfo.CarControl.Hvac.RearACIncarTemp`
3. 车外温度 - `Vehicle.VehInfo.CarControl.Hvac.DspOtsdTemp`
4. 车内湿度 - `未实现`
5. 车内空气质量（PM2.5）- `未实现`
6. 车内二氧化碳 - `Vehicle.VehInfo.CarControl.Hvac.AcAirCo2Value`

---

## 2. 空调通用控制接口 (HVAC General Control API)

### 接口描述
管理空调系统的通用功能，包括制冷模式、同步控制、节能模式和空气循环等

### 功能说明
- A/C制冷功能控制
- 前后排同步控制
- 节能模式管理
- 空气循环模式设置

### 包含的原始接口 (4个)
1. A/C开关 - `Vehicle.VehInfo.CarControl.Hvac.FrontAcAc`
2. SYNC开关 - `Vehicle.VehInfo.CarControl.Hvac.FrontAcSync`
3. 节能空调（ECO）- `Vehicle.VehInfo.CarControl.Hvac.AcEcoMode`
4. 循环模式 - `Vehicle.VehInfo.CarControl.Hvac.AcAirRecycle`

---

## 3. 前排空调系统接口 (Front HVAC System API)

### 接口描述
管理前排空调系统的专属控制功能，包括开关、温度、风量和风向等

### 功能说明
- 前排空调基础开关控制
- 温度和自动模式设置
- 风量大小调节（手动/自动）
- 吹风方向控制

### 包含的原始接口 (6个)
1. 前排空调开关 - `Vehicle.VehInfo.CarControl.Hvac.FrontAcSw`
2. 前排自动空调开关 - `Vehicle.VehInfo.CarControl.Hvac.FrontAcAuto`
3. 主驾温度 - `Vehicle.VehInfo.CarControl.Hvac.FrontAcLeftTemp`
4. 前排空调自动风量 - `Vehicle.VehInfo.CarControl.Hvac.FrontAcWind`
5. 前排空调手动风量 - `Vehicle.VehInfo.CarControl.Hvac.FrontAcWindAuto`
6. 前排吹风方向 - `Vehicle.VehInfo.CarControl.Hvac.FrontAcWindDirection`

---

## 4. 后排空调控制接口 (Rear HVAC Control API)

### 接口描述
管理后排空调系统的独立控制功能

### 功能说明
- 后排空调独立开关控制
- 后排温度和风量调节
- 后排吹风方向设置

### 包含的原始接口 (6个)
1. 后排空调开关 - `Vehicle.VehInfo.CarControl.Hvac.RearAcSw`
2. 后排空调自动开关 - `Vehicle.VehInfo.CarControl.Hvac.RearAcAuto`
3. 后排空调温度 - `Vehicle.VehInfo.CarControl.Hvac.RearAcTemp`
4. 后排空调自动风量 - `Vehicle.VehInfo.CarControl.Hvac.RearAcWindAuto`
5. 后排空调手动风量 - `Vehicle.VehInfo.CarControl.Hvac.RearAcWind`
6. 后排吹风方向 - `Vehicle.VehInfo.CarControl.Hvac.RearAcWindDirection`

---

## 5. 车窗除雾除霜接口 (Defrost & Defogging Control API)

### 接口描述
管理车辆除雾、除霜和特殊制冷功能

### 功能说明
- 前后窗除雾除霜控制
- 急速制冷功能

### 包含的原始接口 (3个)
1. 车内除雾 - `Vehicle.VehInfo.CarControl.Hvac.AcDefrost`
2. 后窗加热 - `Vehicle.VehInfo.CarControl.Hvac.AcRearDefrost`
3. 急速制冷 - `未实现`

---

## 6. 方向盘座椅加热接口 (Steering Wheel & Seat Heating API)

### 接口描述
管理方向盘加热和前排座椅加热功能

### 功能说明
- 方向盘加热控制
- 前排座椅加热管理
- 自动加热调节

### 包含的原始接口 (4个)
1. 方向盘加热 - `Vehicle.VehInfo.CarControl.SeatAc.AcSteeringWheelHeat`
2. 方向盘加热自动调节 - `Vehicle.VehInfo.CarControl.Hvac.AcStrWhlSeatAutoHeat`
3. 主驾座椅加热状态 - `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow1LeftHeat`
4. 副驾座椅加热状态 - `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow1RightHeat`

---

## 7. 后排座椅加热接口 (Rear Seat Heating API)

### 接口描述
管理二排和三排座椅的加热功能

### 功能说明
- 二排座椅加热控制
- 三排座椅加热管理
- 多座椅独立控制

### 包含的原始接口 (6个)
1. 二排左座椅加热状态 - `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow2LeftHeat`
2. 二排右座椅加热状态 - `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow2RightHeat`
3. 二排中间座椅加热状态 - `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow2MiddleHeat`
4. 三排左座椅加热状态 - `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow3LeftHeat`
5. 三排右座椅加热状态 - `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow3RightHeat`
6. 三排中间座椅加热状态 - `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow3MiddleHeat`

---

## 8. 座椅通风系统接口 (Seat Ventilation System API)

### 接口描述
管理前排和后排座椅的通风功能

### 功能说明
- 前排座椅通风控制
- 后排座椅通风管理
- 独立通风调节

### 包含的原始接口 (4个)
1. 座椅通风（主驾）- `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow1LeftVent`
2. 座椅通风（副驾）- `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow1RightVent`
3. 座椅通风（二排左）- `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow2LeftVent`
4. 座椅通风（二排右）- `Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow2RightVent`

---

## 9. 座椅按摩控制接口 (Seat Massage Control API)

### 接口描述
管理座椅按摩功能的开关和基础设置

### 功能说明
- 多座椅按摩开关控制
- 按摩功能启停管理

### 包含的原始接口 (4个)
1. 主驾座椅按摩开关 - `Vehicle.VehInfo.CarControl.Massage.Switch_FL`
2. 副驾座椅按摩开关 - `Vehicle.VehInfo.CarControl.Massage.Switch_FR`
3. 二排左座椅按摩开关 - `Vehicle.VehInfo.CarControl.Massage.Switch_SecL`
4. 二排右座椅按摩开关 - `Vehicle.VehInfo.CarControl.Massage.Switch_SecR`

---

## 10. 座椅按摩模式接口 (Seat Massage Mode API)

### 接口描述
管理座椅按摩的模式和强度设置

### 功能说明
- 按摩模式选择
- 按摩强度调节
- 个性化按摩设置

### 包含的原始接口 (8个)
1. 主驾按摩模式 - `Vehicle.VehInfo.CarControl.Massage.Mode_FL`
2. 副驾按摩模式 - `Vehicle.VehInfo.CarControl.Massage.Mode_FR`
3. 二排左按摩模式 - `Vehicle.VehInfo.CarControl.Massage.Mode_SecL`
4. 二排右按摩模式 - `Vehicle.VehInfo.CarControl.Massage.Mode_SecR`
5. 主驾按摩强度 - `Vehicle.VehInfo.CarControl.Massage.Strength_FL`
6. 副驾按摩强度 - `Vehicle.VehInfo.CarControl.Massage.Strength_FR`
7. 二排左按摩强度 - `Vehicle.VehInfo.CarControl.Massage.Strength_SecL`
8. 二排右按摩强度 - `Vehicle.VehInfo.CarControl.Massage.Strength_SecR`

---

## 11. 热石按摩系统接口 (Hot Stone Massage System API)

### 接口描述
管理座椅热石按摩的高级功能

### 功能说明
- 热石按摩开关控制
- 多座椅热石按摩管理
- 高级按摩体验

### 包含的原始接口 (4个)
1. 主驾热石按摩开关 - `Vehicle.VehInfo.CarControl.Massage.HotStone_FL`
2. 副驾热石按摩开关 - `Vehicle.VehInfo.CarControl.Massage.HotStone_FR`
3. 二排左热石按摩开关 - `Vehicle.VehInfo.CarControl.Massage.HotStone_SecL`
4. 二排右热石按摩开关 - `Vehicle.VehInfo.CarControl.Massage.HotStone_SecR`

---

## 12. 车内照明系统接口 (Interior Lighting System API)

### 接口描述
管理车内各个位置的阅读灯和照明设备控制

### 功能说明
- 多排座椅阅读灯独立控制
- 支持三排座椅布局的完整照明管理
- 个性化照明设置

### 包含的原始接口 (7个)
1. 主驾阅读灯开关状态 - `Vehicle.VehInfo.CarControl.Light.ReadingLight_FL`
2. 副驾阅读灯开关状态 - `Vehicle.VehInfo.CarControl.Light.ReadingLight_FR`
3. 二排左阅读灯开关状态 - `Vehicle.VehInfo.CarControl.Light.ReadingLight_SecL`
4. 二排右阅读灯开关状态 - `Vehicle.VehInfo.CarControl.Light.ReadingLight_SecR`
5. 三排左阅读灯开关状态 - `Vehicle.VehInfo.CarControl.Light.ReadingLight_ThirdL`
6. 三排右阅读灯开关状态 - `Vehicle.VehInfo.CarControl.Light.ReadingLight_ThirdR`
7. 三排中阅读灯 - `Vehicle.VehInfo.CarControl.Light.ReadingLight_ThirdM`

---

## 13. 车内香氛系统接口 (Vehicle Fragrance System API)

### 接口描述
管理车内香氛系统的开关控制和香型选择功能

### 功能说明
- 香氛系统开关控制
- 多种香型选择和切换
- 香氛浓度和模式管理

### 包含的原始接口 (2个)
1. 香氛开关 - `Vehicle.VehInfo.CarControl.Perfume.PerfumeSw`
2. 当前使用香型 - `Vehicle.VehInfo.CarControl.Perfume.PerfumeSelectChannel`

---

## 接口整合优势

### 1. 功能聚合
- 将相关功能集中管理，减少接口调用次数
- 提供更完整的功能视图

### 2. 系统解耦
- 按功能模块划分，降低系统间依赖
- 便于独立开发和维护

### 3. 扩展性强
- 新功能可以轻松添加到对应模块
- 支持渐进式功能升级

### 4. 调用效率
- 减少网络请求次数
- 提供批量操作能力

---

## 总结

原有64个小接口整合为13个功能接口：
- **环境监测接口**: 6个原始接口
- **空调通用控制接口**: 4个原始接口
- **前排空调系统接口**: 6个原始接口
- **后排空调控制接口**: 6个原始接口
- **车窗除雾除霜接口**: 3个原始接口
- **方向盘座椅加热接口**: 4个原始接口
- **后排座椅加热接口**: 6个原始接口
- **座椅通风系统接口**: 4个原始接口
- **座椅按摩控制接口**: 4个原始接口
- **座椅按摩模式接口**: 8个原始接口
- **热石按摩系统接口**: 4个原始接口
- **照明系统接口**: 7个原始接口
- **香氛系统接口**: 2个原始接口
 