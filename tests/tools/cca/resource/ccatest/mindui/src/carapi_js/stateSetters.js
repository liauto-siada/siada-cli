import { registerListener, setKeyValue, setKeyValueWithoutValue, setKeyValueWithSource } from "./utils";
import * as log from './log.js';
import { getterMap } from "./carApiGetter.js";

export function setCarValue(key, target, value) {
    log.i("setCarValue", key, target, value)
    if (value == null || value == undefined) {
        log.e("setCarValue value is null or undefined")
        return;
    }
    try {
        setKeyValue(key, target, value);
    } catch (error) {
        log.e("设置键值对失败", error);
    }
}

function setTargetValueWithUnderline(key, target, value) {
    let breakingPoint = target.lastIndexOf("_")
    let targetRes = target.substring(breakingPoint + 1)
    setCarValue(key, targetRes, value)
}

const CAR_CONTROL_KEY = "CarControlTpuPlugin/carControl/setValue"

export function set_vehicle_fragrance_system(target, value) {
    setTargetValueWithUnderline(CAR_CONTROL_KEY, target, value)
}

export function set_seat_massage_control(target, value) {
    setTargetValueWithUnderline(CAR_CONTROL_KEY, target, value)
}

export function set_interior_lighting_system(target, value) {
    setTargetValueWithUnderline(CAR_CONTROL_KEY, target, value)
}

export function set_seat_ventilation_system(target, value) {
    setTargetValueWithUnderline(CAR_CONTROL_KEY, target, value)
}

export function set_seat_heating(target, value) {
    setTargetValueWithUnderline(CAR_CONTROL_KEY, target, value)
}

export function set_hvac_general_control(target, value) {
    setTargetValueWithUnderline(CAR_CONTROL_KEY, target, value)
}

export function set_defrost_defogging_control(target, value) {
    switch (target) {
        case "CarControlTpuPlugin_AcDefrostState":
            setCarValue(CAR_CONTROL_KEY, "AcDefrost", value)
            break;
        case "CarControlTpuPlugin_AcRearDefrostState":
            setCarValue(CAR_CONTROL_KEY, "AcRearDefrost", value)
            break;
        case "CarControlTpuPlugin_AcMaxColdState":
            setCarValue(CAR_CONTROL_KEY, "AcMaxCold", value)
            break;
        default:
            break;
    }
}

export function set_front_hvac_system(target, value) {
    if (target == "CarControlTpuPlugin_FrontAcPowerState") {
        setCarValue(CAR_CONTROL_KEY, "FrontAcSw", value)
    } else if (target == "CarControlTpuPlugin_FrontAcManualFanLevel") {
        setCarValue(CAR_CONTROL_KEY, "FrontAcWind", value)
    } else if (target == "CarControlTpuPlugin_FrontAcAutoFanLevel") {
        setCarValue(CAR_CONTROL_KEY, "FrontAcWindAuto", value)
    } else if (target == "CarControlTpuPlugin_FrontAcAutoModeEnabled") {
        setCarValue(CAR_CONTROL_KEY, "FrontAcAuto", value)
    } else {
        setTargetValueWithUnderline(CAR_CONTROL_KEY, target, value)
    }
}

export function set_steering_wheel_seat_heating(target, value) {
    if (target == "CarControlTpuPlugin_AcSteeringWheelHeatState") {
        setCarValue(CAR_CONTROL_KEY, "AcSteeringWheelHeat", value)
    } else if (target == "CarControlTpuPlugin_AcStrWhlSeatAutoHeatState") {
        setCarValue(CAR_CONTROL_KEY, "AcStrWhlSeatAutoHeat", value)
    } else {
        setTargetValueWithUnderline(CAR_CONTROL_KEY, target, value)
    }
}

export function set_rear_hvac_control(target, value) {
    if (target == "CarControlTpuPlugin_RearAcPowerState") {
        setCarValue(CAR_CONTROL_KEY, "RearAcSw", value)
    } else if (target == "CarControlTpuPlugin_RearAcManualFanLevel") {
        setCarValue(CAR_CONTROL_KEY, "RearAcWind", value)
    } else if (target == "CarControlTpuPlugin_RearAcAutoFanLevel") {
        setCarValue(CAR_CONTROL_KEY, "RearAcWindAuto", value)
    } else if (target == "CarControlTpuPlugin_RearAcAutoModeEnabled") {
        setCarValue(CAR_CONTROL_KEY, "RearAcAuto", value)
    } else if (target == "CarControlTpuPlugin_RearAcTemp") {
        setCarValue(CAR_CONTROL_KEY, "RearAcTemp", value)
    } else {
        setTargetValueWithUnderline(CAR_CONTROL_KEY, target, value)
    }
}

const CAR_SETTING_KEY = "CarSettingsTpuPlugin/carSettings/setValue"

export function set_vehicle_driving_control(target, value) {
    log.i("set_vehicle_driving_control", target, value)
    switch (target) {
        case "CarSettingsTpuPlugin_EnergyMode":
            setCarValue(CAR_SETTING_KEY, "drive_mode", value)
            break;
        case "CarSettingsTpuPlugin_PowerMode":
            setCarValue(CAR_SETTING_KEY, "driving_mode", value)
            break;
        case "CarSettingsTpuPlugin_MagicSuspensionMode":
        case "CarSettingsTpuPlugin_CdcSuspensionMode":
            setCarValue(CAR_SETTING_KEY, "suspension_version", value)
            break;
        case "CarSettingsTpuPlugin_SuspensionComfortLevel":
            setCarValue(CAR_SETTING_KEY, "suspension_adjustment", value)
            break;
        case "CarSettingsTpuPlugin_SuspensionHeight":
            setCarValue(CAR_SETTING_KEY, "suspension_height", value)
            break;
        case "CarSettingsTpuPlugin_EasyEntryExitEnabled":
            setCarValue(CAR_SETTING_KEY, "low_suspension_button", value)
            break;
        case "CarSettingsTpuPlugin_SteeringMode":
            setCarValue(CAR_SETTING_KEY, "turn_round", value)
            break;
        case "CarSettingsTpuPlugin_RegenerativeBrakingLevel":
            setCarValue(CAR_SETTING_KEY, "energy_recovery_level", value)
            break;
        case "CarSettingsTpuPlugin_LowSpeedWarningEnabled":
            setCarValue(CAR_SETTING_KEY, "warning_for_low_speed", value)
            break;
        default:
            break;
    }
}

export function set_ambient_light_control(target, value) {
    if (target == "CarSettingsPlugin_AmbientLightSwitch") {
        setCarValue("CarSettingsPlugin/carSettings/setSwitch", "AmbientLight", value == 1 ? "open" : "close")
    } else if (target == "CarSettingsPlugin_AmbientLightBrightness") {
        setCarValue(CAR_SETTING_KEY, "ambient_light_brightness", value)
    }
}

const CAR_EXT_KEY = "CarExtDeviceTpuPlugin/carExtDevice/setValue"

export function set_vehicle_refrigerator_control(target, value) {
    if (target == "CarExtDeviceTpuPlugin_FridgeDoorState") {
        setCarValue(CAR_EXT_KEY, "FridgeDoor", value)
    } else {
        setTargetValueWithUnderline(CAR_EXT_KEY, target, value)
    }
}

export function set_charging_control(target, value) {
    const CHARGE_PATH = "ChargeTpuPlugin/charge/setValue";
    const SHOW_PATH = "ChargeTpuPlugin/charge/showPage";
    switch (target) {
        case "ChargeTpuPlugin_ReserveChargeConfig":
            setKeyValueWithoutValue(SHOW_PATH, "reserve")
            break;
        case "ChargeTpuPlugin_ChargeTargetSoc":
            setKeyValueWithSource(CHARGE_PATH, "chargeTargetSoc", value)
            break;
        case "ChargeTpuPlugin_ReserveChargeSwitch":
            setKeyValueWithSource(CHARGE_PATH, "reserve", value);
            break;
        case "ChargeTpuPlugin_BatteryWarm":
            setKeyValueWithSource(CHARGE_PATH, "batteryWarm", value);
            break;
        case "ChargeTpuPlugin_AutoHeating":
            setKeyValueWithSource(CHARGE_PATH, "autoHeating", value);
            break;
        case "ChargeTpuPlugin_ManualPreHeating":
            setKeyValueWithSource(CHARGE_PATH, "manualPreHeating", value);
            break;
        default:
            break;
    }
}

export function set_rear_seat_heating(target, value) {
    setTargetValueWithUnderline(CAR_CONTROL_KEY, target, value)
}

export function set_seat_massage_mode(target, value) {
    log.i("set_seat_massage_mode", target, value)
    let controlType = "";
    let setTarget = "";
    if (target.includes("_driver")) {
        controlType = "DriverMassageStatus";
        setTarget = "FLSeatMassage";
    } else if (target.includes("_passenger")) {
        controlType = "PassengerMassageStatus";
        setTarget = "FRSeatMassage";
    } else if (target.includes("_secondRowLeft")) {
        controlType = "SecondRowLeftMassageStatus";
        setTarget = "SecLSeatMassage";
    } else if (target.includes("_secondRowRight")) {
        controlType = "SecondRowRightMassageStatus";
        setTarget = "SecRSeatMassage";
    }
    console.log("controlType", controlType, ", setTarget", setTarget)
    
    getterMap[controlType]()
        .then(res => {
            let seatStatus = JSON.parse(res);
            log.i("get seatStatus", seatStatus, ", begin set massage mode")
            let index = target.lastIndexOf("_");
            let setType = target.substring(index + 1);
            seatStatus.switch = 1;
            seatStatus.massSwitch = 1;
            seatStatus[setType] = value;
            if (seatStatus.massHotStone == -1) {
                log.i("massHotStone is -1, set to 0")
                seatStatus.massHotStone = 0;
            }
            setCarValue(CAR_CONTROL_KEY, setTarget, JSON.stringify(seatStatus));
        })
        .catch(error => {
            log.e("获取座位状态失败", error);
        });
}

// value="{
//     "switch": 1,
//     "massSwitch": 1,
//     "massType": 2,
//     "massMode": 1,
//     "massStrength": 3
//     "massHotStone": 0
//   }"
// * switch:1->开启，0->关闭
// * massType:1->全身，2->背部，3->坐垫
// * massMode:全身/背部(1~10)，坐垫(1~4)，三点背部(1)
// * massStrength:三点(3)，十点/十六点(1~3)""
// * massHotStone:1->开启，0->关闭，-1->没有此功能
function makeMassageData(switchState, massSwitch, massType, massMode, massStrength, massHotStone) {
    return JSON.stringify({
        switch: switchState,
        massSwitch: massSwitch,
        massType: massType,
        massMode: massMode,
        massStrength: massStrength,
        massHotStone: massHotStone
    })
}

export function setMassageMode(switchState, massSwitch, massType, massMode, massStrength, massHotStone) {
    setCarValue(CAR_CONTROL_KEY, "SecLSeatMassage", makeMassageData(switchState, massSwitch, massType, massMode, massStrength, massHotStone))
}