import { makeData } from "./utils.js";
import { getVehInfo_Speed, getVehicleGearShift, getBindTrip, getEnduranceCondition, getCltcPureEvMileage, getWltcPureEvMileage, getMockData } from "./carApiGetter.js";
import { typeKeyMap, defaultValueMap } from "./carApiGetter.js";
import { getKeyValue } from "./utils.js";
import callbackManager from "./callbackManager.js";
import * as log from "./log.js";

// 在一个模块里，get方法只需调用一次，后面直接使用callback
function registerAndGet(controlType, id, callback) {
    log.i("registerAndGet", controlType, id, "found key: " + typeKeyMap[controlType]);
    registerKeyAndGet(typeKeyMap[controlType], id, callback);
}

export function triggerGetForType(controlType) {
    getKeyValue(typeKeyMap[controlType]);
}

function registerKeyAndGet(key, id, callback) {
    callbackManager.registerCardListener(id, key, callback);
    // 触发一次数据获取
    getKeyValue(key);

    if (getMockData()) {
        setTimeout(() => {
            callbackManager.onWidgetAgentCallback(id, key, JSON.stringify({ value: defaultValueMap[key] }));
        }, 1000);
    }
}

export function get_seat_massage_control(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_defrost_defogging_control(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_front_hvac_system(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_hot_stone_massage_system(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_hvac_general_control(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_interior_lighting_system(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_rear_hvac_control(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_rear_seat_heating(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}


export const get_seat_massage_mode = (() => {
    const statusCache = new Map();
    const callbacks = new Map();

    return function get_seat_massage_mode(id, controlType, callback) {
        let type = "";
        if (controlType.includes("_FL")) {
            type = "DriverMassageStatus";
        } else if (controlType.includes("_FR")) {
            type = "PassengerMassageStatus";
        } else if (controlType.includes("_SecL")) {
            type = "SecondRowLeftMassageStatus";
        } else if (controlType.includes("_SecR")) {
            type = "SecondRowRightMassageStatus";
        }
    
        registerAndGet(type, id, (value) => {
            let statusObj = JSON.parse(value);
            let res = null;
            if (controlType.includes("Mode_")) {
                res = statusObj.massMode;
            } else if (controlType.includes("Strength_")) {
                res = statusObj.massStrength;
            } else if (controlType.includes("HotStone_")) {
                res = statusObj.massHotStone;
            } else if (controlType.includes("Type_")) {
                res = statusObj.massType;
            }
            callback(res);
        });
    }
})();

export function get_seat_ventilation_system(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_steering_wheel_seat_heating(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_vehicle_environment_monitoring(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

function parseZhEn(str) {
    const zhMatch = str.match(/zh-([^;]*)/);
    const enMatch = str.match(/en-([^;]*)/);
    return {
        zh: zhMatch ? zhMatch[1] : "",
        en: enMatch ? enMatch[1] : ""
    };
}

// TODO:
export const get_perfume_information = (() => {
    // 闭包内的缓存，用于存储香氛数据
    const perfumeDataCache = {
        latestChannel: null,
        latestInfo: null,
        callbacks: new Map(), // Map<controlType, Set<{id, callback}>>
        channelListenerRegistered: false,
        infoListenerRegistered: false,
        initialized: false
    };

    // 处理香氛数据并分发到对应的回调
    function processPerfumeData() {
        if (perfumeDataCache.latestChannel == 0) {
            // 未选中香氛，通知所有回调
            perfumeDataCache.callbacks.forEach((callbacks, controlType) => {
                callbacks.forEach(({callback}) => {
                    callback("未选中香氛");
                });
            });
            return;
        }
        
        if (perfumeDataCache.latestChannel == null || perfumeDataCache.latestInfo == null) {
            // 数据不完整，通知所有回调返回null
            perfumeDataCache.callbacks.forEach((callbacks, controlType) => {
                callbacks.forEach(({callback}) => {
                    callback(null);
                });
            });
            return;
        }
        
        try {
            let arr = JSON.parse(perfumeDataCache.latestInfo);
            let data = arr[perfumeDataCache.latestChannel - 1];
            let zhEnDesc = parseZhEn(data.mChannelDescribe);
            let zhEnName = parseZhEn(data.mChannelName);
            
            // 为每个controlType处理数据并通知对应的回调
            perfumeDataCache.callbacks.forEach((callbacks, controlType) => {
                let result = null;
                
                switch (controlType) {
                    case "PerfumeChannelNameZh":
                        result = zhEnName.zh;
                        break;
                    case "PerfumeChannelNameEn":
                        result = zhEnName.en;
                        break;
                    case "PerfumeChannelDescribeZh":
                        result = zhEnDesc.zh;
                        break;
                    case "PerfumeChannelDescribeEn":
                        result = zhEnDesc.en;
                        break;
                    case "PerfumeChannelLevel":
                        result = data.mChannelLevel;
                        break;
                    case "PerfumeChannelType":
                        result = data.mChannelType;
                        break;
                    case "PerfumeTypeLabel":
                        result = data.mChannelType;
                        break;
                    default:
                        break;
                }
                
                // 通知该controlType的所有回调
                callbacks.forEach(({callback}) => {
                    callback(result);
                });
            });
            
        } catch (error) {
            log.e("处理香氛数据失败", error);
            // 数据解析失败，通知所有回调返回null
            perfumeDataCache.callbacks.forEach((callbacks, controlType) => {
                callbacks.forEach(({callback}) => {
                    callback(null);
                });
            });
        }
    }

    return function get_perfume_information(id, controlType, callback) {
        const PerfumeSelectChannelKey = "Vehicle.VehInfo.CarControl.Perfume.PerfumeSelectChannel"; // 当前使用香型
        const PerfumeInfoKey = "Vehicle.VehInfo.CarControl.Perfume.Information";
        
        // 为每个controlType创建独立的回调集合
        if (!perfumeDataCache.callbacks.has(controlType)) {
            perfumeDataCache.callbacks.set(controlType, new Set());
        }
        
        // 添加回调到对应controlType的集合中
        perfumeDataCache.callbacks.get(controlType).add({id, callback});
        
        // 只在第一次调用时注册香型选择监听器
        if (!perfumeDataCache.channelListenerRegistered) {
            callbackManager.registerCardListener(id, PerfumeSelectChannelKey, (channel) => {
                perfumeDataCache.latestChannel = channel;
                processPerfumeData();
            });
            perfumeDataCache.channelListenerRegistered = true;
        }
        
        // 只在第一次调用时注册香氛信息监听器
        if (!perfumeDataCache.infoListenerRegistered) {
            callbackManager.registerCardListener(id, PerfumeInfoKey, (info) => {
                perfumeDataCache.latestInfo = info;
                processPerfumeData();
            });
            perfumeDataCache.infoListenerRegistered = true;
        }
        
        // 触发初始数据获取（只在第一次调用时）
        if (!perfumeDataCache.initialized) {
            getKeyValue(PerfumeSelectChannelKey);
            getKeyValue(PerfumeInfoKey);
            perfumeDataCache.initialized = true;
        }
        
        // 如果已有缓存数据，立即处理
        if (perfumeDataCache.latestChannel !== null || perfumeDataCache.latestInfo !== null) {
            processPerfumeData();
        }
    };
})();

export function get_vehicle_fragrance_system(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_vehicle_refrigerator_status(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_charging_information(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_ambient_light_information(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_driving_information(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

export function get_vehicle_driving_status(id, controlType, callback) {
    registerAndGet(controlType, id, callback);
}

// 需要先判断是否在导航中，停止导航后车端不会清除上一次导航信息
export const get_navigation_information = (() => {
    // 闭包内的缓存，用于存储导航数据
    const navigationDataCache = {
        isInNavi: null,
        navigationData: new Map(),
        callbacks: new Map(), // Map<controlType, Set<{id, callback}>>
        isInNaviListenerRegistered: false,
        navigationListenerRegistered: new Map(),
        initialized: false
    };

    // 处理导航数据并分发到对应的回调
    function processNavigationData() {
        if (!navigationDataCache.isInNavi) {
            // 不在导航中，通知所有回调返回null
            navigationDataCache.callbacks.forEach((callbacks, controlType) => {
                callbacks.forEach(({callback}) => {
                    callback(null);
                });
            });
            return;
        }
        
        if (navigationDataCache.navigationData === null) {
            // 在导航中但没有导航数据，通知所有回调返回null
            navigationDataCache.callbacks.forEach((callbacks, controlType) => {
                callbacks.forEach(({callback}) => {
                    callback(null);
                });
            });
            return;
        }
        
        try {
            // 为每个controlType处理数据并通知对应的回调
            navigationDataCache.callbacks.forEach((callbacks, controlType) => {
                try {
                    callbacks.forEach(({callback}) => {
                        if (callback == null) {
                            return;
                        }
                        callback(navigationDataCache.navigationData[controlType]);
                    });
                } catch (error) {
                    log.e("处理导航数据失败", error);
                    callbacks.forEach(({callback}) => {
                        callback(null);
                    });
                }
            });
        } catch (error) {
            log.e("处理导航数据失败", error);
            navigationDataCache.callbacks.forEach((callbacks, controlType) => {
                callbacks.forEach(({callback}) => {
                    callback(null);
                });
            });
        }
    }

    return function get_navigation_information(id, controlType, callback) {
        const IsInNaviKey = "Vehicle.Travel.OneMap.Navi.IsNaving"; // 是否在导航中
        const navigationKey = typeKeyMap[controlType]; // 导航信息对应的key

        if (controlType === "ArrivalTime") {
            get_navigation_information(id, "RemainTime", null);
        }
        
        // 为每个controlType创建独立的回调集合
        if (!navigationDataCache.callbacks.has(controlType)) {
            navigationDataCache.callbacks.set(controlType, new Set());
        }
        
        // 添加回调到对应controlType的集合中
        navigationDataCache.callbacks.get(controlType).add({id, callback});
        
        // 只在第一次调用时注册导航状态监听器
        if (!navigationDataCache.isInNaviListenerRegistered) {
            callbackManager.registerCardListener(id, IsInNaviKey, (value) => {
                navigationDataCache.isInNavi = value == "1";
                processNavigationData();
            });
            navigationDataCache.isInNaviListenerRegistered = true;
        }
        
        // 只在第一次调用时注册导航信息监听器
        if (!navigationDataCache.navigationListenerRegistered.has(controlType)) {
            callbackManager.registerCardListener(id, navigationKey, (data) => {
                navigationDataCache.navigationData[controlType] = data;
                processNavigationData();
            });
            navigationDataCache.navigationListenerRegistered.set(controlType, true);
        }
        
        // 触发初始数据获取（只在第一次调用时）
        if (!navigationDataCache.initialized) {
            getKeyValue(IsInNaviKey);
            getKeyValue(navigationKey);
            navigationDataCache.initialized = true;
        }
        
        // 如果已有缓存数据，立即处理
        if (navigationDataCache.isInNavi !== null || navigationDataCache.navigationData.has(controlType)) {
            processNavigationData();
        }
    };
})();

// TODO:
export const get_bind_trip = (() => {
    // 闭包内的缓存，用于存储绑定行程数据
    const bindTripDataCache = {
        tripData: null,
        callbacks: new Map(), // Map<controlType, Set<{id, callback}>>
        listenerRegistered: false,
        initialized: false
    };

    // 处理绑定行程数据并分发到对应的回调
    function processBindTripData(tripData) {
        if (!tripData) {
            // 数据为空，通知所有回调返回null
            bindTripDataCache.callbacks.forEach((callbacks, controlType) => {
                callbacks.forEach(({callback}) => {
                    callback(null);
                });
            });
            return;
        }
        
        try {
            const data = JSON.parse(tripData);
            
            // 为每个controlType处理数据并通知对应的回调
            bindTripDataCache.callbacks.forEach((callbacks, controlType) => {
                let result = null;
                
                switch (controlType) {
                    case "adMileage":
                        result = data.adTripModel.adMileage;
                        break;
                    case "maxAdMileage":
                        result = data.adTripModel.powerCycleData.maxAdMileage;
                        break;
                    case "maxAdDuration":
                        result = data.adTripModel.powerCycleData.maxAdDuration;
                        break;
                    case "maxAdRatio":
                        result = data.adTripModel.powerCycleData.maxAdRatio;
                        break;
                    case "noaMileage":
                        result = data.adTripModel.adMileageDetail.noaMileage;
                        break;
                    case "accMileage":
                        result = data.adTripModel.adMileageDetail.accMileage;
                        break;
                    case "lccMileage":
                        result = data.adTripModel.adMileageDetail.lccMileage;
                        break;
                    case "avpMileage":
                        result = data.adTripModel.adMileageDetail.avpMileage;
                        break;
                    case "adDuration":
                        result = data.adTripModel.adDuration.adDuration;
                        break;
                    case "passCross":
                        result = data.adTripModel.adEvents.passCross;
                        break;
                    case "laneChange":
                        result = data.adTripModel.adEvents.laneChange;
                        break;
                    case "laneAvoid":
                        result = data.adTripModel.adEvents.laneAvoid;
                        break;
                    case "cutInLine":
                        result = data.adTripModel.adEvents.cutInLine;
                        break;
                    case "vlm":
                        result = data.adTripModel.adEvents.vlm;
                        break;
                    case "passTollGate":
                        result = data.adTripModel.adEvents.passTollGate;
                        break;
                    case "takeOver":
                        result = data.adTripModel.adEvents.takeOver;
                        break;
                    case "complexScenes":
                        result = data.adTripModel.adEvents.complexScenes;
                        break;
                    case "adDays":
                        result = data.adTripModel.adDays.adDays;
                        break;
                    case "adDaysRatio":
                        result = data.adTripModel.adDays.adDaysRatio;
                        break;
                    case "noaRatio":
                        result = data.adTripModel.adRatio.noaRatio;
                        break;
                    case "accRatio":
                        result = data.adTripModel.adRatio.accRatio;
                        break;
                    case "lccRatio":
                        result = data.adTripModel.adRatio.lccRatio;
                        break;
                    case "adRatio":
                        result = data.adTripModel.adRatio.adRatio;
                        break;
                    case "mileage":
                        result = data.drivingData.mileageData.mileage;
                        break;
                    case "mileageCd":
                        result = data.drivingData.mileageData.mileageCd;
                        break;
                    case "mileageCs":
                        result = data.drivingData.mileageData.mileageCs;
                        break;
                    case "oneHundarFuel":
                        result = data.drivingData.showData.oneHundarFuel;
                        break;
                    case "oneHundarEle":
                        result = data.drivingData.showData.oneHundarEle;
                        break;
                    case "cdShowTime":
                        result = data.drivingData.showData.cdShowTime.hour + ":" + data.drivingData.showData.cdShowTime.minute;
                        break;
                    case "csShowTime":
                        result = data.drivingData.showData.csShowTime.hour + ":" + data.drivingData.showData.csShowTime.minute;
                        break;
                    case "showTime":
                        result = data.drivingData.showData.showTime.hour + ":" + data.drivingData.showData.showTime.minute;
                        break;
                    case "drivingDays":
                        result = data.drivingData.drivingDays.drivingDays;
                        break;
                    case "drivingDuration":
                        result = data.drivingData.drivingDurationData.drivingDuration;
                        break;
                    case "drivingDurationCs":
                        result = data.drivingData.drivingDurationData.drivingDurationCs;
                        break;
                    case "drivingDurationCd":
                        result = data.drivingData.drivingDurationData.drivingDurationCd;
                        break;
                    case "runningDuration":
                        result = data.drivingData.runningDurationData.runningDuration;
                        break;
                    case "drivingAcCd":
                        result = data.energyData.energydis.drivingAcCd;
                        break;
                    case "parkingAc":
                        result = data.energyData.energydis.parkingAc;
                        break;
                    case "drivingDcDcCd":
                        result = data.energyData.energydis.drivingDcDcCd;
                        break;
                    case "parkingDcDc":
                        result = data.energyData.energydis.parkingDcDc;
                        break;
                    case "drivingOutSideCd":
                        result = data.energyData.energydis.drivingOutSideCd;
                        break;
                    case "parkingOutSide":
                        result = data.energyData.energydis.parkingOutSide;
                        break;
                    case "drivingEleCd":
                        result = data.energyData.energydis.drivingEleCd;
                        break;
                    case "drivingFuelCs":
                        result = data.energyData.energydis.drivingFuelCs;
                        break;
                    case "drivingWltcCd":
                        result = data.energyData.endurance.drivingWltcCd;
                        break;
                    case "drivingCltcCd":
                        result = data.energyData.endurance.drivingCltcCd;
                        break;
                    case "parkingWltc":
                        result = data.energyData.endurance.parkingWltc;
                        break;
                    case "parkingCltc":
                        result = data.energyData.endurance.parkingCltc;
                        break;
                    default:
                        break;
                }
                
                // 通知该controlType的所有回调
                callbacks.forEach(({callback}) => {
                    callback(result);
                });
            });
            
        } catch (error) {
            log.e("处理绑定行程数据失败", error);
            // 数据解析失败，通知所有回调返回null
            bindTripDataCache.callbacks.forEach((callbacks, controlType) => {
                callbacks.forEach(({callback}) => {
                    callback(null);
                });
            });
        }
    }

    return function get_bind_trip(id, controlType, callback) {
        const BindTrip_Key = "Vehicle.VehInfo.CarCenter.Trip.BindTrip"; // 绑定行程
        
        // 为每个controlType创建独立的回调集合
        if (!bindTripDataCache.callbacks.has(controlType)) {
            bindTripDataCache.callbacks.set(controlType, new Set());
        }
        
        // 添加回调到对应controlType的集合中
        bindTripDataCache.callbacks.get(controlType).add({id, callback});
        
        // 只在第一次调用时注册监听器
        if (!bindTripDataCache.listenerRegistered) {
            callbackManager.registerCardListener(id, BindTrip_Key, (value) => {
                bindTripDataCache.tripData = value;
                processBindTripData(value);
            });
            bindTripDataCache.listenerRegistered = true;
        }
        
        // 触发初始数据获取（只在第一次调用时）
        if (!bindTripDataCache.initialized) {
            getKeyValue(BindTrip_Key);
            bindTripDataCache.initialized = true;
        }
        
        // 如果已有缓存数据，立即处理
        if (bindTripDataCache.tripData !== null) {
            processBindTripData(bindTripDataCache.tripData);
        }
    };
})();

// 下面几个接口为演示临时添加
// 获取车速
export async function getCarSpeed() {
    let data = null;
    try {
        data = await getVehInfo_Speed();
    } catch (error) {
        log.e("获取数据 " + controlType + " 失败", error);
    }
    return data;
}

// 获取档位
export async function getCarGearShift() {
    let data = null;
    try {
        data = await getVehicleGearShift();
    } catch (error) {
        log.e("获取数据 " + controlType + " 失败", error);
    }
    return data;
}

// 获取NOA占比
export async function getNoaRatio() {
    let result = null;
    try {
        const data = await getBindTrip();
        result = JSON.parse(data).adTripModel.adRatio.noaRatio;
    } catch (error) {
        log.e("获取数据 " + controlType + " 失败", error);
    }
    return result;
}

// 获取续航里程
export async function getMileage() {
    const mileageType = await getEnduranceCondition();
    let data = null;
    try {
        if (mileageType === "CLTC") {
            data = await getCltcPureEvMileage();
        } else if (mileageType === "WLTC") {
            data = await getWltcPureEvMileage();
        }
    } catch (error) {
        log.e("获取数据续航里程失败", error);
    }
    return data;
}