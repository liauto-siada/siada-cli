import os

from benchmark.swe.tools.config import PROXY_FOR_HUGGINGFACE


def set_huggingface_gateway():
    os.environ["HTTP_PROXY"] = PROXY_FOR_HUGGINGFACE
    os.environ["HTTPS_PROXY"] = PROXY_FOR_HUGGINGFACE

def unset_huggingface_gateway():
    del os.environ["HTTP_PROXY"]
    del os.environ["HTTPS_PROXY"]