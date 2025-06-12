"""
冒泡排序算法实现和测试
"""


def bubble_sort(arr):
    """
    冒泡排序算法实现
    
    Args:
        arr (list): 需要排序的数组
        
    Returns:
        list: 排序后的数组
    """
    if not arr:
        return arr
    
    # 创建数组的副本，避免修改原数组
    sorted_arr = arr.copy()
    n = len(sorted_arr)
    
    # 外层循环控制排序的轮数
    for i in range(n):
        # 标记是否发生了交换，用于优化
        swapped = False
        
        # 内层循环进行相邻元素比较
        # 每轮排序后，最大的元素会"冒泡"到末尾
        # 所以内层循环的范围逐渐减小
        for j in range(0, n - i - 1):
            if sorted_arr[j] > sorted_arr[j + 1]:
                # 交换相邻元素
                sorted_arr[j], sorted_arr[j + 1] = sorted_arr[j + 1], sorted_arr[j]
                swapped = True
        
        # 如果这一轮没有发生交换，说明数组已经有序，可以提前结束
        if not swapped:
            break
    
    return sorted_arr


def test_bubble_sort():
    """测试冒泡排序算法的各种情况"""
    
    # 测试用例1：正常情况
    test_arr1 = [64, 34, 25, 12, 22, 11, 90]
    expected1 = [11, 12, 22, 25, 34, 64, 90]
    result1 = bubble_sort(test_arr1)
    assert result1 == expected1, f"测试失败：期望 {expected1}，实际 {result1}"
    print(f"测试1通过：{test_arr1} -> {result1}")
    
    # 测试用例2：空数组
    test_arr2 = []
    expected2 = []
    result2 = bubble_sort(test_arr2)
    assert result2 == expected2, f"测试失败：期望 {expected2}，实际 {result2}"
    print(f"测试2通过：{test_arr2} -> {result2}")
    
    # 测试用例3：只有一个元素
    test_arr3 = [42]
    expected3 = [42]
    result3 = bubble_sort(test_arr3)
    assert result3 == expected3, f"测试失败：期望 {expected3}，实际 {result3}"
    print(f"测试3通过：{test_arr3} -> {result3}")
    
    # 测试用例4：已经排序的数组
    test_arr4 = [1, 2, 3, 4, 5]
    expected4 = [1, 2, 3, 4, 5]
    result4 = bubble_sort(test_arr4)
    assert result4 == expected4, f"测试失败：期望 {expected4}，实际 {result4}"
    print(f"测试4通过：{test_arr4} -> {result4}")
    
    # 测试用例5：反向排序的数组
    test_arr5 = [5, 4, 3, 2, 1]
    expected5 = [1, 2, 3, 4, 5]
    result5 = bubble_sort(test_arr5)
    assert result5 == expected5, f"测试失败：期望 {expected5}，实际 {result5}"
    print(f"测试5通过：{test_arr5} -> {result5}")
    
    # 测试用例6：包含重复元素
    test_arr6 = [3, 1, 4, 1, 5, 9, 2, 6, 5]
    expected6 = [1, 1, 2, 3, 4, 5, 5, 6, 9]
    result6 = bubble_sort(test_arr6)
    assert result6 == expected6, f"测试失败：期望 {expected6}，实际 {result6}"
    print(f"测试6通过：{test_arr6} -> {result6}")
    
    # 测试用例7：包含负数
    test_arr7 = [-5, 2, -8, 0, 3, -1]
    expected7 = [-8, -5, -1, 0, 2, 3]
    result7 = bubble_sort(test_arr7)
    assert result7 == expected7, f"测试失败：期望 {expected7}，实际 {result7}"
    print(f"测试7通过：{test_arr7} -> {result7}")
    
    print("\n所有测试用例都通过了！")


def demonstrate_bubble_sort():
    """演示冒泡排序的执行过程"""
    print("=" * 50)
    print("冒泡排序算法演示")
    print("=" * 50)
    
    # 用于演示的数组
    demo_arr = [64, 34, 25, 12, 22, 11, 90]
    print(f"原始数组: {demo_arr}")
    print()
    
    # 详细展示排序过程
    arr = demo_arr.copy()
    n = len(arr)
    
    for i in range(n):
        print(f"第 {i+1} 轮排序:")
        swapped = False
        
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                print(f"  交换 {arr[j]} 和 {arr[j + 1]}")
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        
        print(f"  本轮结束: {arr}")
        
        if not swapped:
            print("  数组已有序，提前结束")
            break
        print()
    
    print(f"最终结果: {arr}")


if __name__ == "__main__":
    # 运行测试
    test_bubble_sort()
    
    # 演示排序过程
    demonstrate_bubble_sort()