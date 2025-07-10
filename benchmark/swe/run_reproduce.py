from benchmark.swe.eval_framework import run_evaluation
from benchmark.swe.run_infer import download_dataset
from benchmark.swe.run_instance import process_instance_test, process_instance_reproduce

if __name__ == '__main__':
    instances, output_file, target_instance = download_dataset()

    run_evaluation(
        instances, output_file, process_instance_reproduce,
        target_instance = target_instance,
        excluded_instance_ids = None
    )