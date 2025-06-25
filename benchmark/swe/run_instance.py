import asyncio
import os

import pandas as pd

from benchmark.swe.tools.git_util import apply_patch
from siada.foundation.logging import logger
from siada.services.siada_runner import SiadaRunner
from benchmark.swe.tools.conda_env import create_env, _get_swebench_workspace_dir_name
from benchmark.swe.tools.eval_output import EvalOutput
from siada.tools.coder.run_cmd import run_cmd_subprocess


def process_instance(
        instance: pd.Series,
) -> EvalOutput:

    logger.info("start to create conda env")
    create_env(instance)
    logger.info("complete to create conda env")

    try:

        instruction, absolute_workspace = get_instruction(instance)
        # Here's how you can run the agent (similar to the `main` function) and get the final task state
        asyncio.run(run_agent("bugfix", instruction, absolute_workspace))
        output: EvalOutput = run_test(absolute_workspace, instance)
        return output
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        raise e

def process_instance_test(instance: pd.Series) -> EvalOutput:
    """
    只执行测试用例
    """
    create_env(instance)
    try:

        instruction, absolute_workspace = get_instruction(instance)
        output: EvalOutput = run_test(absolute_workspace, instance)
        return output
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        raise e


def get_instruction(instance: pd.Series):
    absolute_workspace, parent_path, work_space = _get_swebench_workspace_dir_name(instance)
    instruction = (
        # '<uploaded_files>\n'
        # f'{parent_path}{work_space}\n'
        # '</uploaded_files>\n'
        f"I've uploaded a python code repository in the directory {work_space}. Consider the following PR description; Fix the issue:\n\n"
        f'<pr_description>\n'
        f'{instance.problem_statement}\n'
        '</pr_description>\n\n'
    )
    return instruction, absolute_workspace

async def run_agent(agent_class: str, instruction: str, workspace: str = None):
    await SiadaRunner.run_agent(agent_class, instruction, workspace)


def run_test(workspace: str, instance) -> EvalOutput:
    test_result = {}
    output = EvalOutput(
        instance_id=instance.instance_id,
        instance=instance.to_dict(),  # SWE Bench specific
        test_result=test_result,
    )
    apply_patch(workspace, instance.test_patch)
    test_results = eval_output(workspace, instance, output)
    print("test result is : ", test_results)
    return output



def eval_output(workspace, instance, output: EvalOutput):
    fail_to_pass_test_case = eval(instance['FAIL_TO_PASS'])  # Convert string representation to list
    pass_to_pass_test_case = eval(instance['PASS_TO_PASS'])  # Convert string representation to list

    env_name = instance.instance_id

    # fail_to_pass_test_case = grep_real_test_case(fail_to_pass_test_case, runtime, env_name, instance)
    # pass_to_pass_test_case = grep_real_test_case(pass_to_pass_test_case, runtime, env_name, instance)
    test_results = {
        'fail_cases': [],
        'pass_count': 0
    }

    # Run fail-to-pass tests
    fail_to_pass_result = process_test_cases(fail_to_pass_test_case, workspace, env_name, test_results)

    if not fail_to_pass_result:
        output.is_passed = False
        output.is_target_issue_passed = False
        output.is_original_issue_passed = None
        #return test_results

    # Run pass-to-pass tests
    pass_to_pass_result = process_test_cases(pass_to_pass_test_case, workspace, env_name, test_results)

    success = (test_results['pass_count'] == len(fail_to_pass_test_case) + len(pass_to_pass_test_case)
               and len(test_results['fail_cases']) == 0)

    output.is_passed = success
    output.is_target_issue_passed = fail_to_pass_result
    output.is_original_issue_passed = pass_to_pass_result
    return test_results


def process_test_cases(test_cases, workspace, env_name, test_results):
    is_passed = True
    for test_path in test_cases:
        result: dict = run_pytest(test_path, workspace, env_name)
        if result['success']:
            test_results['pass_count'] += 1
        else:
            test_results['fail_cases'].append(result['test_case'])
            is_passed = False
            #break
    return is_passed


def run_pytest(test_case, workspace, env_name):
    # Helper function to run a single test
    test_case = remove_unbalanced(test_case)
    test_case = workspace + '/' + test_case
    command = "PYTHONPATH=" + workspace + " " + f'conda run -n {env_name} pytest -v ' + '\'' + test_case + '\''

    return_code, output = run_cmd_subprocess(command)
    # Extract the test file path and test name
    # Parse test results
    success = return_code == 0
    return {
        'test_case': test_case,
        'success': success,
        'output': output
    }

def remove_unbalanced(test_case):
    left_c = test_case.count('[')
    right_c = test_case.count(']')
    if left_c != right_c:
        return test_case.split("[")[0]
    else:
        left_k = test_case.count('(')
        right_k = test_case.count(')')
        if left_k != right_k:
            return test_case.split("[")[0]
    return test_case
