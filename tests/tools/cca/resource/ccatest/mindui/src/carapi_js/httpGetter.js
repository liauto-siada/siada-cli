import callbackManager from "./callbackManager.js";
import * as log from "./log.js";
export function getHttpData(url, headers = "") {
    try {
        const result = window.widgetBridge.httpGet(url, headers);
        log.i("httpGetter result", result);
        return result;
    } catch (error) {
        log.e("httpGetter error", error, "url: " + url + ", headers: " + headers);
        return null;
    }
}

export function getHttpDataAsync(url, headers = "", callbackId, callback) {
    log.i("getHttpDataAsync url: " + url + ", headers: " + headers + ", callbackId: " + callbackId);
    if (window.widgetBridge.getBridgeAPIVersion() < 2) {
        log.i("Bridge API 版本小于2, 使用同步接口");
        callback(getHttpData(url, headers));
        return;
    }
    try {
        callbackManager.addHttpCallback(callbackId, callback);
        window.widgetBridge.httpGetAsync(url, headers, callbackId);
    } catch (error) {
        log.e("httpGetter error", error, "url: " + url + ", headers: " + headers);
        callback(null);
    } 
}