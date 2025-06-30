"""
冒泡排序算法实现

这个模块包含了冒泡排序算法的实现和相关的测试函数。
冒泡排序是一种简单的排序算法，通过重复遍历要排序的列表，
比较相邻元素并在它们顺序错误时交换它们的位置。
"""


def bubble_sort(arr):
    """
    使用冒泡排序算法对数组进行排序
    
    Args:
        arr (list): 要排序的数组
        
    Returns:
        list: 排序后的数组
        
    时间复杂度: O(n²)
    空间复杂度: O(1)
    """
    if not arr:
        return arr
    
    n = len(arr)
    # 创建数组的副本以避免修改原数组
    sorted_arr = arr.copy()
    
    # 外层循环控制排序轮数
    for i in range(n):
        # 标记本轮是否发生了交换
        swapped = False
        
        # 内层循环进行相邻元素比较和交换
        # 每轮循环后，最大的元素会"冒泡"到数组末尾
        for j in range(0, n - i - 1):
            # 如果当前元素大于下一个元素，则交换
            if sorted_arr[j] > sorted_arr[j + 1]:
                sorted_arr[j], sorted_arr[j + 1] = sorted_arr[j + 1], sorted_arr[j]
                swapped = True
        
        # 如果本轮没有发生交换，说明数组已经有序，可以提前退出
        if not swapped:
            break
    
    return sorted_arr


def bubble_sort_descending(arr):
    """
    使用冒泡排序算法对数组进行降序排序
    
    Args:
        arr (list): 要排序的数组
        
    Returns:
        list: 降序排序后的数组
    """
    if not arr:
        return arr
    
    n = len(arr)
    sorted_arr = arr.copy()
    
    for i in range(n):
        swapped = False
        for j in range(0, n - i - 1):
            # 改变比较条件实现降序排序
            if sorted_arr[j] < sorted_arr[j + 1]:
                sorted_arr[j], sorted_arr[j + 1] = sorted_arr[j + 1], sorted_arr[j]
                swapped = True
        
        if not swapped:
            break
    
    return sorted_arr


def bubble_sort_with_steps(arr):
    """
    带步骤显示的冒泡排序，用于演示排序过程
    
    Args:
        arr (list): 要排序的数组
        
    Returns:
        tuple: (排序后的数组, 排序步骤列表)
    """
    if not arr:
        return arr, []
    
    n = len(arr)
    sorted_arr = arr.copy()
    steps = [f"初始数组: {sorted_arr}"]
    
    for i in range(n):
        swapped = False
        round_steps = []
        
        for j in range(0, n - i - 1):
            if sorted_arr[j] > sorted_arr[j + 1]:
                sorted_arr[j], sorted_arr[j + 1] = sorted_arr[j + 1], sorted_arr[j]
                round_steps.append(f"交换 {sorted_arr[j+1]} 和 {sorted_arr[j]}: {sorted_arr}")
                swapped = True
        
        if round_steps:
            steps.append(f"第 {i+1} 轮:")
            steps.extend(round_steps)
        
        if not swapped:
            steps.append("数组已有序，提前结束")
            break
    
    steps.append(f"最终结果: {sorted_arr}")
    return sorted_arr, steps


def test_bubble_sort():
    """
    测试冒泡排序算法的功能
    """
    print("=== 冒泡排序算法测试 ===\n")
    
    # 测试用例1: 普通数组
    test_array1 = [64, 34, 25, 12, 22, 11, 90]
    print(f"测试1 - 原数组: {test_array1}")
    sorted1 = bubble_sort(test_array1)
    print(f"排序结果: {sorted1}")
    print(f"是否正确: {sorted1 == sorted(test_array1)}\n")
    
    # 测试用例2: 已排序数组
    test_array2 = [1, 2, 3, 4, 5]
    print(f"测试2 - 已排序数组: {test_array2}")
    sorted2 = bubble_sort(test_array2)
    print(f"排序结果: {sorted2}")
    print(f"是否正确: {sorted2 == sorted(test_array2)}\n")
    
    # 测试用例3: 逆序数组
    test_array3 = [5, 4, 3, 2, 1]
    print(f"测试3 - 逆序数组: {test_array3}")
    sorted3 = bubble_sort(test_array3)
    print(f"排序结果: {sorted3}")
    print(f"是否正确: {sorted3 == sorted(test_array3)}\n")
    
    # 测试用例4: 空数组
    test_array4 = []
    print(f"测试4 - 空数组: {test_array4}")
    sorted4 = bubble_sort(test_array4)
    print(f"排序结果: {sorted4}")
    print(f"是否正确: {sorted4 == []}\n")
    
    # 测试用例5: 单个元素
    test_array5 = [42]
    print(f"测试5 - 单个元素: {test_array5}")
    sorted5 = bubble_sort(test_array5)
    print(f"排序结果: {sorted5}")
    print(f"是否正确: {sorted5 == [42]}\n")
    
    # 测试用例6: 有重复元素
    test_array6 = [3, 7, 3, 1, 7, 3, 9, 1]
    print(f"测试6 - 有重复元素: {test_array6}")
    sorted6 = bubble_sort(test_array6)
    print(f"排序结果: {sorted6}")
    print(f"是否正确: {sorted6 == sorted(test_array6)}\n")
    
    # 测试降序排序
    print("=== 降序排序测试 ===")
    test_array7 = [64, 34, 25, 12, 22, 11, 90]
    print(f"原数组: {test_array7}")
    sorted7 = bubble_sort_descending(test_array7)
    print(f"降序结果: {sorted7}")
    print(f"是否正确: {sorted7 == sorted(test_array7, reverse=True)}\n")
    
    # 演示排序步骤
    print("=== 排序步骤演示 ===")
    demo_array = [64, 34, 25, 12]
    print(f"演示数组: {demo_array}")
    result, steps = bubble_sort_with_steps(demo_array)
    for step in steps:
        print(step)


if __name__ == "__main__":
    # 运行测试
    test_bubble_sort()