import json
import time
import traceback
from typing import Optional, Callable, Iterable, TextIO

import multiprocessing as mp
import pandas as pd
from tqdm import tqdm

from siada.foundation.logging import logger
from benchmark.swe.tools.eval_output import EvalOutput

def run_evaluation(
    dataset: pd.DataFrame,
    output_file: str,
    process_instance_func: Callable[
        [pd.Series], EvalOutput
    ],
    target_instance: Optional[str] = None,
    excluded_instance_ids: Optional[Iterable[str]] = None,
):


    total_instances = len(dataset)
    pbar = tqdm(total=total_instances, desc='Instances processed')
    output_fp = open(output_file, 'a')

    try:
        for _, instance in dataset.iterrows():
            if target_instance is not None and not instance['instance_id'].startswith(target_instance):
                continue
            if excluded_instance_ids is not None and instance['instance_id'] in excluded_instance_ids:
                continue
            try:
                result = process_instance_func(instance)
                update_progress(result, pbar, output_fp)
            except RuntimeError as e:
                msg = f'process instance fail, instance_id =  {instance.instance_id}'
                logger.error(msg)
    except KeyboardInterrupt:
        print('\nKeyboardInterrupt received. Cleaning up...\n')
        cleanup()

    output_fp.close()
    logger.info('\nEvaluation finished.\n')


def cleanup():
    print('Cleaning up child processes...')
    for process in mp.active_children():
        print(f'Terminating child process: {process.name}')
        process.terminate()
        process.join()


def update_progress(
    result: EvalOutput,
    pbar: tqdm,
    output_fp: TextIO,
):
    """Update the progress bar and write the result to the output file."""
    pbar.update(1)
    pbar.set_description(f'Infer completed , Instance {result.instance_id}')
    output_fp.write(json.dumps(result.model_dump()) + '\n')
    output_fp.flush()
