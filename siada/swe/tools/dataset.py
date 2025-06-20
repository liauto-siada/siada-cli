import json
import os
import platform
import time
from typing import Optional

import pandas as pd
from datasets import load_dataset

from siada.foundation.logging import logger
from siada.swe.tools.gateway import set_huggingface_gateway, unset_huggingface_gateway


def load_huggingface_swe_bench_dataset(dataset_name, dataset_split):
    logger.info(f'Loaded dataset {dataset_name} with split {dataset_split}')
    # 加载数据集
    # 云主机可能出现网关问题，判断当前运行程序的主机是 macos 还是 linux，如果是 linux 则设置网关
    if "linux" in platform.system().lower():
        logger.info("已开启网关")
        set_huggingface_gateway()
    # set_huggingface_gateway()
    retries = 0
    while retries < 5:
        try:
            dataset = load_dataset(dataset_name, split=dataset_split)
            return dataset
        except Exception as e:
            print(f"加载失败: {e}. 正在重试...({retries + 1}/5)")
            retries += 1
            time.sleep(5)
    if retries == 5:
        if "linux" in platform.system().lower():
            logger.info("已关闭网关")
            unset_huggingface_gateway()
        # unset_huggingface_gateway()
        raise Exception("多次尝试加载数据集失败")


def filter_dataset(dataset: pd.DataFrame, filter_column: str) -> pd.DataFrame:
    """
    没看懂原来 SWE-BENCH 代码中这一段想干什么。
    """

    # file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.toml')
    # if os.path.exists(file_path):
    #     with open(file_path, 'r') as file:
    #         data = toml.load(file)
    #         if 'selected_ids' in data:
    #             selected_ids = data['selected_ids']
    #             logger.info(
    #                 f'Filtering {len(selected_ids)} tasks from "selected_ids"...'
    #             )
    #             subset = dataset[dataset[filter_column].isin(selected_ids)]
    #             logger.info(f'Retained {subset.shape[0]} tasks after filtering')
    #             return subset
    return dataset


def prepare_dataset(
    dataset: pd.DataFrame,
    output_file: str,
    eval_n_limit: int,
    eval_ids: list[str] = None,
    skip_num: Optional[int] = None,
):
    """
    该函数 prepare_dataset 的主要功能是准备用于评估的数据集，具体包括以下逻辑：
        检查数据列：确保输入数据包含 'instance_id' 列作为唯一标识。
        读取已完成ID：若输出文件存在，从中加载已处理完成的实例ID。
        筛选待处理数据：
        若指定了 eval_ids，则只保留这些ID对应的实例；
        否则若设置了 skip_num，则跳过前N个实例，并可结合 eval_n_limit 限制数量；
        否则仅使用前 eval_n_limit 个实例。
        过滤已完成实例：排除已经存在于输出文件中的实例。
        返回新数据集：仅包含尚未处理的实例，用于后续评估任务。
    """
    assert (
        'instance_id' in dataset.columns
    ), "Expected 'instance_id' column in the dataset. You should define your own unique identifier for each instance and use it as the 'instance_id' column."
    id_column = 'instance_id'
    logger.info(f'Writing evaluation output to {output_file}')
    finished_ids: set[str] = set()
    if os.path.exists(output_file):
        with open(output_file, 'r') as f:
            for line in f:
                data = json.loads(line)
                finished_ids.add(str(data[id_column]))
        logger.warning(
            f'\nOutput file {output_file} already exists. Loaded {len(finished_ids)} finished instances.'
        )

    if eval_ids:
        eval_ids_converted = [dataset[id_column].dtype.type(id) for id in eval_ids]
        dataset = dataset[dataset[id_column].isin(eval_ids_converted)]
        logger.info(f'Limiting evaluation to {len(eval_ids)} specific instances.')
    elif skip_num and skip_num >= 0:
        skip_num = min(skip_num, len(dataset))
        dataset = dataset.iloc[skip_num:]
        logger.info(
            f'Starting evaluation with skipping first {skip_num} instances ({len(dataset)} instances to run).'
        )
        if eval_n_limit and eval_n_limit > 0:
            dataset = dataset.head(eval_n_limit)
            logger.info(f'Limiting evaluation to {eval_n_limit} instances.')
    elif eval_n_limit and eval_n_limit > 0:
        dataset = dataset.head(eval_n_limit)
        logger.info(f'Limiting evaluation to first {eval_n_limit} instances.')

    new_dataset = [
        instance
        for _, instance in dataset.iterrows()
        if str(instance[id_column]) not in finished_ids
    ]
    logger.info(
        f'Finished instances: {len(finished_ids)}, Remaining instances: {len(new_dataset)}'
    )

    return pd.DataFrame(new_dataset)
