import json
import time
import traceback
from typing import Optional, Callable, Iterable, TextIO

import multiprocessing as mp
import pandas as pd
from tqdm import tqdm

from siada.foundation.logging import logger
from benchmark.swe.tools.eval_output import EvalOutput
from benchmark.swe.tools.metadata import EvalMetadata


def run_evaluation(
    dataset: pd.DataFrame,
    metadata: Optional[EvalMetadata],
    output_file: str,
    num_workers: int,
    process_instance_func: Callable[
        [pd.Series, EvalMetadata, bool], EvalOutput
    ],
    max_retries: int = 3,  # number of retries for each instance
    target_instance: Optional[str] = None,
    excluded_instance_ids: Optional[Iterable[str]] = None,
):
    use_multiprocessing = num_workers > 1

    logger.info(
        f'Evaluation started with Agent {metadata.agent_class}:\n'
        f'max iterations {metadata.max_iterations}.\n'
    )

    total_instances = len(dataset)
    pbar = tqdm(total=total_instances, desc='Instances processed')
    output_fp = open(output_file, 'a')

    try:
        if use_multiprocessing:
            with mp.Pool(num_workers) as pool:
                args_iter = (
                    (process_instance_func, instance, metadata, True, max_retries)
                    for _, instance in dataset.iterrows()
                )
                results = pool.imap_unordered(_process_instance_wrapper_mp, args_iter)
                for result in results:
                    update_progress(result, pbar, output_fp)
        else:
            for _, instance in dataset.iterrows():
                if target_instance is not None and not instance['instance_id'].startswith(target_instance):
                    continue
                if excluded_instance_ids is not None and instance['instance_id'] in excluded_instance_ids:
                    continue
                try:
                    result = _process_instance_wrapper(
                        process_instance_func=process_instance_func,
                        instance=instance,
                        metadata=metadata,
                        use_mp=False,
                        max_retries=max_retries,
                    )
                    update_progress(result, pbar, output_fp)
                except RuntimeError as e:
                    msg = f'process instance fail, instance_id =  {instance.instance_id}'
                    logger.error(msg)
    except KeyboardInterrupt:
        print('\nKeyboardInterrupt received. Cleaning up...\n')
        cleanup()

    output_fp.close()
    logger.info('\nEvaluation finished.\n')


def _process_instance_wrapper_mp(args):
    """Wrapper for multiprocessing, especially for imap_unordered."""
    return _process_instance_wrapper(*args)


def _process_instance_wrapper(
    process_instance_func: Callable[[pd.Series, EvalMetadata], EvalOutput],
    instance: pd.Series,
    metadata: EvalMetadata,
    use_mp: bool,
    max_retries: int = 5,
) -> EvalOutput:
    """Wrap the process_instance_func to handle retries and errors.

    Retry an instance up to max_retries times if it fails (e.g., due to transient network/runtime issues).
    """
    for attempt in range(max_retries + 1):
        try:
            result = process_instance_func(instance, metadata)
            return result
        except Exception as e:
            error = str(e)
            stacktrace = traceback.format_exc()
            if attempt == max_retries:
                logger.error(e)
                raise RuntimeError(
                    f'Maximum error retries reached for instance {instance.instance_id}'
                ) from e
            msg = (
                '-' * 10
                + '\n'
                + f'Error in instance [{instance.instance_id}]: {error}. Stacktrace:\n{stacktrace}'
                + '\n'
                + '-' * 10
                + f'[The above error occurred. Retrying... (attempt {attempt + 1} of {max_retries})]'
                + '-' * 10
                + '\n'
            )
            logger.error(msg)
            if use_mp:
                print(msg)  # use print to directly print to console
            time.sleep(5)


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
