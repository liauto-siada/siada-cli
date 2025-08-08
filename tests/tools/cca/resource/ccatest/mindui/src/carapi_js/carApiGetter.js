import callbackManager from './callbackManager.js';
import { getKeyValue } from './utils.js';
import { getCachedValue, addPendingRequest, removePendingRequest } from './carApiState.js';
import * as log from './log.js';

const CaidID = "card"

let g_mockData = false;

export function mockData(isMock) {
    g_mockData = isMock;
}

export function getMockData() {
    return g_mockData;
}

export function createAsyncGetter(key, timeout = 5000) {
    return function getValue() {
        return new Promise((resolve, reject) => {
            log.i(`[getter] 开始获取: ${key}`);
            // 1. 检查缓存
            const cachedValue = getCachedValue(key);
            if (cachedValue !== undefined && cachedValue !== null) {
                log.i(`[getter] 直接从缓存返回: ${key} : ${cachedValue}`);
                return resolve(cachedValue);
            }

            // 2. 确保监听
            callbackManager.ensureListener(CaidID, key);

            // 3. 挂起请求
            const requestInfo = {};
            const timeoutId = setTimeout(() => {
                removePendingRequest(key, requestInfo);
                resolve(null);
            }, timeout);
            Object.assign(requestInfo, { resolve, reject, timeoutId });
            addPendingRequest(key, requestInfo);

            // 4. 触发一次数据获取
            getKeyValue(key);

            // FIXME: 模拟数据，正式上线时需删除!!!
            if (getMockData()) {
                setTimeout(() => {
                    callbackManager.onWidgetAgentCallback(CaidID, key, JSON.stringify({ value: defaultValueMap[key] }));
                }, 1000);
            }
        });
    }
}

// PART_I
export const ACIncarTempKey = "Vehicle.VehInfo.CarControl.Hvac.ACIncarTemp"; // 车内温度
export const RearACIncarTempKey = "Vehicle.VehInfo.CarControl.Hvac.RearACIncarTemp"; // 车内后排温度
export const DspOtsdTempKey = "Vehicle.VehInfo.CarControl.Hvac.DspOtsdTemp"; // 车外温度
const AcAirCo2ValueKey = "Vehicle.VehInfo.CarControl.Hvac.AcAirCo2Value"; // 车内二氧化碳
const FrontAcSwKey = "Vehicle.VehInfo.CarControl.Hvac.FrontAcSw"; // 前排空调开关
const FrontAcAutoKey = "Vehicle.VehInfo.CarControl.Hvac.FrontAcAuto"; // 前排自动空调开关
const FrontAcAcKey = "Vehicle.VehInfo.CarControl.Hvac.FrontAcAc"; // A/C开关
const FrontAcSyncKey = "Vehicle.VehInfo.CarControl.Hvac.FrontAcSync"; // SYNC开关
const FrontAcLeftTempKey = "Vehicle.VehInfo.CarControl.Hvac.FrontAcLeftTemp"; // 主驾温度
const FrontAcRightTempKey = "Vehicle.VehInfo.CarControl.Hvac.FrontAcRightTemp"; // 副驾温度
const FrontAcWindKey = "Vehicle.VehInfo.CarControl.Hvac.FrontAcWind"; // 前排空调手动风量
const FrontAcWindAutoKey = "Vehicle.VehInfo.CarControl.Hvac.FrontAcWindAuto"; // 前排空调自动风量
const FrontAcWindDirectionKey = "Vehicle.VehInfo.CarControl.Hvac.FrontAcWindDirection"; // 前排吹风方向（除霜、吹脸、吹脚）
const AcAirRecycleKey = "Vehicle.VehInfo.CarControl.Hvac.AcAirRecycle"; // 循环模式
const AcDefrostKey = "Vehicle.VehInfo.CarControl.Hvac.AcDefrost"; // 车内除雾
const AcRearDefrostKey = "Vehicle.VehInfo.CarControl.Hvac.AcRearDefrost"; // 后窗加热
const RearAcSwKey = "Vehicle.VehInfo.CarControl.Hvac.RearAcSw"; // 后排空调开关
const RearAcAutoKey = "Vehicle.VehInfo.CarControl.Hvac.RearAcAuto"; // 后排空调自动开关
const RearAcTempKey = "Vehicle.VehInfo.CarControl.Hvac.RearAcTemp"; // 后排空调温度
const RearAcWindAutoKey = "Vehicle.VehInfo.CarControl.Hvac.RearAcWindAuto"; // 后排空调自动风量
const RearAcWindKey = "Vehicle.VehInfo.CarControl.Hvac.RearAcWind"; // 后排空调手动风量
const RearAcWindDirectionKey = "Vehicle.VehInfo.CarControl.Hvac.RearAcWindDirection"; // 后排吹风方向：吹脸、吹脚
const AcSteeringWheelHeatKey = "Vehicle.VehInfo.CarControl.SeatAc.AcSteeringWheelHeat"; // 方向盘加热
const AcStrWhlSeatAutoHeatKey = "Vehicle.VehInfo.CarControl.Hvac.AcStrWhlSeatAutoHeat"; // 方向盘座椅加热自动调节
const SeatAcRow1LeftVentKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow1LeftVent"; // 座椅通风（主驾）
const SeatAcRow1RightVentKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow1RightVent"; // 座椅通风（副驾）
const SeatAcRow2LeftVentKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow2LeftVent"; // 座椅通风（二排左）
const SeatAcRow2RightVentKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow2RightVent"; // 座椅通风（二排右）
const SeatAcRow1LeftHeatKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow1LeftHeat"; // 主驾座椅加热状态
const SeatAcRow1RightHeatKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow1RightHeat"; // 副驾座椅加热状态
const SeatAcRow2LeftHeatKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow2LeftHeat"; // 二排左座椅加热状态
const SeatAcRow2RightHeatKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow2RightHeat"; // 二排右座椅加热状态
const SeatAcRow2MiddleHeatKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow2MiddleHeat"; // 二排中间座椅加热状态
const SeatAcRow3LeftHeatKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow3LeftHeat"; // 三排左座椅加热状态
const SeatAcRow3RightHeatKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow3RightHeat"; // 三排右座椅加热状态
const SeatAcRow3MiddleHeatKey = "Vehicle.VehInfo.CarControl.SeatAc.SeatAcRow3MiddleHeat"; // 三排中间座椅加热状态
const ReadingLight_FLKey = "Vehicle.VehInfo.CarControl.Light.ReadingLight_FL"; // 主驾阅读灯开关状态
const ReadingLight_FRKey = "Vehicle.VehInfo.CarControl.Light.ReadingLight_FR"; // 副驾阅读灯开关状态
const ReadingLight_SecLKey = "Vehicle.VehInfo.CarControl.Light.ReadingLight_SecL"; // 二排左阅读灯开关状态
const ReadingLight_SecRKey = "Vehicle.VehInfo.CarControl.Light.ReadingLight_SecR"; // 二排右阅读灯开关状态
const ReadingLight_ThirdLKey = "Vehicle.VehInfo.CarControl.Light.ReadingLight_ThirdL"; // 三排左阅读灯开关状态
const ReadingLight_ThirdRKey = "Vehicle.VehInfo.CarControl.Light.ReadingLight_ThirdR"; // 三排右阅读灯开关状态
const ReadingLight_ThirdMKey = "Vehicle.VehInfo.CarControl.Light.ReadingLight_ThirdM"; // 三排中阅读灯
const AcEcoModeKey = "Vehicle.VehInfo.CarControl.Hvac.AcEcoMode"; // 节能空调（ECO）
const PerfumeSwKey = "Vehicle.VehInfo.CarControl.Perfume.PerfumeSw"; // 香氛开关
const PerfumeSelectChannelKey = "Vehicle.VehInfo.CarControl.Perfume.PerfumeSelectChannel"; // 当前使用香型
const PerfumeInfoKey = "Vehicle.VehInfo.CarControl.Perfume.Information"; // 香氛信息
const MassageSwitch_FLKey = "Vehicle.VehInfo.CarControl.Massage.Switch_FL"; // 主驾座椅按摩开关
const MassageSwitch_FRKey = "Vehicle.VehInfo.CarControl.Massage.Switch_FR"; // 副驾座椅按摩开关
const MassageSwitch_SecLKey = "Vehicle.VehInfo.CarControl.Massage.Switch_SecL"; // 二排左座椅按摩开关
const MassageSwitch_SecRKey = "Vehicle.VehInfo.CarControl.Massage.Switch_SecR"; // 二排右座椅按摩开关
const MassageMode_FLKey = "Vehicle.VehInfo.CarControl.Massage.Mode_FL"; // 主驾按摩模式
const MassageMode_FRKey = "Vehicle.VehInfo.CarControl.Massage.Mode_FR"; // 副驾按摩模式
const MassageMode_SecLKey = "Vehicle.VehInfo.CarControl.Massage.Mode_SecL"; // 二排左按摩模式
const MassageMode_SecRKey = "Vehicle.VehInfo.CarControl.Massage.Mode_SecR"; // 二排右按摩模式
const MassageStrength_FLKey = "Vehicle.VehInfo.CarControl.Massage.Strength_FL"; // 主驾按摩强度
const MassageStrength_FRKey = "Vehicle.VehInfo.CarControl.Massage.Strength_FR"; // 副驾按摩强度
const MassageStrength_SecLKey = "Vehicle.VehInfo.CarControl.Massage.Strength_SecL"; // 二排左按摩强度
const MassageStrength_SecRKey = "Vehicle.VehInfo.CarControl.Massage.Strength_SecR"; // 二排右按摩强度
const MassageHotStone_FLKey = "Vehicle.VehInfo.CarControl.Massage.HotStone_FL"; // 主驾热石按摩开关
const MassageHotStone_FRKey = "Vehicle.VehInfo.CarControl.Massage.HotStone_FR"; // 副驾热石按摩开关
const MassageHotStone_SecLKey = "Vehicle.VehInfo.CarControl.Massage.HotStone_SecL"; // 二排左热石按摩开关
const MassageHotStone_SecRKey = "Vehicle.VehInfo.CarControl.Massage.HotStone_SecR"; // 二排右热石按摩开关

// PART_II
const VehInfo_SpeedKey = "CreateWidget.VehInfo.Speed"; // 车速
const VehicleGearShift_Key = "Vehicle.VehInfo.CarControl.VehicleBody.VehicleGearShift"; // 档位
const BindTrip_Key = "Vehicle.VehInfo.CarCenter.Trip.BindTrip"; // 绑定行程
const EnduranceCondition_Key = "Vehicle.VehInfo.CarCenter.BasicState.EnduranceCondition"; // 续航显示工况
const CltcPureEvMileage_Key = "Vehicle.VehInfo.CarCenter.Endurance.CltcPureEvMileage"; // 纯电续航CLTC
const WltcPureEvMileage_Key = "Vehicle.VehInfo.CarCenter.Endurance.WltcPureEvMileage"; // 纯电续航WLTC
const CltcReevMileage_Key = "Vehicle.VehInfo.CarCenter.Endurance.CltcReevMileage"; // CltcReevMileage
const WltcReevMileage_Key = "Vehicle.VehInfo.CarCenter.Endurance.WltcReevMileage"; // WltcReevMileage
const MileageFinalResult_Key = "Vehicle.Cabin.CLTC.MileageFinalResult"; // MileageFinalResult
const PowerPercent_Key = "Vehicle.VehInfo.CarCenter.BasicState.PowerPercent"; // PowerPercent
const DriveMode_Key = "Vehicle.VehInfo.CarSettings.DriveSettings.DriveMode"; // DriveMode
const DrivingMode_Key = "Vehicle.VehInfo.CarSettings.DriveSettings.DrivingMode"; // DrivingMode
const AirSuspension_Key = "Vehicle.VehInfo.CarSettings.DriveSettings.AirSuspension"; // AirSuspension
const SpringSuspension_Key = "Vehicle.VehInfo.CarSettings.DriveSettings.SpringSuspension"; // SpringSuspension
const Altitude_Key = "Vehicle.Master.Compass.Height.Altitude"; // Altitude
const SuspensionAdjustment_Key = "Vehicle.VehInfo.CarSettings.DriveSettings.SuspensionAdjustment"; // SuspensionAdjustment
const SuspensionHeight_Key = "Vehicle.VehInfo.CarSettings.DriveSettings.SuspensionHeight"; // SuspensionHeight
const LowSuspension_Key = "Vehicle.VehInfo.CarSettings.DriveSettings.LowSuspension"; // LowSuspension
const TurnRound_Key = "Vehicle.VehInfo.CarSettings.DriveSettings.TurnRound"; // TurnRound
const EnergyRecovery_Key = "Vehicle.VehInfo.CarSettings.DriveSettings.EnergyRecovery"; // EnergyRecovery
const VESS_Key = "Vehicle.VehInfo.CarSettings.Maintain.VESS"; // VESS
const RangeExtenderTemp_Key = "Vehicle.VehInfo.CarCenter.BasicState.RangeExtenderTemp"; // RangeExtenderTemp
const FridgeDoor_Key = "Vehicle.VehInfo.ExtDevices.Fridge.Door"; // FridgeDoor
const FridgeCoolTmp_Key = "Vehicle.VehInfo.ExtDevices.Fridge.CoolTmp"; // CoolTmp
const FridgeHotTmp_Key = "Vehicle.VehInfo.ExtDevices.Fridge.HotTmp"; // HotTmp
const FridgeWorkMode_Key = "Vehicle.VehInfo.ExtDevices.Fridge.WorkMode"; // WorkMode
const ChargeStatus_Key = "Vehicle.VehInfo.CarCenter.ChargeManagement.ChargeStatus"; // ChargeStatus
const ChargingStartTime_Key = "Vehicle.VehInfo.CarCenter.ChargeManagement.ChargingStartTime"; // ChargingStartTime
const MSG_RESSInterVolt_Key = "Vehicle.Powertrain.Battery.MSG_RESSInterVolt"; // MSG_RESSInterVolt
const DischargeStatus_Key = "Vehicle.Powertrain.Battery.DischargeStatus"; // DischargeStatus
const ChargeRemainTime_Key = "Vehicle.VehInfo.CarCenter.ChargeManagement.ChargeRemainTime"; // ChargeRemainTime
const ChargeLimit_Key = "Vehicle.VehInfo.CarCenter.ChargeManagement.ChargeLimit"; // ChargeLimit
const ReserveSwitchStatus_Key = "Vehicle.VehInfo.CarCenter.ChargeManagement.ReserveSwitchStatus"; // ReserveSwitchStatus
const ChargeType_Key = "Vehicle.VehInfo.CarCenter.ChargeManagement.ChargeType"; // ChargeType
const OGCChargeVoltage_Key = "Vehicle.Powertrain.Battery.OGCChargeVoltage"; // OGCChargeVoltage
const OGCChargeCurrent_Key = "Vehicle.Powertrain.Battery.OGCChargeCurrent"; // OGCChargeCurrent
const ACChargeVoltage_Key = "Vehicle.Powertrain.Battery.ACChargeVoltage"; // ACChargeVoltage
const ACChargeCurrent_Key = "Vehicle.Powertrain.Battery.ACChargeCurrent"; // ACChargeCurrent
const WarmSwitchStatus_Key = "Vehicle.VehInfo.CarCenter.ChargeManagement.WarmSwitchStatus"; // WarmSwitchStatus

const InCarHumidityKey = "Vehicle.VehInfo.CarControl.Hvac.InCarHumidity"; // 车内相对湿度
const AcAirPm25ValueKey = "Vehicle.VehInfo.CarControl.Hvac.AcAirPm25Value"; // PM2.5的value值、空调净化运行时
const AcMaxColdKey = "Vehicle.VehInfo.CarControl.Hvac.AcMaxCold"; // 空调 急速制冷
const TempControlKey = "Vehicle.VehInfo.CarCenter.Trip.TempControl"; // 自动在途温控状态(自动预热预冷)
const ManuTempAdjStatusKey = "Vehicle.VehInfo.CarCenter.ChargeManagement.ManuTempAdjStatus"; // 手动温控状态（手动预热预冷）
const AmbientLightSwitchKey = "Vehicle.VehInfo.CarSettings.Lamp.AmbientLightSwitch"; // 氛围灯开启状态
const AmbientLightBrightnessKey = "Vehicle.VehInfo.CarSettings.Lamp.AmbientLightBrightness"; // 氛围灯亮度
const DestinationPoiNameKey = "Vehicle.Travel.OneMap.Navi.DestinationPoiName"; // 目的地名称
const RemainTimeKey = "Vehicle.Travel.OneMap.Navi.RemainTime"; // 剩余时间
const ArrivalTimeKey = "Vehicle.Travel.OneMap.Navi.ArrivalTime"; // 到达时间,模拟VKB信号key，保持收发信数据流程统一
const DriverMassageStatusKey = "CreateAgent.CarControl.Massage.Status_FL"; // 主驾座椅按摩状态
const PassengerMassageStatusKey = "CreateAgent.CarControl.Massage.Status_FR"; // 副驾座椅按摩状态
const SecondRowLeftMassageStatusKey = "CreateAgent.CarControl.Massage.Status_SecL"; // 二排左座椅按摩状态
const SecondRowRightMassageStatusKey = "CreateAgent.CarControl.Massage.Status_SecR"; // 二排右座椅按摩状态

// 批量生成 getter 并导出
export const getACIncarTemp = createAsyncGetter(ACIncarTempKey);
export const getRearACIncarTemp = createAsyncGetter(RearACIncarTempKey);
export const getDspOtsdTemp = createAsyncGetter(DspOtsdTempKey);
export const getAcAirCo2Value = createAsyncGetter(AcAirCo2ValueKey);
export const getFrontAcSw = createAsyncGetter(FrontAcSwKey);
export const getFrontAcAuto = createAsyncGetter(FrontAcAutoKey);
export const getFrontAcAc = createAsyncGetter(FrontAcAcKey);
export const getFrontAcSync = createAsyncGetter(FrontAcSyncKey);
export const getFrontAcLeftTemp = createAsyncGetter(FrontAcLeftTempKey);
export const getFrontAcRightTemp = createAsyncGetter(FrontAcRightTempKey);
export const getFrontAcWind = createAsyncGetter(FrontAcWindKey);
export const getFrontAcWindAuto = createAsyncGetter(FrontAcWindAutoKey);
export const getFrontAcWindDirection = createAsyncGetter(FrontAcWindDirectionKey);
export const getAcAirRecycle = createAsyncGetter(AcAirRecycleKey);
export const getAcDefrost = createAsyncGetter(AcDefrostKey);
export const getAcRearDefrost = createAsyncGetter(AcRearDefrostKey);
export const getRearAcSw = createAsyncGetter(RearAcSwKey);
export const getRearAcAuto = createAsyncGetter(RearAcAutoKey);
export const getRearAcTemp = createAsyncGetter(RearAcTempKey);
export const getRearAcWindAuto = createAsyncGetter(RearAcWindAutoKey);
export const getRearAcWind = createAsyncGetter(RearAcWindKey);
export const getRearAcWindDirection = createAsyncGetter(RearAcWindDirectionKey);
export const getAcSteeringWheelHeat = createAsyncGetter(AcSteeringWheelHeatKey);
export const getAcStrWhlSeatAutoHeat = createAsyncGetter(AcStrWhlSeatAutoHeatKey);
export const getSeatAcRow1LeftVent = createAsyncGetter(SeatAcRow1LeftVentKey);
export const getSeatAcRow1RightVent = createAsyncGetter(SeatAcRow1RightVentKey);
export const getSeatAcRow2LeftVent = createAsyncGetter(SeatAcRow2LeftVentKey);
export const getSeatAcRow2RightVent = createAsyncGetter(SeatAcRow2RightVentKey);
export const getSeatAcRow1LeftHeat = createAsyncGetter(SeatAcRow1LeftHeatKey);
export const getSeatAcRow1RightHeat = createAsyncGetter(SeatAcRow1RightHeatKey);
export const getSeatAcRow2LeftHeat = createAsyncGetter(SeatAcRow2LeftHeatKey);
export const getSeatAcRow2RightHeat = createAsyncGetter(SeatAcRow2RightHeatKey);
export const getSeatAcRow2MiddleHeat = createAsyncGetter(SeatAcRow2MiddleHeatKey);
export const getSeatAcRow3LeftHeat = createAsyncGetter(SeatAcRow3LeftHeatKey);
export const getSeatAcRow3RightHeat = createAsyncGetter(SeatAcRow3RightHeatKey);
export const getSeatAcRow3MiddleHeat = createAsyncGetter(SeatAcRow3MiddleHeatKey);
export const getReadingLight_FL = createAsyncGetter(ReadingLight_FLKey);
export const getReadingLight_FR = createAsyncGetter(ReadingLight_FRKey);
export const getReadingLight_SecL = createAsyncGetter(ReadingLight_SecLKey);
export const getReadingLight_SecR = createAsyncGetter(ReadingLight_SecRKey);
export const getReadingLight_ThirdL = createAsyncGetter(ReadingLight_ThirdLKey);
export const getReadingLight_ThirdR = createAsyncGetter(ReadingLight_ThirdRKey);
export const getReadingLight_ThirdM = createAsyncGetter(ReadingLight_ThirdMKey);
export const getAcEcoMode = createAsyncGetter(AcEcoModeKey);
export const getPerfumeSw = createAsyncGetter(PerfumeSwKey);
export const getPerfumeSelectChannel = createAsyncGetter(PerfumeSelectChannelKey);
export const getPerfumeInfo = createAsyncGetter(PerfumeInfoKey);
export const getMassageSwitch_FL = createAsyncGetter(MassageSwitch_FLKey);
export const getMassageSwitch_FR = createAsyncGetter(MassageSwitch_FRKey);
export const getMassageSwitch_SecL = createAsyncGetter(MassageSwitch_SecLKey);
export const getMassageSwitch_SecR = createAsyncGetter(MassageSwitch_SecRKey);
export const getMassageMode_FL = createAsyncGetter(MassageMode_FLKey);
export const getMassageMode_FR = createAsyncGetter(MassageMode_FRKey);
export const getMassageMode_SecL = createAsyncGetter(MassageMode_SecLKey);
export const getMassageMode_SecR = createAsyncGetter(MassageMode_SecRKey);
export const getMassageStrength_FL = createAsyncGetter(MassageStrength_FLKey);
export const getMassageStrength_FR = createAsyncGetter(MassageStrength_FRKey);
export const getMassageStrength_SecL = createAsyncGetter(MassageStrength_SecLKey);
export const getMassageStrength_SecR = createAsyncGetter(MassageStrength_SecRKey);
export const getMassageHotStone_FL = createAsyncGetter(MassageHotStone_FLKey);
export const getMassageHotStone_FR = createAsyncGetter(MassageHotStone_FRKey);
export const getMassageHotStone_SecL = createAsyncGetter(MassageHotStone_SecLKey);
export const getMassageHotStone_SecR = createAsyncGetter(MassageHotStone_SecRKey);
export const getDriverMassageStatus = createAsyncGetter(DriverMassageStatusKey);
export const getPassengerMassageStatus = createAsyncGetter(PassengerMassageStatusKey);
export const getSecondRowLeftMassageStatus = createAsyncGetter(SecondRowLeftMassageStatusKey);
export const getSecondRowRightMassageStatus = createAsyncGetter(SecondRowRightMassageStatusKey);

// PART_II getter
export const getVehInfo_Speed = createAsyncGetter(VehInfo_SpeedKey);
export const getVehicleGearShift = createAsyncGetter(VehicleGearShift_Key);
export const getBindTrip = createAsyncGetter(BindTrip_Key);
export const getEnduranceCondition = createAsyncGetter(EnduranceCondition_Key);
export const getCltcPureEvMileage = createAsyncGetter(CltcPureEvMileage_Key);
export const getWltcPureEvMileage = createAsyncGetter(WltcPureEvMileage_Key);
export const getCltcReevMileage = createAsyncGetter(CltcReevMileage_Key);
export const getWltcReevMileage = createAsyncGetter(WltcReevMileage_Key);
export const getMileageFinalResult = createAsyncGetter(MileageFinalResult_Key);
export const getPowerPercent = createAsyncGetter(PowerPercent_Key);
export const getDriveMode = createAsyncGetter(DriveMode_Key);
export const getDrivingMode = createAsyncGetter(DrivingMode_Key);
export const getAirSuspension = createAsyncGetter(AirSuspension_Key);
export const getSpringSuspension = createAsyncGetter(SpringSuspension_Key);
export const getAltitude = createAsyncGetter(Altitude_Key);
export const getSuspensionAdjustment = createAsyncGetter(SuspensionAdjustment_Key);
export const getSuspensionHeight = createAsyncGetter(SuspensionHeight_Key);
export const getLowSuspension = createAsyncGetter(LowSuspension_Key);
export const getTurnRound = createAsyncGetter(TurnRound_Key);
export const getEnergyRecovery = createAsyncGetter(EnergyRecovery_Key);
export const getVESS = createAsyncGetter(VESS_Key);
export const getRangeExtenderTemp = createAsyncGetter(RangeExtenderTemp_Key);
export const getFridgeDoor = createAsyncGetter(FridgeDoor_Key);
export const getFridgeCoolTmp = createAsyncGetter(FridgeCoolTmp_Key);
export const getFridgeHotTmp = createAsyncGetter(FridgeHotTmp_Key);
export const getFridgeWorkMode = createAsyncGetter(FridgeWorkMode_Key);
export const getChargeStatus = createAsyncGetter(ChargeStatus_Key);
export const getChargingStartTime = createAsyncGetter(ChargingStartTime_Key);
export const getMSG_RESSInterVolt = createAsyncGetter(MSG_RESSInterVolt_Key);
export const getDischargeStatus = createAsyncGetter(DischargeStatus_Key);
export const getChargeRemainTime = createAsyncGetter(ChargeRemainTime_Key);
export const getChargeLimit = createAsyncGetter(ChargeLimit_Key);
export const getReserveSwitchStatus = createAsyncGetter(ReserveSwitchStatus_Key);
export const getChargeType = createAsyncGetter(ChargeType_Key);
export const getOGCChargeVoltage = createAsyncGetter(OGCChargeVoltage_Key);
export const getOGCChargeCurrent = createAsyncGetter(OGCChargeCurrent_Key);
export const getACChargeVoltage = createAsyncGetter(ACChargeVoltage_Key);
export const getACChargeCurrent = createAsyncGetter(ACChargeCurrent_Key);
export const getWarmSwitchStatus = createAsyncGetter(WarmSwitchStatus_Key);

// 批量生成 getter 并导出
export const getInCarHumidity = createAsyncGetter(InCarHumidityKey);
export const getAcAirPm25Value = createAsyncGetter(AcAirPm25ValueKey);
export const getAcMaxCold = createAsyncGetter(AcMaxColdKey);
export const getTempControl = createAsyncGetter(TempControlKey);
export const getManuTempAdjStatus = createAsyncGetter(ManuTempAdjStatusKey);
export const getAmbientLightSwitch = createAsyncGetter(AmbientLightSwitchKey);
export const getAmbientLightBrightness = createAsyncGetter(AmbientLightBrightnessKey);
export const getDestinationPoiName = createAsyncGetter(DestinationPoiNameKey);
export const getRemainTime = createAsyncGetter(RemainTimeKey);

// 构建 type 到 getter 的映射表
export const getterMap = {
    ACIncarTemp: getACIncarTemp,
    RearACIncarTemp: getRearACIncarTemp,
    DspOtsdTemp: getDspOtsdTemp,
    AcAirCo2Value: getAcAirCo2Value,
    FrontAcSw: getFrontAcSw,
    FrontAcAuto: getFrontAcAuto,
    FrontAcAc: getFrontAcAc,
    FrontAcSync: getFrontAcSync,
    FrontAcLeftTemp: getFrontAcLeftTemp,
    FrontAcRightTemp: getFrontAcRightTemp,
    FrontAcWindDirection: getFrontAcWindDirection,
    AcAirRecycle: getAcAirRecycle,
    AcDefrost: getAcDefrost,
    AcRearDefrost: getAcRearDefrost,
    SeatAcRow1LeftVent: getSeatAcRow1LeftVent,
    SeatAcRow1RightVent: getSeatAcRow1RightVent,
    SeatAcRow2LeftVent: getSeatAcRow2LeftVent,
    SeatAcRow2RightVent: getSeatAcRow2RightVent,
    SeatAcRow2LeftHeat: getSeatAcRow2LeftHeat,
    SeatAcRow2RightHeat: getSeatAcRow2RightHeat,
    SeatAcRow2MiddleHeat: getSeatAcRow2MiddleHeat,
    SeatAcRow3LeftHeat: getSeatAcRow3LeftHeat,
    SeatAcRow3RightHeat: getSeatAcRow3RightHeat,
    SeatAcRow3MiddleHeat: getSeatAcRow3MiddleHeat,
    ReadingLight_FL: getReadingLight_FL,
    ReadingLight_FR: getReadingLight_FR,
    ReadingLight_SecL: getReadingLight_SecL,
    ReadingLight_SecR: getReadingLight_SecR,
    ReadingLight_ThirdL: getReadingLight_ThirdL,
    ReadingLight_ThirdR: getReadingLight_ThirdR,
    ReadingLight_ThirdM: getReadingLight_ThirdM,
    AcEcoMode: getAcEcoMode,
    PerfumeSw: getPerfumeSw,
    PerfumeSelectChannel: getPerfumeSelectChannel,
    Switch_FL: getMassageSwitch_FL,
    Switch_FR: getMassageSwitch_FR,
    Switch_SecL: getMassageSwitch_SecL,
    Switch_SecR: getMassageSwitch_SecR,
    Mode_FL: getMassageMode_FL,
    Mode_FR: getMassageMode_FR,
    Mode_SecL: getMassageMode_SecL,
    Mode_SecR: getMassageMode_SecR,
    Strength_FL: getMassageStrength_FL,
    Strength_FR: getMassageStrength_FR,
    Strength_SecL: getMassageStrength_SecL,
    Strength_SecR: getMassageStrength_SecR,
    HotStone_FL: getMassageHotStone_FL,
    HotStone_FR: getMassageHotStone_FR,
    HotStone_SecL: getMassageHotStone_SecL,
    HotStone_SecR: getMassageHotStone_SecR,
    Speed: getVehInfo_Speed,
    EnduranceCondition: getEnduranceCondition,
    CltcPureEvMileage: getCltcPureEvMileage,
    WltcPureEvMileage: getWltcPureEvMileage,
    CltcReevMileage: getCltcReevMileage,
    WltcReevMileage: getWltcReevMileage,
    MileageFinalResult: getMileageFinalResult,
    PowerPercent: getPowerPercent,
    DriveMode: getDriveMode,
    DrivingMode: getDrivingMode,
    AirSuspension: getAirSuspension,
    SpringSuspension: getSpringSuspension,
    Altitude: getAltitude,
    SuspensionAdjustment: getSuspensionAdjustment,
    SuspensionHeight: getSuspensionHeight,
    LowSuspension: getLowSuspension,
    TurnRound: getTurnRound,
    EnergyRecovery: getEnergyRecovery,
    VESS: getVESS,
    RangeExtenderTemp: getRangeExtenderTemp,
    Door: getFridgeDoor,
    CoolTmp: getFridgeCoolTmp,
    HotTmp: getFridgeHotTmp,
    WorkMode: getFridgeWorkMode,
    ChargeStatus: getChargeStatus,
    ChargingStartTime: getChargingStartTime,
    MSG_RESSInterVolt: getMSG_RESSInterVolt,
    DischargeStatus: getDischargeStatus,
    ChargeRemainTime: getChargeRemainTime,
    ChargeLimit: getChargeLimit,
    ReserveSwitchStatus: getReserveSwitchStatus,
    ChargeType: getChargeType,
    OGCChargeVoltage: getOGCChargeVoltage,
    OGCChargeCurrent: getOGCChargeCurrent,
    ACChargeVoltage: getACChargeVoltage,
    ACChargeCurrent: getACChargeCurrent,
    WarmSwitchStatus: getWarmSwitchStatus,
    InCarHumidity: getInCarHumidity,
    AcAirPm25Value: getAcAirPm25Value,
    AcDefrost: getAcDefrost,
    AcRearDefrost: getAcRearDefrost,
    AcMaxCold: getAcMaxCold,
    TempControl: getTempControl,
    ManuTempAdjStatus: getManuTempAdjStatus,
    AmbientLightSwitch: getAmbientLightSwitch,
    AmbientLightBrightness: getAmbientLightBrightness,
    FrontAcWindAuto: getFrontAcWindAuto,
    RearAcSw: getRearAcSw,
    RearAcAuto: getRearAcAuto,
    RearAcTemp: getRearAcTemp,
    RearAcWind: getRearAcWind,
    RearAcWindAuto: getRearAcWindAuto,
    RearAcWindDirection: getRearAcWindDirection,
    RearAcTemp: getRearAcTemp,
    AcSteeringWheelHeat: getAcSteeringWheelHeat,
    AcStrWhlSeatAutoHeat: getAcStrWhlSeatAutoHeat,
    SeatAcRow1LeftHeat: getSeatAcRow1LeftHeat,
    SeatAcRow1RightHeat: getSeatAcRow1RightHeat,
    VehicleGearShift: getVehicleGearShift,
    DestinationPoiName: getDestinationPoiName,
    RemainTime: getRemainTime,
    FrontAcWind: getFrontAcWind,
    DriverMassageStatus: getDriverMassageStatus,
    PassengerMassageStatus: getPassengerMassageStatus,
    SecondRowLeftMassageStatus: getSecondRowLeftMassageStatus,
    SecondRowRightMassageStatus: getSecondRowRightMassageStatus,
};

// 构建 type 到 getter 的映射表
export const typeKeyMap = {
    ACIncarTemp: ACIncarTempKey,
    RearACIncarTemp: RearACIncarTempKey,
    DspOtsdTemp: DspOtsdTempKey,
    AcAirCo2Value: AcAirCo2ValueKey,
    FrontAcSw: FrontAcSwKey,
    FrontAcAuto: FrontAcAutoKey,
    FrontAcAc: FrontAcAcKey,
    FrontAcSync: FrontAcSyncKey,
    FrontAcLeftTemp: FrontAcLeftTempKey,
    FrontAcWindDirection: FrontAcWindDirectionKey,
    AcAirRecycle: AcAirRecycleKey,
    AcDefrost: AcDefrostKey,
    AcRearDefrost: AcRearDefrostKey,
    SeatAcRow1LeftVent: SeatAcRow1LeftVentKey,
    SeatAcRow1RightVent: SeatAcRow1RightVentKey,
    SeatAcRow2LeftVent: SeatAcRow2LeftVentKey,
    SeatAcRow2RightVent: SeatAcRow2RightVentKey,
    SeatAcRow2LeftHeat: SeatAcRow2LeftHeatKey,
    SeatAcRow2RightHeat: SeatAcRow2RightHeatKey,
    SeatAcRow2MiddleHeat: SeatAcRow2MiddleHeatKey,
    SeatAcRow3LeftHeat: SeatAcRow3LeftHeatKey,
    SeatAcRow3RightHeat: SeatAcRow3RightHeatKey,
    SeatAcRow3MiddleHeat: SeatAcRow3MiddleHeatKey,
    ReadingLight_FL: ReadingLight_FLKey,
    ReadingLight_FR: ReadingLight_FRKey,
    ReadingLight_SecL: ReadingLight_SecLKey,
    ReadingLight_SecR: ReadingLight_SecRKey,
    ReadingLight_ThirdL: ReadingLight_ThirdLKey,
    ReadingLight_ThirdR: ReadingLight_ThirdRKey,
    ReadingLight_ThirdM: ReadingLight_ThirdMKey,
    AcEcoMode: AcEcoModeKey,
    PerfumeSw: PerfumeSwKey,
    PerfumeSelectChannel: PerfumeSelectChannelKey,
    Switch_FL: MassageSwitch_FLKey,
    Switch_FR: MassageSwitch_FRKey,
    Switch_SecL: MassageSwitch_SecLKey,
    Switch_SecR: MassageSwitch_SecRKey,
    Mode_FL: MassageMode_FLKey,
    Mode_FR: MassageMode_FRKey,
    Mode_SecL: MassageMode_SecLKey,
    Mode_SecR: MassageMode_SecRKey,
    Strength_FL: MassageStrength_FLKey,
    Strength_FR: MassageStrength_FRKey,
    Strength_SecL: MassageStrength_SecLKey,
    Strength_SecR: MassageStrength_SecRKey,
    HotStone_FL: MassageHotStone_FLKey,
    HotStone_FR: MassageHotStone_FRKey,
    HotStone_SecL: MassageHotStone_SecLKey,
    HotStone_SecR: MassageHotStone_SecRKey,
    Speed: VehInfo_SpeedKey,
    EnduranceCondition: EnduranceCondition_Key,
    CltcPureEvMileage: CltcPureEvMileage_Key,
    WltcPureEvMileage: WltcPureEvMileage_Key,
    CltcReevMileage: CltcReevMileage_Key,
    WltcReevMileage: WltcReevMileage_Key,
    MileageFinalResult: MileageFinalResult_Key,
    PowerPercent: PowerPercent_Key,
    DriveMode: DriveMode_Key,
    DrivingMode: DrivingMode_Key,
    AirSuspension: AirSuspension_Key,
    SpringSuspension: SpringSuspension_Key,
    Altitude: Altitude_Key,
    SuspensionAdjustment: SuspensionAdjustment_Key,
    SuspensionHeight: SuspensionHeight_Key,
    LowSuspension: LowSuspension_Key,
    TurnRound: TurnRound_Key,
    EnergyRecovery: EnergyRecovery_Key,
    VESS: VESS_Key,
    RangeExtenderTemp: RangeExtenderTemp_Key,
    Door: FridgeDoor_Key,
    CoolTmp: FridgeCoolTmp_Key,
    HotTmp: FridgeHotTmp_Key,
    WorkMode: FridgeWorkMode_Key,
    ChargeStatus: ChargeStatus_Key,
    ChargingStartTime: ChargingStartTime_Key,
    MSG_RESSInterVolt: MSG_RESSInterVolt_Key,
    DischargeStatus: DischargeStatus_Key,
    ChargeRemainTime: ChargeRemainTime_Key,
    ChargeLimit: ChargeLimit_Key,
    ReserveSwitchStatus: ReserveSwitchStatus_Key,
    ChargeType: ChargeType_Key,
    OGCChargeVoltage: OGCChargeVoltage_Key,
    OGCChargeCurrent: OGCChargeCurrent_Key,
    ACChargeVoltage: ACChargeVoltage_Key,
    ACChargeCurrent: ACChargeCurrent_Key,
    WarmSwitchStatus: WarmSwitchStatus_Key,
    InCarHumidity: InCarHumidityKey,
    AcAirPm25Value: AcAirPm25ValueKey,
    AcDefrost: AcDefrostKey,
    AcRearDefrost: AcRearDefrostKey,
    AcMaxCold: AcMaxColdKey,
    TempControl: TempControlKey,
    ManuTempAdjStatus: ManuTempAdjStatusKey,
    AmbientLightSwitch: AmbientLightSwitchKey,
    AmbientLightBrightness: AmbientLightBrightnessKey,
    FrontAcWindAuto: FrontAcWindAutoKey,
    RearAcSw: RearAcSwKey,
    RearAcAuto: RearAcAutoKey,
    RearAcTemp: RearAcTempKey,
    RearAcWind: RearAcWindKey,
    RearAcWindAuto: RearAcWindAutoKey,
    RearAcWindDirection: RearAcWindDirectionKey,
    RearAcTemp: RearAcTempKey,
    AcSteeringWheelHeat: AcSteeringWheelHeatKey,
    AcStrWhlSeatAutoHeat: AcStrWhlSeatAutoHeatKey,
    SeatAcRow1LeftHeat: SeatAcRow1LeftHeatKey,
    SeatAcRow1RightHeat: SeatAcRow1RightHeatKey,
    VehicleGearShift: VehicleGearShift_Key,
    DestinationPoiName: DestinationPoiNameKey,
    RemainTime: RemainTimeKey,
    ArrivalTime: ArrivalTimeKey,
    FrontAcWind: FrontAcWindKey,
    DriverMassageStatus: DriverMassageStatusKey,
    PassengerMassageStatus: PassengerMassageStatusKey,
    SecondRowLeftMassageStatus: SecondRowLeftMassageStatusKey,
    SecondRowRightMassageStatus: SecondRowRightMassageStatusKey,
};

const fakeBindTripData = {
    "tripName": "",
    "defind_tripType": -1,
    "start_time": 0,
    "stop_time": 0,
    "isValidity": 0,
    "drivingData": {
        "mileageData": {
            "mileage": 1000,
            "mileageCd": 300,
            "mileageCs": 700
        },
        "showData": {
            "oneHundarFuel": "45",
            "oneHundarEle": "78",
            "cdShowTime": {
                "hour": 10,
                "minute": 0
            },
            "csShowTime": {
                "hour": 5,
                "minute": 50
            },
            "showTime": {
                "hour": 4,
                "minute": 20
            }
        },
        "drivingDays": {
            "drivingDays": 209
        },
        "drivingDurationData": {
            "drivingDuration": 300,
            "drivingDurationCs": 10,
            "drivingDurationCd": 560
        },
        "runningDurationData": {
            "runningDuration": 820
        }
    },
    "adTripModel": {
        "adMileage": 340,
        "powerCycleData": {
            "maxAdMileage": 410,
            "maxAdDuration": 720,
            "maxAdRatio": 50.0
        },
        "adMileageDetail": {
            "noaMileage": 670,
            "accMileage": 890,
            "lccMileage": 550,
            "avpMileage": 340
        },
        "adDuration": {
            "adDuration": 980
        },
        "adEvents": {
            "passCross": 30,
            "laneChange": 20,
            "laneAvoid": 10,
            "cutInLine": 10,
            "vlm": 10,
            "passTollGate": 20,
            "takeOver": 10,
            "complexScenes": 10
        },
        "adDays": {
            "adDays": 11,
            "adDaysRatio": 37.0
        },
        "adRatio": {
            "noaRatio": 70.0,
            "accRatio": 60.0,
            "lccRatio": 50.0,
            "adRatio": 40.0
        }
    },
    "energyData": {
        "energydis": {
            "drivingAcCd": 0,
            "parkingAc": 0,
            "drivingDcDcCd": 0,
            "parkingDcDc": 0,
            "drivingOutSideCd": 0,
            "parkingOutSide": 0,
            "drivingEleCd": 0,
            "drivingFuelCs": 0
        },
        "endurance": {
            "drivingWltcCd": 0,
            "drivingCltcCd": 0,
            "parkingWltc": 0,
            "parkingCltc": 0
        }
    }
}

const fakePerfumeInfo = [{
    "mChannelDescribe": "zh-令人宁静的木质香，纯粹且富有灵气;en-A serene woody fragrance, pure and full of aura", // 香型的描述，需要二次解析，zh-后面跟着的是中文，en-后面跟着的是英文
    "mChannelLevel": 17, // 香氛余量
    "mChannelName": "zh-沉香;en-Agarwood", // 香型名字，需要二次解析，解析规则同上
    "mChannelType": 2, // 暂时用不上
    "mPerfumeTypeLabel": "chenxiang" // 香型的唯一表示
}, {
    "mChannelDescribe": "zh-鼓舞精神的味道，传达着能量、阳光与力量;en-Uplifting smells convey energy, sunshine and power",
    "mChannelLevel": 4,
    "mChannelName": "zh-海洋;en-Ocean",
    "mChannelType": 3,
    "mPerfumeTypeLabel": "haiyang"
}, {
    "mChannelDescribe": "zh-与青春面孔相遇的清香，充满年轻活力的气息;en-The fragrance of meeting with the youthful face is full of youthful vitality",
    "mChannelLevel": 0,
    "mChannelName": "zh-活力;en-Vigour",
    "mChannelType": 1,
    "mPerfumeTypeLabel": "huoli"
}]

// 批量默认值映射表
export const defaultValueMap = {
    [ACIncarTempKey]: "26",
    [RearACIncarTempKey]: "28",
    [DspOtsdTempKey]: "30",
    [AcAirCo2ValueKey]: "400",
    [FrontAcSwKey]: "1",
    [FrontAcAutoKey]: "1",
    [FrontAcAcKey]: "0",
    [FrontAcSyncKey]: "1",
    [FrontAcLeftTempKey]: "26",
    [FrontAcWindKey]: "4",
    [FrontAcWindAutoKey]: "1",
    [FrontAcWindDirectionKey]: "0",
    [AcAirRecycleKey]: "1",
    [AcDefrostKey]: "1",
    [AcRearDefrostKey]: "0",
    [RearAcSwKey]: "1",
    [RearAcAutoKey]: "1",
    [RearAcTempKey]: "28",
    [RearAcWindAutoKey]: "7",
    [RearAcWindKey]: "3",
    [RearAcWindDirectionKey]: "0",
    [AcSteeringWheelHeatKey]: "1",
    [AcStrWhlSeatAutoHeatKey]: "1",
    [SeatAcRow1LeftVentKey]: "1",
    [SeatAcRow1RightVentKey]: "1",
    [SeatAcRow2LeftVentKey]: "2",
    [SeatAcRow2RightVentKey]: "3",
    [SeatAcRow1LeftHeatKey]: "2",
    [SeatAcRow1RightHeatKey]: "2",
    [SeatAcRow2LeftHeatKey]: "1",
    [SeatAcRow2RightHeatKey]: "2",
    [SeatAcRow2MiddleHeatKey]: "2",
    [SeatAcRow3LeftHeatKey]: "3",
    [SeatAcRow3RightHeatKey]: "2",
    [SeatAcRow3MiddleHeatKey]: "2",
    [ReadingLight_FLKey]: "1",
    [ReadingLight_FRKey]: "1",
    [ReadingLight_SecLKey]: "0",
    [ReadingLight_SecRKey]: "1",
    [ReadingLight_ThirdLKey]: "0",
    [ReadingLight_ThirdRKey]: "1",
    [ReadingLight_ThirdMKey]: "0",
    [AcEcoModeKey]: "1",
    [PerfumeSwKey]: "0",
    [PerfumeSelectChannelKey]: "2",
    [PerfumeInfoKey]: JSON.stringify(fakePerfumeInfo),
    [MassageSwitch_FLKey]: "1",
    [MassageSwitch_FRKey]: "1",
    [MassageSwitch_SecLKey]: "1",
    [MassageSwitch_SecRKey]: "1",
    [MassageMode_FLKey]: "1",
    [MassageMode_FRKey]: "1",
    [MassageMode_SecLKey]: "1",
    [MassageMode_SecRKey]: "1",
    [MassageStrength_FLKey]: "1",
    [MassageStrength_FRKey]: "1",
    [MassageStrength_SecLKey]: "2",
    [MassageStrength_SecRKey]: "2",
    [MassageHotStone_FLKey]: "1",
    [MassageHotStone_FRKey]: "1",
    [MassageHotStone_SecLKey]: "1",
    [MassageHotStone_SecRKey]: "1",
    [VehInfo_SpeedKey]: "120",
    [VehicleGearShift_Key]: "1",
    [BindTrip_Key]: JSON.stringify(fakeBindTripData),
    [EnduranceCondition_Key]: "CLTC",
    [CltcPureEvMileage_Key]: "433km",
    [WltcPureEvMileage_Key]: "433km",
    [CltcReevMileage_Key]: "433km",
    [WltcReevMileage_Key]: "433km",
    [MileageFinalResult_Key]: "500",
    [PowerPercent_Key]: "80%",
    [DriveMode_Key]: "1",
    [DrivingMode_Key]: "1",
    [AirSuspension_Key]: "1",
    [SpringSuspension_Key]: "1",
    [Altitude_Key]: "1",
    [SuspensionAdjustment_Key]: "1",
    [SuspensionHeight_Key]: "1",
    [LowSuspension_Key]: "1",
    [TurnRound_Key]: "1",
    [EnergyRecovery_Key]: "1",
    [VESS_Key]: "1",
    [RangeExtenderTemp_Key]: "20",
    [FridgeDoor_Key]: "1",
    [FridgeCoolTmp_Key]: "4",
    [FridgeHotTmp_Key]: "38",
    [FridgeWorkMode_Key]: "1",
    [ChargeStatus_Key]: "1",
    [ChargingStartTime_Key]: "1752045092000",
    [MSG_RESSInterVolt_Key]: "100",
    [DischargeStatus_Key]: "100",
    [ChargeRemainTime_Key]: "100",
    [ChargeLimit_Key]: "90",
    [ReserveSwitchStatus_Key]: "1",
    [ChargeType_Key]: "1",
    [OGCChargeVoltage_Key]: "100",
    [OGCChargeCurrent_Key]: "100",
    [ACChargeVoltage_Key]: "10",
    [ACChargeCurrent_Key]: "10",
    [WarmSwitchStatus_Key]: "1",
    [TempControlKey]: "2",
    [ManuTempAdjStatusKey]: "1",
    [AmbientLightSwitchKey]: "1",
    [AmbientLightBrightnessKey]: "1",
    [AcMaxColdKey]: "0",
    [VehicleGearShift_Key]: "1",
    [InCarHumidityKey]: "50",
    [AcAirPm25ValueKey]: "10",
    [DestinationPoiNameKey]: "望京南地铁站C口",
    [RemainTimeKey]: "1912",

};

const modeMap = {
    0: "未开启按摩",
    101: "全身激活",
    102: "全身放松",
    103: "全身舒缓",
    104: "全身松弛",
    105: "腰臀放松",
    106: "腰臀激活",
    107: "全身舒展",
    108: "肩臀放松",
    201: "背部激活",
    202: "背部放松",
    203: "背部舒缓",
    204: "脊柱松弛",
    205: "腰部放松",
    206: "腰部激活",
    207: "背部舒展",
    208: "肩部放松",
    301: "臀部激活",
    302: "臀部放松",
    303: "臀部松弛",
    304: "臀部解压",
    401: "揉捏放松",
    402: "揉捏激活",
    403: "叩击放松",
    404: "叩击激活",
    405: "点按放松",
    406: "点按激活",
    407: "腰臀放松",
    408: "腰臀激活",
    409: "循环放松",
    410: "循环激活",
    501: "揉捏放松",
    502: "揉捏激活",
    503: "叩击放松",
    504: "叩击激活",
    505: "点按放松",
    506: "点按激活",
    507: "腰部放松",
    508: "腰部激活",
    509: "循环放松",
    510: "循环激活",
    601: "揉捏放松",
    602: "揉捏激活",
    603: "叩击放松",
    604: "叩击激活",
    605: "点按放松",
    606: "点按激活",
    609: "循环放松",
    610: "循环激活",


    204: "脊柱松弛",
    205: "腰部放松",
    206: "腰部激活",
    207: "背部舒展",
    208: "肩部放松",

    301: "臀部激活",
    302: "臀部放松",
    303: "臀部松弛",
    304: "臀部解压",

    401: "揉捏放松",
    402: "揉捏激活",
    403: "叩击放松",
    404: "叩击激活",
    405: "点按放松",
    406: "点按激活",
    407: "腰臀放松",
    408: "腰臀激活",
    409: "循环放松",
    410: "循环激活",

    501: "揉捏放松",
    502: "揉捏激活",
    503: "叩击放松",
    504: "叩击激活",
    505: "点按放松",
    506: "点按激活",
    507: "腰部放松",
    508: "腰部激活",
    509: "循环放松",
    510: "循环激活",

    601: "揉捏放松",
    602: "揉捏激活",
    603: "叩击放松",
    604: "叩击激活",
    605: "点按放松",
    606: "点按激活",
    609: "循环放松",
    610: "循环激活",
}

// 将车机返回的数值转化为展示给用户的文案
export function getMeaningfulData(type, src) {
    switch (type) {
        case "AcDefrost":
        case "AcRearDefrost":
        case "FrontAcSw":
        case "FrontAcAuto":
        case "HotStone_FL":
        case "HotStone_FR":
        case "HotStone_SecL":
        case "HotStone_SecR":
        case "FrontAcAc":
        case "FrontAcSync":
        case "AcEcoMode":
        case "ReadingLight_FL":
        case "ReadingLight_FR":
        case "ReadingLight_SecL":
        case "ReadingLight_SecR":
        case "ReadingLight_ThirdL":
        case "ReadingLight_ThirdR":
        case "ReadingLight_ThirdM":
        case "RearAcSw":
        case "RearAcAuto":
        case "Switch_FL":
        case "Switch_FR":
        case "Switch_SecL":
        case "Switch_SecR":
        case "AcSteeringWheelHeat":
        case "AcStrWhlSeatAutoHeat":
        case "AmbientLightSwitch":
        case "AcMaxCold":
        case "AcDefrost":
        case "AcRearDefrost":
        case "ReserveSwitchStatus":
        case "WarmSwitchStatus":
        case "TempControl":
        case "ManuTempAdjStatus":
        case "LowSuspension":
        case "VESS":
            switch (src) {
                case "0" || 0:
                    return "关闭";
                case "1" || 1:
                    return "开启";
                default:
                    return src;
            }
        case "FrontAcWindDirection":
            switch (src) {
                case "1" || 1:
                    return "吹脸";
                case "2" || 2:
                    return "吹脸&吹脚";
                case "3" || 3:
                    return "吹脚";
                case "4" || 4:
                    return "吹脚&吹窗";
                case "5" || 5:
                    return "吹窗";
                case "6" || 6:
                    return "吹脸&吹窗";
                case "7" || 7:
                    return "吹脸&吹脚&吹窗";
                default:
                    return src;
            }
        case "AcAirRecycle":
            switch (src) {
                case "1" || 1:
                    return "外循环";
                case "2" || 2:
                    return "内循环";
                case "3" || 3:
                    return "自动";
                default:
                    return src;
            }
        case "RearAcWindDirection":
            switch (src) {
                case "0" || 0:
                    return "吹脸";
                case "1" || 1:
                    return "吹脚";
                default:
                    return src;
            }
        case "PerfumeSw":
            switch (src) {
                case "0" || 0:
                    return "关闭";
                case "1" || 1:
                    return "淡香";
                case "2" || 2:
                    return "清香";
                case "3" || 3:
                    return "浓香";
                default:
                    return src;
            }
        case "PerfumeSelectChannel":
            switch (src) {
                case "0" || 0:
                    return "未选中任何香型";
                case "1" || 1:
                    return "通道一";
                case "2" || 2:
                    return "通道一";
                case "3" || 3:
                    return "通道三";
                default:
                    return src;
            }
        case "Door":
            switch (src) {
                case "2" || 2:
                    return "关闭";
                case "1" || 1:
                    return "打开";
                default:
                    return src;
            }
        case "WorkMode":
            switch (src) {
                case "0" || 0:
                    return "关闭";
                case "1" || 1:
                    return "制冷";
                case "2" || 2:
                    return "制热";
                default:
                    return src;
            }
        case "ChargeStatus":
            switch (src) {
                case "0" || 0:
                    return "无状态";
                case "1" || 1:
                    return "充电枪已连接";
                case "2" || 2:
                    return "电池预热";
                case "3" || 3:
                    return "充电中";
                case "4" || 4:
                    return "电池保温";
                case "5" || 5:
                    return "充电停止";
                case "6" || 6:
                    return "充电暂停";
                case "7" || 7:
                    return "充电错误";
                case "15" || 15:
                    return "充电枪拔出";
                case "16" || 16:
                    return "预约充电等待中";
                case "17" || 17:
                    return "充电完成";
                default:
                    return src;
            }
        case "ChargingStartTime":
            if (src) {
                const date = new Date(Number(src));
                const hours = date.getHours().toString().padStart(2, '0');
                const minutes = date.getMinutes().toString().padStart(2, '0');
                return `${hours}:${minutes}`;
            } else if (src == "-1") {
                return "未充电";
            }
            return src;
        case "ChargeType":
            switch (src) {
                case "0" || 0:
                    return "未插枪";
                case "1" || 1:
                    return "慢充(交流枪)";
                case "2" || 2:
                    return "快充(直流枪)";
                default:
                    return src;
            }
        case "VehicleGearShift":
            switch (src) {
                case "1" || 1:
                    return "R";
                case "2" || 2:
                    return "N";
                case "3" || 3:
                    return "D";
                case "4" || 4:
                    return "P";
                default:
                    return src;
            }
        case "DriveMode":
            switch (src) {
                case "0" || 0:
                    return "纯电优先";
                case "1" || 1:
                    return "燃油优先";
                case "2" || 2:
                    return "油电混合";
                default:
                    return src;
            }
        case "DrivingMode":
            switch (src) {
                case "0" || 0:
                    return "舒适";
                case "1" || 1:
                    return "标准";
                case "2" || 2:
                    return "运动";
                case "3" || 3:
                    return "高性能";
                case "4" || 4:
                    return "节能";
                case "5" || 5:
                    return "后排舒适";
                default:
                    return src;
            }
        case "AirSuspension":
            switch (src) {
                case "0" || 0:
                    return "舒适魔毯";
                case "1" || 1:
                    return "运动魔毯";
                default:
                    return src;
            }
        case "SpringSuspension":
            switch (src) {
                case "0" || 0:
                    return "舒适CDC";
                case "1" || 1:
                    return "运动CDC";
                default:
                    return src;
            }
        case "SuspensionAdjustment":
            switch (src) {
                case "0" || 0:
                    return "舒适";
                case "1" || 1:
                    return "标准";
                case "2" || 2:
                    return "运动";
                default:
                    return src;
            }
        case "SuspensionHeight":
            switch (src) {
                case "0" || 0:
                    return "低";
                case "1" || 1:
                    return "标准";
                case "2" || 2:
                    return "高";
                case "3" || 3:
                    return "较高";
                default:
                    return src;
            }
        case "TurnRound":
            switch (src) {
                case "0" || 0:
                    return "舒适";
                case "1" || 1:
                    return "标准";
                case "2" || 2:
                    return "运动";
                default:
                    return src;
            }
        case "EnergyRecovery":
            switch (src) {
                case "0" || 0:
                    return "舒适";
                case "1" || 1:
                    return "标准";
                case "2" || 2:
                    return "强";
                default:
                    return src;
            }
        case "Mode_FL":
        case "Mode_FR":
        case "Mode_SecL":
        case "Mode_SecR":
            return modeMap[Number(src)];
        case "Strength_FL":
        case "Strength_FR":
        case "Strength_SecL":
        case "Strength_SecR":
            switch (src) {
                case "0" || 0:
                    return "未开启按摩";
                case "1" || 1:
                    return "轻柔";
                case "2" || 2:
                    return "标准";
                case "3" || 3:
                    return "强力";
                default:
                    return src;
            }
        case "PerfumeChannelType":
            switch (src) {
                case "1" || 0:
                    return "沉香";
                case "2" || 2:
                    return "活力";
                case "3" || 3:
                    return "海洋";
                case "4" || 4:
                    return "雨漫庭园";
                case "5" || 5:
                    return "晨沐雪松";
                case "6" || 6:
                    return "若水龙涎";
                case "7" || 7:
                    return "守护树";
                case "8" || 8:
                    return "平安果";
                case "9" || 9:
                    return "吉祥云"
                default:
                    return src;
            }
        case "AcAirCo2Value":
            if (src == "-1") {
                return "--";
            } else if (src < 1000) {
                return "低";
            } else if (src < 2000) {
                return "中";
            } else {
                return "高";
            }
        case "Altitude":
            if (src == "-2147483648") {
                return "--";
            } else {
                return src;
            }
        case "ACIncarTemp":
        case "RearACIncarTemp":
        case "DspOtsdTemp":
            let number = Number(src);
            if (isNaN(number)) {
                return "--";
            } else if (number < -40 || number > 85) {
                return "--";
            } else {
                return number.toFixed(1);
            }
        case "FrontAcLeftTemp":
        case "FrontAcRightTemp":
        case "RearAcTemp":
            let frontAcLeftTemp = Number(src);
            if (isNaN(frontAcLeftTemp)) {
                return "--";
            } else if (frontAcLeftTemp < 16 || frontAcLeftTemp > 28) {
                return "--";
            } else {
                return src;
            }
        case "InCarHumidity":
            let inCarHumidity = Number(src);
            if (isNaN(inCarHumidity)) {
                return "--";
            } else if (inCarHumidity < 0 || inCarHumidity > 126) {
                return "--";
            } else {
                return src;
            }
        case "AcAirPm25Value":
            let acAirPm25Value = Number(src);
            if (isNaN(acAirPm25Value)) {
                return "--";
            } else if (acAirPm25Value < 0 || acAirPm25Value >= 1000) {
                return "--";
            } else {
                return src;
            }
        case "Speed":
            let speed = Number(src);
            if (isNaN(speed)) {
                return "--";
            } else if (speed < 0 || speed > 200) {
                return "--";
            } else {
                return src;
            }
        default:
            return src;
    }
}