import markdownit from "markdown-it";
import DOMPurify from "dompurify";
import "./markdown.css";

// Plugins
import md_abbr from "markdown-it-abbr";
import md_container from "markdown-it-container";
import md_deflist from "markdown-it-deflist";
import md_footnote from "markdown-it-footnote";
import md_ins from "markdown-it-ins";
import md_mark from "markdown-it-mark";

const Markdown = (props: { content: string }) => {
  const md = markdownit("default")
    .use(md_abbr)
    .use(md_mark)
    .use(md_container, "warning")
    .use(md_deflist)
    .use(md_footnote)
    .use(md_ins);

  md.renderer.rules.table_open = function () {
    return '<table class="table table-striped">\n';
  };

  const result = md.render(props.content);
  const sanitizedResult = DOMPurify.sanitize(result);

  return (
    <div
      className="markdown-body"
      dangerouslySetInnerHTML={{ __html: sanitizedResult }}
    />
  );
};

const MarkdownExample = () => {
  const content = `
在北京办理摩托车车照，您可以参考以下步骤：
# 一、 确认申请条件
## **1. 年龄**
申请普通三轮摩托车、普通二轮摩托车准驾车型，在 18 周岁以上，60 周岁以下；年龄在 60 周岁以上、70 周岁以下能够通过记忆力、判断力、反应力等能力测试的，也可以申请；申请轻便摩托车准驾车型在 18 周岁以上，70 周岁以上通过能力测试也可申请。  
## **2. 身体**  
两眼裸视力或者矫正视力达到对数视力表 4.9 以上（单眼视力障碍，优眼裸视力或者矫正视力达到对数视力表 5.0 以上，且水平视野达到 150 度也有相应准驾可申请）；无红绿色盲；两耳分别距音叉 50 厘米能辨别声源方向（有听力障碍但佩戴助听设备能达条件，可申请部分准驾车型）；双下肢健全且运动功能正常，不等长度不得大于 5 厘米（下肢有缺失情况也有对应申请条件）；躯干、颈部无运动功能障碍。

**Unordered**

+ Create a list by starting a line with \`+\`, \`-\`, or \`*\`
+ Sub-lists are made by indenting 2 spaces:
  - Marker character change forces new list start:
    * Ac tristique libero volutpat at
    + Facilisis in pretium nisl aliquet
    - Nulla volutpat aliquam velit
+ Very easy!

Ordered
1. Lorem ipsum dolor sit amet
2. Consectetur adipiscing elit
3. Integer molestie lorem at massa

| Option | Description |
| ------ | ----------- |
| data   | path to data files to supply the data that will be passed into templates. |
| engine | engine to be used for processing templates. Handlebars is the default. |
| ext    | extension to be used for dest files. |

---

  # 二、 准备材料
## Emphasis

**This is bold text**

__This is bold text__

*This is italic text*

_This is italic text_

~~Strikethrough~~

## Blockquotes


> Blockquotes can also be nested...
>> ...by using additional greater-than signs right next to each other...
> > > ...or with spaces between arrows.


## Links

[link text](http://dev.nodeca.com)

## Images

![Minion](https://octodex.github.com/images/minion.png)

### [\\<ins>](https://github.com/markdown-it/markdown-it-ins)

++Inserted text++


  `;
  return <Markdown content={content} />;
};

export default Markdown;

export { Markdown, MarkdownExample };
