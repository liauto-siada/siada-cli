import csv
import json
import os


def process_sympy_csv_to_json():
    """
    读取 swebench_ps.csv 文件，筛选 sympy__sympy 前缀的数据，
    转换为 JSON 格式并输出到文件
    """
    # 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 输入和输出文件路径
    input_file = os.path.join(current_dir, 'swebench_ps.csv')
    output_file = os.path.join(current_dir, 'sympy_problems.json')
    
    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    sympy_data = []
    
    # 尝试不同的编码格式来读取 CSV 文件
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            with open(input_file, 'r', encoding=encoding) as csvfile:
                reader = csv.DictReader(csvfile)
                
                # 检查必要的列是否存在
                if 'instance_id' not in reader.fieldnames or 'problem_statement' not in reader.fieldnames:
                    raise ValueError("CSV file must contain 'instance_id' and 'problem_statement' columns")
                
                print(f"Successfully opened file with encoding: {encoding}")
                
                # 逐行读取并处理数据
                for row in reader:
                    instance_id = row['instance_id']
                    problem_statement = row['problem_statement']
                    
                    # 只处理 instance_id 前缀为 sympy__sympy 的数据
                    if instance_id.startswith('sympy__sympy'):
                        sympy_data.append({
                            'instance_id': instance_id,
                            'problem_statement': problem_statement
                        })
                
                # 如果成功读取完整个文件，跳出循环
                break
                
        except UnicodeDecodeError:
            print(f"Failed to read with encoding: {encoding}")
            continue
    
    if not sympy_data:
        # 检查是否因为编码问题导致没有读取到任何数据
        print("Warning: No sympy data found. This might be due to encoding issues.")
    
    # 将数据写入 JSON 文件
    with open(output_file, 'w', encoding='utf-8') as jsonfile:
        json.dump(sympy_data, jsonfile, ensure_ascii=False, indent=2)
    
    print(f"Successfully processed {len(sympy_data)} sympy records")
    print(f"Output saved to: {output_file}")
    
    return output_file


if __name__ == "__main__":
    # 如果直接运行此文件，执行处理函数
    process_sympy_csv_to_json()
