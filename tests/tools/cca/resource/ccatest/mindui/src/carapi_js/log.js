// 日志输出+TAG
export function i(...args) {
    console.info('[carapi-js-lib][INFO]', ...args);
}

export function w(...args) {
    console.warn('[carapi-js-lib][WARN]', ...args);
}

export function e(...args) {
    console.error('[carapi-js-lib][ERROR]', ...args);
}

export function d(...args) {
    console.debug('[carapi-js-lib][DEBUG]', ...args);
}