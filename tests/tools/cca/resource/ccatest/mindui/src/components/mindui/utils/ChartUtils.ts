const ChartUtils = {
  calculateAxisProps: (data: number[]) => {
    if (data.length === 0) return { maxValue: 100, ticks: [0, 25, 50, 75, 100] };

    const maxDataValue = Math.max(...data);

    // 计算合适的步长（确保刻度是等差数列）
    const exponent = Math.floor(Math.log10(maxDataValue));
    const power = Math.pow(10, exponent);
    const normalizedValue = maxDataValue / power;

    let step;
    if (normalizedValue < 2) {
      step = 0.2 * power;
    } else if (normalizedValue < 5) {
      step = 0.5 * power;
    } else {
      step = power;
    }

    // 计算最大值 - 确保柱子高度可以超过最大刻度值
    const maxValue = Math.ceil(maxDataValue / step) * step;

    // 生成等差数列刻度
    const ticks = [];
    for (let i = 0; i <= maxValue; i += step) {
      // 只添加小于等于最大值的刻度（避免顶部空白线）
      if (i <= maxValue) {
        ticks.push(i);
      }
    }

    return { maxValue, ticks };
  },

  calculateAxisProps2: (data: number[]) => {
    if (data.length === 0) return { minValue: 0, maxValue: 100, ticks: [0, 25, 50, 75, 100] };

    // 获取数据最小值和最大值
    const values = data;
    const minDataValue = Math.min(...values);
    const maxDataValue = Math.max(...values);

    // 计算数据范围
    const dataRange = maxDataValue - minDataValue;

    // 计算合适的步长（确保刻度是等差数列）
    const exponent = Math.floor(Math.log10(dataRange));
    const power = Math.pow(10, exponent);
    const normalizedRange = dataRange / power;

    let step;
    if (normalizedRange < 2) {
      step = 0.2 * power;
    } else if (normalizedRange < 5) {
      step = 0.5 * power;
    } else {
      step = power;
    }

    // 计算最小值（向下取整到最近的步长倍数，并留出间距）
    const minValue = Math.floor((minDataValue - step * 0.2) / step) * step;

    // 计算最大值（向上取整到最近的步长倍数，并允许数据超出）
    const maxValue = Math.ceil((maxDataValue + step * 0.2) / step) * step;

    // 生成等差数列刻度
    const ticks = [];
    for (let i = minValue; i <= maxValue; i += step) {
      // 保留两位小数避免浮点精度问题
      const tickValue = parseFloat(i.toFixed(10));

      // 确保刻度值在范围内
      if (tickValue >= minValue && tickValue <= maxValue) {
        ticks.push(tickValue);
      }
    }

    return { minValue, maxValue, ticks };
  }
};

export default ChartUtils;