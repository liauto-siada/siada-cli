import asyncio
import os

import pandas as pd

from siada.foundation.logging import logger
from siada.services.siada_runner import SiadaRunner
from benchmark.swe.tools.conda_env import create_env, _get_swebench_workspace_dir_name
from benchmark.swe.tools.eval_output import EvalOutput
from benchmark.swe.tools.logger import reset_logger_for_multiprocessing
from benchmark.swe.tools.metadata import EvalMetadata
from benchmark.swe.tools.run_instance_config.agent_config import AgentConfig
from benchmark.swe.tools.run_instance_config.app_config import AppConfig
from benchmark.swe.tools.run_instance_config.sandbox_config import SandboxConfig

SWE_BENCH_CONTAINER_IMAGE = 'ghcr.io/opendevin/eval-swe-bench:full-v1.2.1'

def process_instance(
        instance: pd.Series,
        metadata: EvalMetadata,
) -> EvalOutput:

    # 日志调整
    logger.info("start to adjust log")
    log_dir = os.path.join(metadata.eval_output_dir, 'infer_logs')
    reset_logger_for_multiprocessing(logger, instance.instance_id, log_dir)
    logger.info("complete to adjust log")

    logger.info("start to create conda env")
    create_env(instance, metadata.details)
    logger.info("complete to create conda env")

    try:

        instruction = get_instruction(instance)

        # Here's how you can run the agent (similar to the `main` function) and get the final task state
        output = asyncio.run(
            run_controller_wrapper(
                instruction=instruction,
                agent_class=metadata.agent_class,
                instance=instance
            )
        )
        return output
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        raise e


def get_config(
        instance: pd.Series,
        metadata: EvalMetadata,
) -> AppConfig:
    base_container_image = SWE_BENCH_CONTAINER_IMAGE
    logger.info(f'Using swe-bench container image: {base_container_image}')
    workspace = os.getcwd()

    config = AppConfig(
        default_agent=metadata.agent_class,
        run_as_openhands=False,
        max_iterations=metadata.max_iterations,
        runtime=os.environ.get('RUNTIME', 'eventstream_local'),
        sandbox=SandboxConfig(
            base_container_image=base_container_image,
            enable_auto_lint=True,
            use_host_network=False,
            # large enough timeout, since some testcases take very long to run
            # 调整Action超时时间为60秒
            timeout=120,
            # Add platform to the sandbox config to solve issue 4401
            platform='linux/amd64',
            api_key=os.environ.get('ALLHANDS_API_KEY', None),
            remote_runtime_api_url=os.environ.get('SANDBOX_REMOTE_RUNTIME_API_URL'),
            keep_remote_runtime_alive=False,
        ),
        # 默认为当前目录
        workspace_base=workspace,
        workspace_mount_path=None,
    )
    # config.set_llm_config(
    #     update_llm_config_for_completions_logging(
    #         metadata.llm_config, metadata.eval_output_dir, instance['instance_id']
    #     )
    # )
    agent_config = AgentConfig(
        codeact_enable_jupyter=False,
        codeact_enable_browsing=False,
        codeact_enable_llm_editor=False,
        llm_model=metadata.llm_model,
    )
    config.set_agent_config(agent_config)
    return config


# TODO: Input 设计
def get_instruction(instance: pd.Series):
    workspace_dir_name, parent_path, work_space = _get_swebench_workspace_dir_name(instance)
    instruction = (
        '<uploaded_files>\n'
        f'{parent_path}{work_space}\n'
        '</uploaded_files>\n'
        f"I've uploaded a python code repository in the directory {work_space}. Consider the following PR description; you must give it the utmost attention possible:\n\n"
        f'<pr_description>\n'
        f'{instance.problem_statement}\n'
        '</pr_description>\n\n'
    )
    return instruction


async def run_controller_wrapper(agent_class, instruction, instance, **kwargs) -> EvalOutput:
    await run_agent(agent_class, instruction)
    # If you are working on some simpler benchmark that only evaluates the final model output (e.g., in a MessageAction)
    # You can simply get the LAST `MessageAction` from the returned `state.history` and parse it for evaluation.

    if kwargs['details']['create_env'] == 'true':
        output: EvalOutput = await run_test()
        await eval_output(instance, output)
        return output
    else:
        return EvalOutput(instance_id=instance['instance_id'], test_result={})


async def run_agent(agent_class: str, instruction: str):
    await SiadaRunner.run_agent(agent_class, instruction)


# TODO: 测试 设计
async def run_test() -> EvalOutput:
    ...


# TODO: 评估 设计
async def eval_output(instance, output):
    ...
