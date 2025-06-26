import os
from pathlib import Path

import pandas as pd

from siada.foundation.logging import logger
from benchmark.swe.eval_framework import run_evaluation
from benchmark.swe.tools.parser import get_parser
from benchmark.swe.run_instance import process_instance


def find_git_root(start_path=None):
    """
    通过向上查找 .git 目录来确定 Git 仓库根目录
    """
    if start_path is None:
        start_path = os.getcwd()

    current_path = Path(start_path).resolve()

    # 向上遍历目录
    for parent in [current_path] + list(current_path.parents):
        git_dir = parent / '.git'
        if git_dir.exists():
            return str(parent)

    raise Exception("未找到 Git 仓库根目录")


def download_dataset():
    logger.info("Start ...")
    parser = get_parser()
    args, _ = parser.parse_known_args()

    output_file = os.path.join(args.output_dir, 'output.jsonl')

    # Get dataset from local
    instances = pd.read_csv(find_git_root() + '/swebench_test.csv', encoding='utf-8', dtype=str).astype(str).replace(
        'nan', '')

    # Get dataset from huggingface
    # swe_bench_test_dataset = load_huggingface_swe_bench_dataset(args.dataset, args.split)
    # instances = prepare_dataset(swe_bench_test_dataset.to_pandas(), output_file, 300)

    if len(instances) > 0 and not isinstance(
            instances['PASS_TO_PASS'][instances['PASS_TO_PASS'].index[0]], str
    ):
        for col in ['PASS_TO_PASS', 'FAIL_TO_PASS']:
            instances[col] = instances[col].apply(lambda x: str(x))

    return instances, output_file, args.target_instance


if __name__ == '__main__':
    instances, output_file, target_instance = download_dataset()

    run_evaluation(
        instances, output_file, process_instance,
        target_instance=target_instance,
        excluded_instance_ids=None
    )
