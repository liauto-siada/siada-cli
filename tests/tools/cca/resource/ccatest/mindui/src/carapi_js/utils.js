import * as log from './log.js';
import { getterMap } from './carApiGetter.js';

//******************** 车端通信接口封装 ********************
/**
 * 调用设置类车端接口
 * @param {string} key 要设置的功能对应的path
 * @param {string} target 设置的具体目标
 * @param {string} value 设置的值，可选
 * @returns {string} 返回结果
 */
export function setKeyValue(key, target, value) {
    try {
        const result = window.widgetBridge.call(JSON.stringify({
            type: "set",
            data: JSON.stringify({
                key: key,
                value: JSON.stringify({
                    target: target,
                    value: String(value)
                })
            })
        }));
        return result;
    } catch (error) {
        log.e("设置键值对失败", error);
        return false;
    }
}

export function setKeyValueWithSource(key, target, value) {
    console.log("setKeyValueWithSource", key, target, value);
    try {
        const result = window.widgetBridge.call(JSON.stringify({
            type: "set",
            data: JSON.stringify({
                key: key,
                value: JSON.stringify({
                    target: target,
                    value: String(value),
                    action_from: "cca"
                })
            })
        }));
        return result;
    } catch (error) {
        log.e("设置键值对失败", error);
        return false;
    }
}

export function setKeyValueWithoutValue(key, target) {
    console.log("setKeyValueWithoutValue", key, target);
    try {
        const result = window.widgetBridge.call(JSON.stringify({
            type: "set",
            data: JSON.stringify({
                key: key,
                value: JSON.stringify({
                    target: target,
                    action_from: "cca"
                })
            })
        }));
        return result;
    } catch (error) {
        log.e("设置键值对失败", error);
        return false;
    }
}

/**
 * 调用获取类车端接口
 * @param {string} key 要获取的功能对应的path
 * @param {string} extras 额外参数，可选
 * @returns {string} 返回结果
 */
export function getKeyValue(key, extras = "") {
    try {
        const result = window.widgetBridge.call(JSON.stringify({
            type: "get",
            data: JSON.stringify({
                key: key,
                extras: extras
            })
        }));
        return result;
    } catch (error) {
        log.e("获取键值对失败", error);
        return null;
    }
}

/**
 * 注册监听器
 * @param {string} id 监听器id
 * @param {string} key 要监听的功能对应的path
 * @param {function} callback 回调函数
 * @returns {string} 返回结果
 */
export function registerListener(id, key) {
    const arrivalTimeKey = "Vehicle.Travel.OneMap.Navi.ArrivalTime";
    if (key === arrivalTimeKey) {
        return;
    }
    try {
        const param = JSON.stringify({
            id: id,
            key: key
        });
        const result = window.widgetBridge.registerListener(param);
        return result;
    } catch (error) {
        log.e("注册监听器失败", error);
        return false;
    }
}

/**
 * 注销监听器
 * @param {string} id 监听器id
 * @param {string} key 要注销的功能对应的path
 * @returns {string} 返回结果
 */
export function unregisterListener(id, key) {
    try {
        const param = JSON.stringify({
            id: id,
            key: key
        });
        const result = window.widgetBridge.unregisterListener(param);
        return result;
    } catch (error) {
        log.e("注销监听器失败", error);
        return false;
    }
}

//******************** 模型端接口封装 ********************
export async function makeAllData(typeList) {
    var data = {};
    for (var i = 0; i < typeList.length; i++) {
        data[typeList[i]] = await getterMap[typeList[i]]();
    }
    return {
        success: true,
        code: 0,
        data: data
    };
}

export async function makeData(controlType) {
    var success = true;
    var code = 0;
    var data = null;
    try {
        data = await getterMap[controlType]();
    } catch (error) {
        log.e("获取数据 " + controlType + " 失败", error);
        success = false;
    } finally {
        return makeDataBase(controlType, data, success, code);
    }
}

export function makeDataBase(controlType, data, success, code) {
    return {
        success: success,
        code: code,
        data: {
            [controlType]: data
        }
    };
}

// 返回一个整数随机数，范围为min到max（包括min和max）
export function getRandomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1) + min);
}