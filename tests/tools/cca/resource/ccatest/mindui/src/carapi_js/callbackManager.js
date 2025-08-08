import { registerListener, unregisterListener } from './utils.js';
import { updateValueAndResolveRequests } from './carApiState.js';
import * as log from './log.js';

class CallbackManager {
    constructor() {
        this.TAG = '[CallbackManager]';
        // 用 Set 记录已监听的 key
        this.listeners = new Set();
        this.callbacks = new Map();
        this.httpCallbacks = new Map();
        // 用于记录和跟踪所有注册的回调ID
        this.allCallbackIds = [];
        // 用 Map 记录已监听的 key 和 id 的对应关系
        this.listenerMap = new Map(); // Map<id, Map<key, Set<callback>>>
    }

    /**
     * 当从车端收到回调时被调用。
     * @param {string} id - 还没想好怎么用
     * @param {string} key - 哪个数据更新了
     * @param {any} newValue - 新的数据值
     */
    onWidgetAgentCallback(id, key, newValue) {
        var str = null;
        if (typeof newValue !== 'string') {
            str = JSON.stringify(newValue);
        } else {
            str = newValue;
        }
        
        // 调用状态管理模块来更新数据和处理挂起的 Promise
        var json = JSON.parse(str);
        log.i(`${this.TAG} 收到${key}的回调 json = ${str}, value = ${json.value} id = ${id}`);
        
        // 检查该 key 是否有注册的监听器
        // 遍历所有 id 的监听器，找到包含该 key 的监听器
        if (this.listenerMap.has(id)) {
            const keyMap = this.listenerMap.get(id);
            if (keyMap.has(key)) {
                const callbacks = keyMap.get(key);
                callbacks.forEach(callback => {
                    callback(json.value);
                });
            }
        } else {
            log.i(`${this.TAG} 收到${key}的回调 id = ${id} 没有监听器`);
        }
        
        updateValueAndResolveRequests(key, json.value);
        // TODO: 32-36行为临时添加
        if (this.callbacks.has(key)) {
            this.callbacks.get(key).forEach(callback => {
                callback(json.value);
            });
        }

        this.pretendArrivalTimeCallback(id, key, json.value);
    }

    pretendArrivalTimeCallback(id, key, newValue) {
        function getArrivalTime(remainTime) {
            if (remainTime == 0) {
                return null;
            }
            const currentTime = new Date();
            const arrivalTime = new Date(currentTime.getTime() + remainTime * 1000);
            return arrivalTime.toLocaleTimeString('zh-CN', { 
                hour: '2-digit', 
                minute: '2-digit',
                hour12: false 
            });
        }
        
        const arrivalTimeKey = "Vehicle.Travel.OneMap.Navi.ArrivalTime";
        const remainTimeKey = "Vehicle.Travel.OneMap.Navi.RemainTime";
        if (key === remainTimeKey) {
            if (this.listenerMap.has(id)) {
                const keyMap = this.listenerMap.get(id);
                if (keyMap.has(arrivalTimeKey)) {
                    const callbacks = keyMap.get(arrivalTimeKey);
                    callbacks.forEach(callback => {
                        callback(getArrivalTime(newValue));
                    });
                }
            }
        }
    }

    // TODO: 临时接口，用于风量和冰箱温度
    addCallback(key, callback) {
        if (this.callbacks.has(key)) {
            this.callbacks.get(key).add(callback);
        } else {
            this.callbacks.set(key, new Set());
            this.callbacks.get(key).add(callback);
        }
    }

    addHttpCallback(id, callback) {
        // 记录回调ID，用于调试
        this.allCallbackIds.push({
            id: id,
            timestamp: Date.now()
        });
        
        // 打印所有回调ID，便于调试
        const callbackIdsStr = this.allCallbackIds.map(item => `${item.id}(${new Date(item.timestamp).toLocaleTimeString()})`).join(', ');
        log.i(`${this.TAG} 所有已注册的回调ID: ${callbackIdsStr}`);
        
        if (this.httpCallbacks.has(id)) {
            this.httpCallbacks.get(id).add(callback);
            log.i(`${this.TAG} addHttpCallback 添加回调 ${id} 的回调, 该id已存在回调个数: ${this.httpCallbacks.get(id).size}`);
        } else {
            this.httpCallbacks.set(id, new Set());
            this.httpCallbacks.get(id).add(callback);
            log.i(`${this.TAG} addHttpCallback 添加回调 ${id} 的回调, 该id不存在回调, 添加后回调个数: ${this.httpCallbacks.get(id).size}`);
        }
        
        // 打印当前活跃的回调ID
        const activeCallbackIds = Array.from(this.httpCallbacks.keys());
        log.i(`${this.TAG} 当前活跃的回调ID: ${activeCallbackIds.join(', ')}`);
    }

    onHttpResponse(callbackId, response) {
        // 打印收到的回调ID和响应类型
        const responseType = typeof response;
        let responseStr = '未知';
        
        if (response === null || response === undefined) {
            responseStr = '空值';
        } else if (responseType === 'object') {
            try {
                responseStr = JSON.stringify(response).substring(0, 100) + '...';
            } catch (e) {
                responseStr = '[无法序列化的对象]';
            }
        } else if (responseType === 'string') {
            responseStr = response.substring(0, 100) + (response.length > 100 ? '...' : '');
        } else {
            responseStr = String(response);
        }
        
        log.i(`${this.TAG} onHttpResponse 收到回调, 类型: ${responseType}, 内容: ${responseStr}`);
        
        // 获取当前所有活跃的回调ID
        const activeCallbackIds = Array.from(this.httpCallbacks.keys());
        
        // 检查是否有任何存储的回调ID
        if (activeCallbackIds.length > 0) {
            // 获取第一个回调ID
            const firstCallbackId = activeCallbackIds[0];
            
            log.i(`${this.TAG} 找到存储的回调ID: ${firstCallbackId}, 执行回调并清空所有回调`);
            
            // 执行第一个回调
            if (this.httpCallbacks.has(firstCallbackId)) {
                const callbacks = this.httpCallbacks.get(firstCallbackId);
                callbacks.forEach(callback => {
                    try {
                        callback(response);
                    } catch (error) {
                        log.e(`${this.TAG} 执行回调出错: ${error}`);
                    }
                });
            }
            
            // 清空所有回调
            this.httpCallbacks.clear();
            log.i(`${this.TAG} 已清空所有回调`);
        } else {
            log.w(`${this.TAG} 没有存储的回调ID，忽略此回调`);
        }
    }

    /**
     * 确保一个 key 正在被监听。
     * 这是幂等的，重复调用不会产生副作用。
     * @param {string} key
     */
    ensureListener(id, key) {
        if (!this.listeners.has(key)) {
            if (registerListener(id, key)) {
                this.listeners.add(key);
                log.i(`${this.TAG} 开始监听 ${key}`);
                return true;
            } else {
                log.e(`${this.TAG} 开始监听 ${key} 失败`);
                return false;
            }
        } else {
            // log.i(`${this.TAG} 已监听 ${key}`);
            return true;
        }
    }

    registerCardListener(id, key, callback) {
        // 如果该 id 还没有注册过，创建一个新的 keyMap
        if (!this.listenerMap.has(id)) {
            this.listenerMap.set(id, new Map());
        }
        
        const keyMap = this.listenerMap.get(id);
        
        // 如果该 id 还没有监听过这个 key，创建一个新的 callback Set
        if (!keyMap.has(key)) {
            keyMap.set(key, new Set());
            // 注册监听器
            registerListener(id, key);
        }
        
        // 添加 callback 到该 key 的 Set 中
        keyMap.get(key).add(callback);
    }

    unregisterCardListener(id) {
        log.i(`${this.TAG} unregisterCardListener 取消监听 ${id}`);
        if (!this.listenerMap.has(id)) {
            return;
        }
        const keyMap = this.listenerMap.get(id);
        keyMap.forEach((callbacks, key) => {
            unregisterListener(id, key);

        });
        this.listenerMap.delete(id);
    }

    /**
     * 停止监听一个 key。
     * 注意: 在更复杂的应用中，您可能需要一个引用计数系统来决定何时真正调用 unregisterListener，
     * 以免一个组件停止监听而影响到另一个也需要该数据的组件。
     * @param {string} key
     */
    removeListener(id, key) {
        if (this.listeners.has(key)) {
            this.listeners.delete(key);
            unregisterListener(id, key);
            log.i(`${this.TAG} 停止监听 ${key}`);
        }
    }
    
    /**
     * 重置回调处理状态
     */
    resetCallbackState() {
        // 清空所有HTTP回调
        this.httpCallbacks.clear();
        log.i(`${this.TAG} 重置回调处理状态，清空所有HTTP回调`);
    }
}

// 导出类的实例，使其成为单例模式
const callbackManager = new CallbackManager();
export default callbackManager;
window.callbackManager = callbackManager;