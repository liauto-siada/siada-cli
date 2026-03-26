from siada.tools.coder.file_search import RipgrepSearcher
from siada.tools.coder.file_search.search import SEARCH_DOCS


def regex_search_files(
    cwd: str,
    directory_path: str,
    regex: str,
    file_pattern: str = "*"
) -> str:

    searcher = RipgrepSearcher()
    search_result = searcher.search_in_files(directory_path, regex, file_pattern, cwd)

    return search_result.content

regex_search_files.__doc__ = SEARCH_DOCS