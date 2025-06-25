import os

from siada.foundation.logging import logger
from benchmark.swe.tools.dataset import load_huggingface_swe_bench_dataset, prepare_dataset
from benchmark.swe.eval_framework import run_evaluation
from benchmark.swe.tools.parser import get_parser
from benchmark.swe.run_instance import process_instance


def download_dataset():
    logger.info("Start ...")
    parser = get_parser()
    args, _ = parser.parse_known_args()
    # dataset_description = (
    #         args.dataset.replace('/', '__') + '-' + args.split.replace('/', '__')
    # )
    output_file = os.path.join(args.output_dir, 'output.jsonl')
    swe_bench_test_dataset = load_huggingface_swe_bench_dataset(args.dataset, args.split)
    instances = prepare_dataset(swe_bench_test_dataset.to_pandas(), output_file, 300)
    if len(instances) > 0 and not isinstance(
            instances['PASS_TO_PASS'][instances['PASS_TO_PASS'].index[0]], str
    ):
        for col in ['PASS_TO_PASS', 'FAIL_TO_PASS']:
            instances[col] = instances[col].apply(lambda x: str(x))

    return instances,  output_file, args.target_instance


if __name__ == '__main__':
    instances, output_file, target_instance = download_dataset()

    run_evaluation(
        instances, output_file, process_instance,
        target_instance = target_instance,
        excluded_instance_ids = None
    )
