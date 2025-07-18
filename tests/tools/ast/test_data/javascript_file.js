/**
 * JavaScript测试文件
 * 包含各种JavaScript定义
 */

// 函数定义
function simpleFunction(x, y) {
    return x + y;
}

// 箭头函数
const arrowFunction = (a, b) => {
    return a * b;
};

// 类定义
class TestClass {
    constructor(name) {
        this.name = name;
    }
    
    getName() {
        return this.name;
    }
    
    setName(name) {
        this.name = name;
    }
    
    static staticMethod() {
        return "static";
    }
}

// 异步函数
async function asyncFunction() {
    const result = await fetch('/api/data');
    return result.json();
}

// 对象方法
const objectWithMethods = {
    method1: function() {
        return "method1";
    },
    
    method2() {
        return "method2";
    }
};

// 导出
module.exports = {
    simpleFunction,
    arrowFunction,
    TestClass,
    asyncFunction,
    objectWithMethods
};
