import argparse

from agents.models.openai_provider import DEFAULT_MODEL

from benchmark.swe.tools.config import SWE_DEFAULT_AGENT, SWE_MAX_AGENT_ITERATION


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run an agent with a specific task')
    parser.add_argument(
        '--dataset',
        type=str,
        default='princeton-nlp/SWE-bench',
        help='data set to evaluate on, either full-test or lite-test',
    )
    parser.add_argument(
        '--split',
        type=str,
        default='test',
        help='split to evaluate on',
    )
    parser.add_argument(
        '--target_instance',
        type=str,
        default=None,
        help='Specify the target instance, e.g., "astropy".',
        required = True
    )
    parser.add_argument(
        '--max-iterations',
        default=SWE_MAX_AGENT_ITERATION,
        type=int,
        help='The maximum number of iterations to run the agent',
    )
    parser.add_argument(
        '--agent-cls',
        default=SWE_DEFAULT_AGENT,
        type=str,
        help='Name of the default agent to use',
    )
    parser.add_argument(
        '--eval-num-workers',
        default=4,
        type=int,
        help='The number of workers to use for evaluation',
    )
    parser.add_argument(
        '--llm_model',
        type=str,
        default=DEFAULT_MODEL,
        help='Specify the LLM model to use for the agent.',
    )
    parser.add_argument(
        '--username',
        default='default',
        type=str,
        help='User who runs the agent',
    )
    parser.add_argument(
        '--create_env',
        default='true',
        type=str,
        help='是否创建虚拟环境',
    )
    parser.add_argument(
        '--output_dir',
        default="Users/youzijun/siada/siada-agenthub",
        type=str,
        help='输出地址'
    )
    return parser

