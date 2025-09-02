#!/bin/bash
echo "=== 按文件夹统计 Problem Description 数量 ==="
echo ""

total=0

# 遍历 gold/ 下的所有子文件夹
for dir in */; do
    if [ -f "$dir/report.json" ]; then
        count=$(grep -c "\"resolved\": true," "$dir/report.json")
        folder_name=$(basename "$dir")
        echo "$folder_name: $count"
        total=$((total + count))
    fi
done

echo ""
echo "总计: $total"

