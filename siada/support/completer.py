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
        
        # Add completion state management
        self.completion_state = {
            'just_completed': False,
            'last_completion_pos': 0,
            'last_at_command': None,
            'last_completion_text': None
        }

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

        # Check for @ symbol anywhere in the text before cursor
        text_before_cursor = document.text_before_cursor
        at_pos = text_before_cursor.rfind("@")
        
        if at_pos != -1:
            try:
                # Extract query text from @ symbol to cursor
                query_text = text_before_cursor[at_pos:]
                current_pos = len(text_before_cursor)
                
                # Check if user just completed a selection and cursor is at end
                if (self.completion_state['just_completed'] and 
                    current_pos == self.completion_state['last_completion_pos'] and
                    query_text == self.completion_state['last_at_command']):
                    # Reset state and don't show suggestions immediately after completion
                    self.completion_state['just_completed'] = False
                    return
                
                # Reset completion state if user moved cursor or changed text
                if (current_pos != self.completion_state['last_completion_pos'] or
                    query_text != self.completion_state['last_at_command']):
                    self.completion_state['just_completed'] = False
                
                if self.file_recommendation_engine.should_show_suggestions(query_text):
                    suggestions = self.file_recommendation_engine.get_suggestions_sync(query_text)
                    
                    # Calculate start_position to replace from @ symbol
                    start_position = at_pos - len(text_before_cursor)
                    
                    for suggestion in suggestions:
                        # Create completion that will trigger state update when selected
                        # Auto-add space after completion to indicate completion end
                        completion_text = "@" + suggestion['value'] + " "
                        completion = Completion(
                            completion_text, 
                            start_position=start_position,
                            display=suggestion['label']
                        )
                        
                        # Store state for after completion (include space in position calculation)
                        self._prepare_completion_state(
                            completion_text,
                            at_pos + len(completion_text)
                        )
                        
                        yield completion
                else:
                    if query_text == "@":
                        suggestions = self.file_recommendation_engine.get_suggestions_sync("@")
                        for suggestion in suggestions:
                            # Auto-add space after completion to indicate completion end
                            completion_text = "@" + suggestion['value'] + " "
                            completion = Completion(
                                completion_text,
                                start_position=at_pos - len(text_before_cursor),  # Replace from @ symbol
                                display=suggestion['label']
                            )
                            
                            # Store state for after completion (include space in position calculation)
                            self._prepare_completion_state(
                                completion_text,
                                at_pos + len(completion_text)
                            )
                            
                            yield completion
            except Exception as e:
                pass


        candidates = self.words
        candidates = [word if type(word) is tuple else (word, word) for word in candidates]

        last_word = words[-1]
    
    def _prepare_completion_state(self, completion_text: str, completion_pos: int):
        """
        Prepare completion state for tracking when user selects a completion
        
        Args:
            completion_text: The text that will be inserted
            completion_pos: The cursor position after completion
        """
        self.completion_state.update({
            'just_completed': True,
            'last_completion_pos': completion_pos,
            'last_at_command': completion_text,
            'last_completion_text': completion_text
        })
    
    def reset_completion_state(self):
        """
        Reset completion state
        """
        self.completion_state.update({
            'just_completed': False,
            'last_completion_pos': 0,
            'last_at_command': None,
            'last_completion_text': None
        })
