import json
from typing import Optional, Any, Union

from pydantic import BaseModel

from siada.swe.tools.metadata import EvalMetadata


class EvalOutput(BaseModel):
    # NOTE: User-specified
    instance_id: str
    # output of the evaluation
    # store anything that is needed for the score calculation
    test_result: dict[str, Any]

    instruction: Optional[str] = None

    # Interaction info
    metadata: Optional[EvalMetadata] = None
    # list[tuple[dict[str, Any], dict[str, Any]]] - for compatibility with the old format
    history: Union[
        list[dict[str, Any]],
        list[tuple[dict[str, Any], dict[str, Any]]],
        None
    ] = None
    metrics: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    # Optionally save the input test instance
    instance: Optional[dict[str, Any]] = None
    is_target_issue_passed: Optional[bool] = None
    is_original_issue_passed: Optional[bool] = None
    is_passed: Optional[bool] = None

    def model_dump(self, *args, **kwargs):
        dumped_dict = super().model_dump(*args, **kwargs)
        # Remove None values
        dumped_dict = {k: v for k, v in dumped_dict.items() if v is not None}
        # Apply custom serialization for metadata (to avoid leaking sensitive information)
        if self.metadata is not None:
            dumped_dict['metadata'] = self.metadata.model_dump()
        return dumped_dict

    def model_dump_json(self, *args, **kwargs):
        dumped = super().model_dump_json(*args, **kwargs)
        dumped_dict = json.loads(dumped)
        # Apply custom serialization for metadata (to avoid leaking sensitive information)
        if 'metadata' in dumped_dict:
            dumped_dict['metadata'] = json.loads(self.metadata.model_dump_json())
        return json.dumps(dumped_dict)