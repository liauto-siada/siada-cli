/**
 * Sample JavaScript file for testing ReadManyFiles tool.
 */

function greetUser(name) {
    return `Hello, ${name}!`;
}

class MathUtils {
    static add(a, b) {
        return a + b;
    }
    
    static multiply(a, b) {
        return a * b;
    }
}

// Export for Node.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { greetUser, MathUtils };
}

console.log(greetUser("World"));
console.log("5 + 3 =", MathUtils.add(5, 3));
