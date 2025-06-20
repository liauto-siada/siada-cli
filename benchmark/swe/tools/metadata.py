import json
import os
import pathlib
import time
from typing import Optional, Any

from pydantic import BaseModel

from siada.foundation.logging import logger


class EvalMetadata(BaseModel):
    agent_class: str
    # llm_config: LLMConfig
    max_iterations: int
    eval_output_dir: str
    start_time: str
    git_commit: str
    dataset: Optional[str] = None
    data_split: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    search_relevant_files: Optional[bool] = True
    llm_model: Optional[str] = None

    def model_dump(self, *args, **kwargs):
        dumped_dict = super().model_dump(*args, **kwargs)
        # avoid leaking sensitive information
        # dumped_dict['llm_config'] = self.llm_config.to_safe_dict()
        return dumped_dict

    def model_dump_json(self, *args, **kwargs):
        dumped = super().model_dump_json(*args, **kwargs)
        dumped_dict = json.loads(dumped)
        # avoid leaking sensitive information
        # dumped_dict['llm_config'] = self.llm_config.to_safe_dict()
        # logger.debug(f'Dumped metadata: {dumped_dict}')
        return json.dumps(dumped_dict)


def make_metadata(
        # llm_config: LLMConfig,
        dataset_name: str,
        agent_class: str,
        max_iterations: int,
        eval_note: Optional[str],
        eval_output_dir: str,
        data_split: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        search_relevant_files: Optional[bool] = True,
        llm_model: Optional[str] = None,
) -> EvalMetadata:
    # model_name = llm_config.model.split('/')[-1]
    # model_path = model_name.replace(':', '_').replace('@', '-')
    eval_note = f'_N_{eval_note}' if eval_note else ''

    eval_output_path = os.path.join(
        eval_output_dir,
        dataset_name,
        agent_class,
        f'max_iteration_{max_iterations}{eval_note}',
    )

    pathlib.Path(eval_output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(os.path.join(eval_output_path, 'logs')).mkdir(
        parents=True, exist_ok=True
    )
    logger.info(f'Using evaluation output directory: {eval_output_path}')

    metadata = EvalMetadata(
        agent_class=agent_class,
        # llm_config=llm_config,
        max_iterations=max_iterations,
        eval_output_dir=eval_output_path,
        start_time=time.strftime('%Y-%m-%d %H:%M:%S'),
        git_commit='yzj',
        dataset=dataset_name,
        data_split=data_split,
        details=details,
        search_relevant_files=search_relevant_files,
        llm_model=llm_model,
    )
    metadata_json = metadata.model_dump_json()
    logger.info(f'Metadata: {metadata_json}')
    with open(os.path.join(eval_output_path, 'metadata.json'), 'w') as f:
        f.write(metadata_json)

    return metadata
