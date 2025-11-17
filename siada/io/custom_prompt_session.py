"""
自定义 PromptSession，只在输入区域添加边框
"""
from functools import partial
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.shortcuts.prompt import CompleteStyle
from prompt_toolkit.layout import Layout, HSplit, Window, Float, FloatContainer
from prompt_toolkit.layout.containers import ConditionalContainer, WindowAlign, WritePosition
from prompt_toolkit.layout.controls import (
    BufferControl,
    FormattedTextControl,
    SearchBufferControl,
)
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu, MultiColumnCompletionsMenu
from prompt_toolkit.layout.processors import (
    AfterInput,
    AppendAutoSuggestion,
    ConditionalProcessor,
    DisplayMultipleCursors,
    DynamicProcessor,
    HighlightIncrementalSearchProcessor,
    HighlightSelectionProcessor,
    PasswordProcessor,
    ReverseSearchProcessor,
    merge_processors,
)
from prompt_toolkit.widgets import Frame, Box, Label
from prompt_toolkit.widgets.base import Border
from prompt_toolkit.widgets.toolbars import (
    SearchToolbar,
    SystemToolbar,
    ValidationToolbar,
)
from prompt_toolkit.filters import (
    Condition,
    has_arg,
    has_focus,
    is_done,
    renderer_height_is_known,
)
from prompt_toolkit.enums import DEFAULT_BUFFER
from prompt_toolkit.application.current import get_app
from prompt_toolkit.lexers import DynamicLexer
from prompt_toolkit.formatted_text import fragment_list_to_text
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.layout.screen import Screen, Point
from prompt_toolkit.layout.mouse_handlers import MouseHandlers


def _split_multiline_prompt(get_prompt_text):
    """
    从原始 prompt.py 复制的辅助函数
    """
    from prompt_toolkit.layout.utils import explode_text_fragments
    
    def has_before_fragments():
        for fragment, char, *_ in get_prompt_text():
            if "\n" in char:
                return True
        return False

    def before():
        result = []
        found_nl = False
        for fragment, char, *_ in reversed(explode_text_fragments(get_prompt_text())):
            if found_nl:
                result.insert(0, (fragment, char))
            elif char == "\n":
                found_nl = True
        return result

    def first_input_line():
        result = []
        for fragment, char, *_ in reversed(explode_text_fragments(get_prompt_text())):
            if char == "\n":
                break
            else:
                result.insert(0, (fragment, char))
        return result

    return has_before_fragments, before, first_input_line


class _RPrompt(Window):
    """右侧提示符"""
    def __init__(self, text):
        super().__init__(
            FormattedTextControl(text=text),
            align=WindowAlign.RIGHT,
            style="class:rprompt",
        )


class CustomFloatContainer(FloatContainer):
    """
    自定义 FloatContainer，确保浮动层（如补全菜单）的最小高度
    """
    
    def __init__(self, content, floats, min_float_height=3, **kwargs):
        """
        :param min_float_height: 浮动层的最小高度（行数）
        """
        self.min_float_height = min_float_height
        super().__init__(content, floats, **kwargs)
    
    def _draw_float(
        self,
        fl: Float,
        screen: Screen,
        mouse_handlers: MouseHandlers,
        write_position: WritePosition,
        style: str,
        erase_bg: bool,
        z_index: int | None,
    ) -> None:
        """
        重写 _draw_float 方法，确保浮动层的最小高度
        """
        from prompt_toolkit.application.current import get_app
        
        # 获取光标位置
        cpos = screen.get_menu_position(
            fl.attach_to_window or get_app().layout.current_window
        )
        cursor_position = Point(
            x=cpos.x - write_position.xpos, y=cpos.y - write_position.ypos
        )

        fl_width = fl.get_width()
        fl_height = fl.get_height()
        width: int
        height: int
        xpos: int
        ypos: int

        # ===== 计算水平位置（与原实现相同）=====
        if fl.left is not None and fl_width is not None:
            xpos = fl.left
            width = fl_width
        elif fl.left is not None and fl.right is not None:
            xpos = fl.left
            width = write_position.width - fl.left - fl.right
        elif fl_width is not None and fl.right is not None:
            xpos = write_position.width - fl.right - fl_width
            width = fl_width
        elif fl.xcursor:
            if fl_width is None:
                width = fl.content.preferred_width(write_position.width).preferred
                width = min(write_position.width, width)
            else:
                width = fl_width

            xpos = cursor_position.x
            if xpos + width > write_position.width:
                xpos = max(0, write_position.width - width)
        elif fl_width:
            xpos = int((write_position.width - fl_width) / 2)
            width = fl_width
        else:
            width = fl.content.preferred_width(write_position.width).preferred

            if fl.left is not None:
                xpos = fl.left
            elif fl.right is not None:
                xpos = max(0, write_position.width - width - fl.right)
            else:
                xpos = max(0, int((write_position.width - width) / 2))

            width = min(width, write_position.width - xpos)

        # ===== 计算垂直位置（添加最小高度逻辑）=====
        if fl.top is not None and fl_height is not None:
            ypos = fl.top
            height = fl_height
        elif fl.top is not None and fl.bottom is not None:
            ypos = fl.top
            height = write_position.height - fl.top - fl.bottom
        elif fl_height is not None and fl.bottom is not None:
            ypos = write_position.height - fl_height - fl.bottom
            height = fl_height
        elif fl.ycursor:
            ypos = cursor_position.y + (0 if fl.allow_cover_cursor else 1)

            if fl_height is None:
                height = fl.content.preferred_height(
                    width, write_position.height
                ).preferred
            else:
                height = fl_height

            # ⭐ 关键修改：确保最小高度
            height = max(height, self.min_float_height)

            # 智能调整位置：如果下方空间不足
            if height > write_position.height - ypos:
                if write_position.height - ypos + 1 >= ypos:
                    # 下方空间更多：缩小高度适应下方（但不小于最小高度）
                    height = max(write_position.height - ypos, self.min_float_height)
                else:
                    # 上方空间更多：显示在光标上方
                    height = min(height, cursor_position.y)
                    # 如果上方空间也不足以显示最小高度，尽可能使用可用空间
                    if height < self.min_float_height:
                        height = min(self.min_float_height, cursor_position.y)
                    ypos = cursor_position.y - height
        elif fl_height:
            ypos = int((write_position.height - fl_height) / 2)
            height = fl_height
        else:
            height = fl.content.preferred_height(width, write_position.height).preferred

            if fl.top is not None:
                ypos = fl.top
            elif fl.bottom is not None:
                ypos = max(0, write_position.height - height - fl.bottom)
            else:
                ypos = max(0, int((write_position.height - height) / 2))

            height = min(height, write_position.height - ypos)

        # ===== 绘制浮动层 =====
        if height > 0 and width > 0:
            wp = WritePosition(
                xpos=xpos + write_position.xpos,
                ypos=ypos + write_position.ypos,
                width=width,
                height=height,
            )

            if not fl.hide_when_covering_content or self._area_is_empty(screen, wp):
                fl.content.write_to_screen(
                    screen,
                    mouse_handlers,
                    wp,
                    style,
                    erase_bg=not fl.transparent(),
                    z_index=z_index,
                )


class CustomCompletionsMenu(CompletionsMenu):
    """自定义补全菜单,支持最小高度"""
    
    def __init__(self, min_height=4, **kwargs):
        self._min_height = min_height
        self._patched = False
        super().__init__(**kwargs)
    
    def __pt_container__(self):
        """返回容器,并在首次调用时修改高度"""
        container = super().__pt_container__()
        
        # 只修改一次
        if not self._patched:
            self._patched = True
            # CompletionsMenu 的 container 是一个 ConditionalContainer
            # 其 content 是一个 Window
            if hasattr(container, 'content') and hasattr(container.content, 'height'):
                # 保存原始高度函数
                original_height = container.content.height
                min_h = self._min_height
                
                # 创建新的高度函数
                def new_height():
                    if callable(original_height):
                        h = original_height()
                        if isinstance(h, Dimension):
                            return Dimension(
                                min=max(h.min or 0, min_h),
                                max=h.max,
                                preferred=max(h.preferred or 0, min_h)
                            )
                        elif isinstance(h, int):
                            return Dimension(min=min_h, max=h, preferred=max(h, min_h))
                        return Dimension(min=min_h, preferred=min_h)
                    elif isinstance(original_height, Dimension):
                        return Dimension(
                            min=max(original_height.min or 0, min_h),
                            max=original_height.max,
                            preferred=max(original_height.preferred or 0, min_h)
                        )
                    elif isinstance(original_height, int):
                        return Dimension(min=min_h, max=original_height, preferred=max(original_height, min_h))
                    return Dimension(min=min_h, preferred=min_h)
                
                container.content.height = new_height
        
        return container


class RoundedBorder(Border):
    """圆角边框"""
    TOP_LEFT = "╭"
    TOP_RIGHT = "╮"
    BOTTOM_LEFT = "╰"
    BOTTOM_RIGHT = "╯"
    VERTICAL = "│"
    HORIZONTAL = "─"


class RoundedFrame:
    """
    带圆角边框的 Frame
    
    这是 Frame 类的修改版本，使用圆角边框字符
    """
    def __init__(
        self,
        body,
        title: str = "",
        style: str = "",
        width=None,
        height=None,
        key_bindings=None,
        modal: bool = False,
    ):
        from prompt_toolkit.layout.containers import (
            VSplit, HSplit, Window, ConditionalContainer, DynamicContainer
        )
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.filters import Condition
        from prompt_toolkit.formatted_text import Template
        from functools import partial
        
        self.title = title
        self.body = body

        fill = partial(Window, style="class:frame.border")
        style = "class:frame " + style

        top_row_with_title = VSplit(
            [
                fill(width=1, height=1, char=RoundedBorder.TOP_LEFT),
                fill(char=RoundedBorder.HORIZONTAL),
                fill(width=1, height=1, char="|"),
                Label(
                    lambda: Template(" {} ").format(self.title),
                    style="class:frame.label",
                    dont_extend_width=True,
                ),
                fill(width=1, height=1, char="|"),
                fill(char=RoundedBorder.HORIZONTAL),
                fill(width=1, height=1, char=RoundedBorder.TOP_RIGHT),
            ],
            height=1,
        )

        top_row_without_title = VSplit(
            [
                fill(width=1, height=1, char=RoundedBorder.TOP_LEFT),
                fill(char=RoundedBorder.HORIZONTAL),
                fill(width=1, height=1, char=RoundedBorder.TOP_RIGHT),
            ],
            height=1,
        )

        @Condition
        def has_title() -> bool:
            return bool(self.title)

        self.container = HSplit(
            [
                ConditionalContainer(
                    content=top_row_with_title,
                    filter=has_title,
                    alternative_content=top_row_without_title,
                ),
                VSplit(
                    [
                        fill(width=1, char=RoundedBorder.VERTICAL),
                        DynamicContainer(lambda: self.body),
                        fill(width=1, char=RoundedBorder.VERTICAL),
                    ],
                    padding=0,
                ),
                VSplit(
                    [
                        fill(width=1, height=1, char=RoundedBorder.BOTTOM_LEFT),
                        fill(char=RoundedBorder.HORIZONTAL),
                        fill(width=1, height=1, char=RoundedBorder.BOTTOM_RIGHT),
                    ],
                    height=1,
                ),
            ],
            width=width,
            height=height,
            style=style,
            key_bindings=key_bindings,
            modal=modal,
        )

    def __pt_container__(self):
        return self.container


class CustomPromptSession(PromptSession):
    """
    自定义 PromptSession，只在输入区域添加边框
    
    使用方法：
        session = CustomPromptSession(message='> ')
        result = session.prompt()
    """
    
    def _get_default_buffer_control_height(self) -> Dimension:
        buff = self.default_buffer
        text = buff.text
        if '\n' not in text and len(text) <= 10:
            return Dimension(min=1, max=1, preferred=1)
        return Dimension()

    def _create_layout(self) -> Layout:

        dyncond = self._dyncond
        (
            has_before_fragments,
            get_prompt_text_1,
            get_prompt_text_2,
        ) = _split_multiline_prompt(self._get_prompt)

        default_buffer = self.default_buffer
        search_buffer = self.search_buffer

        @Condition
        def display_placeholder():
            return self.placeholder is not None and self.default_buffer.text == ""

        all_input_processors = [
            HighlightIncrementalSearchProcessor(),
            HighlightSelectionProcessor(),
            ConditionalProcessor(
                AppendAutoSuggestion(), has_focus(default_buffer) & ~is_done
            ),
            ConditionalProcessor(PasswordProcessor(), dyncond("is_password")),
            DisplayMultipleCursors(),
            DynamicProcessor(lambda: merge_processors(self.input_processors or [])),
            ConditionalProcessor(
                AfterInput(lambda: self.placeholder),
                filter=display_placeholder,
            ),
        ]

        bottom_toolbar = ConditionalContainer(
            Window(
                FormattedTextControl(
                    lambda: self.bottom_toolbar, style="class:bottom-toolbar.text"
                ),
                style="class:bottom-toolbar",
                dont_extend_height=True,
                height=Dimension(min=1),
            ),
            filter=Condition(lambda: self.bottom_toolbar is not None)
            & ~is_done
            & renderer_height_is_known,
        )

        search_toolbar = SearchToolbar(
            search_buffer, ignore_case=dyncond("search_ignore_case")
        )

        search_buffer_control = SearchBufferControl(
            buffer=search_buffer,
            input_processors=[ReverseSearchProcessor()],
            ignore_case=dyncond("search_ignore_case"),
        )

        system_toolbar = SystemToolbar(
            enable_global_bindings=dyncond("enable_system_prompt")
        )

        def get_search_buffer_control():
            from prompt_toolkit.filters import is_true
            if is_true(self.multiline):
                return search_toolbar.control
            else:
                return search_buffer_control

        default_buffer_control = BufferControl(
            buffer=default_buffer,
            search_buffer_control=get_search_buffer_control,
            input_processors=all_input_processors,
            include_default_input_processors=False,
            lexer=DynamicLexer(lambda: self.lexer),
            preview_search=True,
        )

        default_buffer_window = Window(
            default_buffer_control,
            height=self._get_default_buffer_control_height,
            get_line_prefix=partial(
                self._get_line_prefix, get_prompt_text_2=get_prompt_text_2
            ),
            dont_extend_height=True,
            wrap_lines=dyncond("wrap_lines"),
        )

        @Condition
        def multi_column_complete_style():
            from prompt_toolkit.shortcuts.prompt import CompleteStyle
            return self.complete_style == CompleteStyle.MULTI_COLUMN

        # ===== 关键修改：只在输入窗口周围添加圆角边框 =====
        # 将 default_buffer_window 包装在圆角 Frame 中
        framed_input_window = ConditionalContainer(
            RoundedFrame(
                ConditionalContainer(
                    default_buffer_window,
                    Condition(
                        lambda: get_app().layout.current_control
                        != search_buffer_control
                    ),
                ),
                style=""
            ),
            filter=dyncond("show_frame") & ~ is_done,
            # 当不显示边框时，显示原始的输入窗口
            alternative_content=ConditionalContainer(
                default_buffer_window,
                Condition(
                    lambda: get_app().layout.current_control
                    != search_buffer_control
                ),
            ),
        )

        # 创建主输入容器（带浮动补全菜单）
        # 使用自定义 FloatContainer 确保补全菜单最小高度为 4 行
        main_input_container = CustomFloatContainer(
            content=HSplit(
                [
                    # 多行提示符的前几行
                    ConditionalContainer(
                        Window(
                            FormattedTextControl(get_prompt_text_1),
                            dont_extend_height=True,
                        ),
                        Condition(has_before_fragments),
                    ),
                    # 带边框的输入窗口
                    framed_input_window,
                    # 搜索缓冲区窗口
                    ConditionalContainer(
                        Window(search_buffer_control),
                        Condition(
                            lambda: get_app().layout.current_control
                            == search_buffer_control
                        ),
                    ),
                ]
            ),
            floats=[
                # 补全菜单（浮动层）- 最小高度4行
                Float(
                    xcursor=True,
                    ycursor=True,
                    transparent=True,
                    content=CustomCompletionsMenu(
                        min_height=4,
                        max_height=16,
                        scroll_offset=1,
                        extra_filter=has_focus(default_buffer)
                        & ~multi_column_complete_style,
                    ),
                ),
                Float(
                    xcursor=True,
                    ycursor=True,
                    transparent=True,
                    content=MultiColumnCompletionsMenu(
                        show_meta=True,
                        extra_filter=has_focus(default_buffer)
                        & multi_column_complete_style,
                    ),
                ),
                # 右侧提示符
                Float(
                    right=0,
                    top=0,
                    hide_when_covering_content=True,
                    content=_RPrompt(lambda: self.rprompt),
                ),
            ],
            min_float_height=4,
        )

        # 组装最终布局
        layout = HSplit(
            [
                main_input_container,
                ConditionalContainer(ValidationToolbar(), filter=~is_done),
                ConditionalContainer(
                    system_toolbar, dyncond("enable_system_prompt") & ~is_done
                ),
                # 多行模式下的 arg 工具栏
                ConditionalContainer(
                    Window(FormattedTextControl(self._get_arg_text), height=1),
                    dyncond("multiline") & has_arg,
                ),
                ConditionalContainer(search_toolbar, dyncond("multiline") & ~is_done),
                bottom_toolbar,
            ]
        )

        return Layout(layout, default_buffer_window)


# 使用示例
if __name__ == "__main__":
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.styles import Style
    
    # 创建自定义样式
    style = Style.from_dict({
        'frame.border': 'cyan',  # 青色边框
        # 'prompt': '#00aaff bold',   # 蓝色提示符
        'placeholder': '#888888',  # 灰色占位符
    })
    
    # 创建补全器
    completer = WordCompleter(
        ['hello', 'world', 'help', 'exit', 'test', 'example'],
        ignore_case=True
    )
    
    # 创建自定义会话
    # placeholder 使用 FormattedText 格式指定样式
    session = CustomPromptSession(
        placeholder=[('class:placeholder', 'Type a message, /command, or @path/to/file ...')],
        message='> ',
        completer=completer,
        style=style,
        show_frame=True,  # 启用边框
        complete_while_typing=True,
        wrap_lines= True,
    )
    
    print("自定义 PromptSession 示例")
    print("输入 'exit' 退出")
    print("边框只包围输入区域\n")
    
    while True:
        try:
            result = session.prompt()
            if result.lower() == 'exit':
                break
            print(f'你输入了: {result}')
        except KeyboardInterrupt:
            print('\n用户按了 Ctrl-C')
            break
        except EOFError:
            print('\n用户按了 Ctrl-D')
            break
