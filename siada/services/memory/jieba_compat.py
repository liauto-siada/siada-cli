"""Import jieba while containing warnings from its legacy pkg_resources import."""

import warnings

# jieba._compat imports pkg_resources, which warns while registering Google's
# old namespace packages. The dependency is needed for Chinese tokenization;
# silence only these import-time warnings until jieba drops pkg_resources.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r"Deprecated call to `pkg_resources\.declare_namespace\('google(?:\.cloud)?'\)`\.",
        category=DeprecationWarning,
        module=r"pkg_resources",
    )
    warnings.filterwarnings(
        "ignore", message="pkg_resources is deprecated", category=UserWarning,
    )
    warnings.filterwarnings("ignore", category=SyntaxWarning, module="jieba")
    import jieba


def import_posseg():
    """Load the POS tagger only for entity extraction, as before."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning, module="jieba")
        import jieba.posseg as pseg
    return pseg
