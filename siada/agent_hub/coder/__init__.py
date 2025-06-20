"""
Coder用户代理模块

包含所有与代码相关的Agent实现
"""


from .bug_fix_agent import BugFixAgent
from .code_gen_agent import CodeGenAgent
from .fe_gen_agent import FeGenAgent


__all__ = [
    'BugFixAgent',
    'CodeGenAgent',
    'FeGenAgent'

]

from .code_gen_agent import CodeGenAgent

