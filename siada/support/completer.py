from prompt_toolkit.completion import Completer, Completion
import os

from siada.services.file_recommendation import FileRecommendationEngine, CompletionConfig


class CommandCompletionException(Exception):
    """Raised when a command should use the normal autocompleter instead of
    command-specific completion."""
    pass



class AutoCompleter(Completer):
    def __init__(
        self, root, commands, encoding
    ):
        self.encoding = encoding
        self.root = root

        self.words = set()

        self.commands = commands
        self.command_completions = dict()
        if commands:
            self.command_names = self.commands.get_commands()
        
        # Initialize file recommendation engine
        current_dir = root if root else os.getcwd()
        config = CompletionConfig(
            max_results=20,
            enable_recursive_search=True,
            max_search_depth=5,
            respect_git_ignore=True
        )
        self.file_recommendation_engine = FileRecommendationEngine(
            current_directory=current_dir,
            config=config
        )

    def get_command_completions(self, document, complete_event, text, words):
        if len(words) == 1 and not text[-1].isspace():
            partial = words[0].lower()
            candidates = [cmd for cmd in self.command_names if cmd.startswith(partial)]
            for candidate in sorted(candidates):
                yield Completion(candidate, start_position=-len(words[-1]))
            return

        if len(words) <= 1 or text[-1].isspace():
            return

        cmd = words[0]
        partial = words[-1].lower()

        matches, _, _ = self.commands.matching_commands(cmd)
        if len(matches) == 1:
            cmd = matches[0]
        elif cmd not in matches:
            return

        raw_completer = self.commands.get_raw_completions(cmd)
        if raw_completer:
            yield from raw_completer(document, complete_event)
            return

        if cmd not in self.command_completions:
            candidates = self.commands.get_completions(cmd)
            self.command_completions[cmd] = candidates
        else:
            candidates = self.command_completions[cmd]

        if candidates is None:
            return

        candidates = [word for word in candidates if partial in word.lower()]
        for candidate in sorted(candidates):
            yield Completion(candidate, start_position=-len(words[-1]))

    def get_completions(self, document, complete_event):

        text = document.text_before_cursor
        words = text.split()
        if not words:
            return

        if text and text[-1].isspace():
            # don't keep completing after a space
            return

        if text[0] == "/":
            try:
                yield from self.get_command_completions(document, complete_event, text, words)
                return
            except CommandCompletionException:
                # Fall through to normal completion
                pass

        elif text[0] == "@":
            try:
                if self.file_recommendation_engine.should_show_suggestions(text):
                    suggestions = self.file_recommendation_engine.get_suggestions_sync(text)
                    
                    # Calculate start_position to replace from @ symbol
                    start_position = -len(text)
                    
                    for suggestion in suggestions:
                        yield Completion(
                            "@" + suggestion['value'], 
                            start_position=start_position,
                            display=suggestion['label']
                        )
                else:
                    if text == "@":
                        suggestions = self.file_recommendation_engine.get_suggestions_sync("@")
                        for suggestion in suggestions:
                            yield Completion(
                                "@" + suggestion['value'],
                                start_position=-1,  # Replace the @ symbol
                                display=suggestion['label']
                            )
            except Exception as e:
                pass


        candidates = self.words
        candidates = [word if type(word) is tuple else (word, word) for word in candidates]

        last_word = words[-1]
