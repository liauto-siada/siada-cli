import * as log from './log.js';
// carApiState.js - 这是一个用来存储和管理车端接口状态的模块

// 存储最新的已知值，key 是接口路径
const valueCache = new Map();

// 存储正在等待数据的请求
// 结构: { key: [{ resolve, reject, timeoutId }, ...] }
const pendingRequests = new Map();


/**
 * 当收到新的数据时，更新缓存并解决所有等待该数据的请求。
 * @param {string} key 数据路径
 * @param {any} newValue 新的值
 */
export function updateValueAndResolveRequests(key, newValue) {
    if (valueCache.has(key) && (newValue === undefined || newValue === null)) {
        log.e(`[State] 收到 ${key} 的值为 undefined 或 null。`);
        return;
    }
    // 1. 更新缓存
    // valueCache.set(key, newValue);

    // 2. 检查是否有等待这个 key 的请求
    if (pendingRequests.has(key)) {
        const requests = pendingRequests.get(key);
        log.i(`[State] 收到 ${key} 的值: ${newValue}。正在处理 ${requests.length} 个挂起的请求。`);

        // 3. 遍历并解决所有挂起的请求
        requests.forEach(({ resolve, timeoutId }) => {
            clearTimeout(timeoutId); // 清除超时定时器
            resolve(newValue);
        });

        // 4. 清理已处理的请求
        pendingRequests.delete(key);
    }
}

/**
 * 添加一个新的挂起请求。
 * @param {string} key
 * @param {object} requestInfo - 包含 { resolve, reject, timeoutId }
 */
export function addPendingRequest(key, requestInfo) {
    if (!pendingRequests.has(key)) {
        pendingRequests.set(key, []);
    }
    pendingRequests.get(key).push(requestInfo);
}

/**
 * 获取缓存的值。
 * @param {string} key
 * @returns {any | undefined}
 */
export function getCachedValue(key) {
    return valueCache.get(key);
}

/**
 * 移除一个挂起的请求（例如，当它超时时）。
 * @param {string} key
 * @param {object} requestInfo
 */
export function removePendingRequest(key, requestInfo) {
    if (pendingRequests.has(key)) {
        const requests = pendingRequests.get(key).filter(req => req !== requestInfo);
        if (requests.length === 0) {
            pendingRequests.delete(key);
        } else {
            pendingRequests.set(key, requests);
        }
    }
}