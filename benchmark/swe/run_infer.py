import os

from siada.foundation.logging import logger
from benchmark.swe.tools.dataset import load_huggingface_swe_bench_dataset, filter_dataset, prepare_dataset
from benchmark.swe.tools.eval_framework import run_evaluation
from benchmark.swe.tools.metadata import make_metadata
from benchmark.swe.tools.parser import get_parser
from benchmark.swe.tools.run_instance import process_instance

if __name__ == '__main__':
    logger.info("Start ...")
    parser = get_parser()
    args, _ = parser.parse_known_args()

    # TODO: Agent 需要先在 AgentMap 中定义好，才能获取到
    _agent_cls = args.agent_cls

    dataset_description = (
            args.dataset.replace('/', '__') + '-' + args.split.replace('/', '__')
    )

    # Metadata 负责核心数据在整个流程中的读取和更新。
    metadata = make_metadata(
        # llm_config,
        dataset_description,
        "bugfix",
        args.max_iterations,
        None,
        args.output_dir,
        details={"create_env": args.create_env},
        search_relevant_files=False,
        llm_model=args.llm_model,
    )

    # 数据集处理 dataset: Dataset -> instances: DataFrame
    output_file = os.path.join(metadata.eval_output_dir, 'output.jsonl')
    swe_bench_test_dataset = load_huggingface_swe_bench_dataset(args.dataset, args.split)
    swe_bench_test_dataset = filter_dataset(swe_bench_test_dataset.to_pandas(), 'instance_id')
    instances = prepare_dataset(swe_bench_test_dataset, output_file, 300)
    if len(instances) > 0 and not isinstance(
            instances['PASS_TO_PASS'][instances['PASS_TO_PASS'].index[0]], str
    ):
        for col in ['PASS_TO_PASS', 'FAIL_TO_PASS']:
            instances[col] = instances[col].apply(lambda x: str(x))

    run_evaluation(
        instances, metadata, output_file, args.eval_num_workers, process_instance,
        target_instance=args.target_instance,
        excluded_instance_ids=None
    )
