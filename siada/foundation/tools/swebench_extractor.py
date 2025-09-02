import csv
import os
from pathlib import Path
from typing import List, Optional


class SWEBenchExtractor:
    """工具类，用于从SWEBench CSV文件中提取指定instance_id的problem_statement。"""

    @staticmethod
    def extract_problem_statements(
        csv_path: str,
        instance_ids: List[str],
        output_base_dir: str
    ) -> dict:
        """
        从CSV文件中提取指定instance_id的problem_statement并保存到指定目录。

        Args:
            csv_path: CSV文件的路径
            instance_ids: 要提取的instance_id列表
            output_base_dir: 输出目录的基础路径

        Returns:
            dict: 包含成功和失败信息的字典
        """
        csv_path = Path(csv_path)
        output_base_dir = Path(output_base_dir)
        
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV文件不存在: {csv_path}")
        
        # 确保输出目录存在
        output_base_dir.mkdir(parents=True, exist_ok=True)
        
        extracted_count = 0
        failed_instances = []
        found_instances = {}
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                # 使用csv.DictReader来读取CSV文件
                reader = csv.DictReader(csvfile)
                
                for row in reader:
                    instance_id = row.get('instance_id', '').strip()
                    
                    if instance_id in instance_ids:
                        problem_statement = row.get('problem_statement', '').strip()
                        patch = row.get('patch', '').strip()
                        test_patch = row.get('test_patch', '').strip()
                        
                        if problem_statement:
                            # 创建instance_id对应的目录
                            instance_dir = output_base_dir / instance_id
                            instance_dir.mkdir(parents=True, exist_ok=True)
                            
                            files_written = []
                            
                            try:
                                # 写入problem_statement.txt文件
                                problem_file = instance_dir / 'problem_statement.txt'
                                with open(problem_file, 'w', encoding='utf-8') as f:
                                    f.write(problem_statement)
                                files_written.append('problem_statement.txt')
                                
                                # 写入patch.txt文件
                                if patch:
                                    patch_file = instance_dir / 'patch.txt'
                                    with open(patch_file, 'w', encoding='utf-8') as f:
                                        f.write(patch)
                                    files_written.append('patch.txt')
                                
                                # 写入test_patch.txt文件
                                if test_patch:
                                    test_patch_file = instance_dir / 'test_patch.txt'
                                    with open(test_patch_file, 'w', encoding='utf-8') as f:
                                        f.write(test_patch)
                                    files_written.append('test_patch.txt')
                                
                                found_instances[instance_id] = str(instance_dir)
                                extracted_count += 1
                                print(f"✓ 已提取 {instance_id} 到 {instance_dir} (文件: {', '.join(files_written)})")
                                
                            except Exception as e:
                                failed_instances.append(f"{instance_id}: 写入文件失败 - {str(e)}")
                                print(f"✗ 写入失败 {instance_id}: {str(e)}")
                        else:
                            failed_instances.append(f"{instance_id}: problem_statement为空")
                            print(f"✗ {instance_id}: problem_statement为空")
        
        except Exception as e:
            raise Exception(f"读取CSV文件失败: {str(e)}")
        
        # 检查哪些instance_id没有找到
        missing_instances = set(instance_ids) - set(found_instances.keys())
        for missing_id in missing_instances:
            failed_instances.append(f"{missing_id}: 在CSV文件中未找到")
            print(f"✗ {missing_id}: 在CSV文件中未找到")
        
        result = {
            'extracted_count': extracted_count,
            'total_requested': len(instance_ids),
            'found_instances': found_instances,
            'failed_instances': failed_instances,
            'output_directory': str(output_base_dir)
        }
        
        print(f"\n提取完成: {extracted_count}/{len(instance_ids)} 个实例成功提取")
        
        return result

    @staticmethod
    def extract_all_instances(
        csv_path: str = "/Users/caoxin/Projects/AgentHub/siada-agenthub/swebench_test.csv",
        output_dir: str = "/Users/caoxin/Projects/latest_agent/logs/checker_link/gold/"
    ) -> dict:
        """
        提取CSV文件中的所有instance_id的problem_statement。

        Args:
            csv_path: CSV文件路径，默认为指定路径
            output_dir: 输出目录，默认为指定路径

        Returns:
            dict: 提取结果
        """
        csv_path = Path(csv_path)
        
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV文件不存在: {csv_path}")
        
        # 读取CSV文件获取所有instance_id
        target_instances = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    instance_id = row.get('instance_id', '').strip()
                    if instance_id:
                        target_instances.append(instance_id)
        except Exception as e:
            raise Exception(f"读取CSV文件失败: {str(e)}")
        
        print(f"开始提取 {len(target_instances)} 个实例的problem_statement...")
        print(f"CSV文件路径: {csv_path}")
        print(f"输出目录: {output_dir}")
        print("-" * 60)
        
        return SWEBenchExtractor.extract_problem_statements(
            csv_path=csv_path,
            instance_ids=target_instances,
            output_base_dir=output_dir
        )

    @staticmethod
    def extract_specific_instances(
        csv_path: str = "/Users/caoxin/Projects/AgentHub/siada-agenthub/swebench_test.csv",
        output_dir: str = "/Users/caoxin/Projects/latest_agent/logs/django_41_902_1/gold/"
    ) -> dict:
        """
        根据output_dir目录中已有的文件夹名称来提取对应的instance_id的problem_statement。

        Args:
            csv_path: CSV文件路径，默认为指定路径
            output_dir: 输出目录，默认为指定路径。将扫描此目录下的文件夹名称作为instance_id列表

        Returns:
            dict: 提取结果
        """
        output_path = Path(output_dir)
        
        # 检查输出目录是否存在
        if not output_path.exists():
            print(f"输出目录不存在，将创建: {output_path}")
            output_path.mkdir(parents=True, exist_ok=True)
            target_instances = []
        else:
            # 扫描输出目录，获取所有子文件夹名称作为instance_id
            target_instances = []
            for item in output_path.iterdir():
                if item.is_dir():
                    instance_id = item.name
                    # 验证文件夹名称是否符合instance_id格式（包含双下划线）
                    if '__' in instance_id:
                        target_instances.append(instance_id)
                    else:
                        print(f"⚠️  跳过不符合格式的文件夹: {instance_id}")
        
        if not target_instances:
            print("❌ 在输出目录中没有找到任何符合格式的instance_id文件夹")
            print("提示: instance_id文件夹格式应为 'project__repo-number'，例如 'django__django-12308'")
            return {
                'extracted_count': 0,
                'total_requested': 0,
                'found_instances': {},
                'failed_instances': ['输出目录中没有找到任何符合格式的instance_id文件夹'],
                'output_directory': str(output_path)
            }
        
        # 按字母顺序排序
        target_instances.sort()
        
        print(f"📁 从输出目录扫描到 {len(target_instances)} 个instance_id:")
        for i, instance_id in enumerate(target_instances, 1):
            print(f"   {i:2d}. {instance_id}")
        
        print(f"\n开始提取 {len(target_instances)} 个实例的problem_statement...")
        print(f"CSV文件路径: {csv_path}")
        print(f"输出目录: {output_dir}")
        print("-" * 60)
        
        return SWEBenchExtractor.extract_problem_statements(
            csv_path=csv_path,
            instance_ids=target_instances,
            output_base_dir=output_dir
        )


# Example usage
if __name__ == "__main__":
    try:
        # 默认提取所有实例
        result = SWEBenchExtractor.extract_specific_instances()
        
        print("\n" + "=" * 60)
        print("提取结果摘要:")
        print(f"成功提取: {result['extracted_count']}/{result['total_requested']}")
        print(f"输出目录: {result['output_directory']}")
        
        if result['failed_instances']:
            print(f"\n失败的实例 ({len(result['failed_instances'])}):")
            for failed in result['failed_instances']:
                print(f"  - {failed}")
                
    except Exception as e:
        print(f"错误: {e}")
