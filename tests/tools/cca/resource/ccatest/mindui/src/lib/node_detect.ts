const calcTextNode = (element: Text, _level: number) => {
    const container = element.parentNode as HTMLElement;
    const computedStyle = window.getComputedStyle(container as HTMLElement);
    const range = document.createRange();
    range.selectNodeContents(element);
    const rects = range.getClientRects();
    const rect = container.getBoundingClientRect();
    const _styles = container.style.cssText?.split(/; +/g)
                        .filter(e=>e.trim())
                        .map(e=>{
                            const [k, v] = e.split(/: +/g).map(it=>it.trim());
                            return {
                                key: k,
                                value: v
                            };
                        });
    const info = {
        tagName: container.tagName.toLowerCase(),
        classNames: container.className.split(/ +/g),
        styles: _styles,
    };
    const calcRes = {
        textInfo: {
            textContent: element.textContent?.trim(),
            lineCount: rects.length,
            wordCount: element.textContent?.trim().split(/\\s+/).length
        },
        fontInfo: {
            fontSize: computedStyle.fontSize,
            fontFamily: computedStyle.fontFamily,
            lineHeight: computedStyle.lineHeight,
            color: computedStyle.color
        },
        containerInfo: {
            elementHeight: container.offsetHeight,
            elementWidth: container.offsetWidth,
            position: {
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: rect.height
            }
        },
        depth: _level
    };
    return calcRes;
};



interface ElementPathProps {
    tagName: string;
    classNames: Array<string>;
    styles: Array<{
        key: string;
        value: string;
    }>;
    siblingIndex: number;
};

interface ResultProps {
    textInfo: {
        textContent: string | undefined;
        lineCount: number;
        wordCount: number | undefined;
    };
    fontInfo: {
        fontSize: string;
        fontFamily: string;
        lineHeight: string;
        color: string;
    };
    containerInfo: {
        elementHeight: number;
        elementWidth: number;
        position: {
            x: number;
            y: number;
            width: number;
            height: number;
        };
    };
    depth: number;
};

const _findNodeReCursive = (node: Node, results: Array<ResultProps>, level: number) => {
    for (let i = 0; i < node.childNodes.length; i++) {
        const child = node.childNodes[i];
        if (child.nodeType === Node.ELEMENT_NODE) {
            const element = child as HTMLElement;
            const excludeTags = ['SCRIPT', 'STYLE', 'NOSCRIPT', 'META'];
            if (excludeTags.includes(element.tagName)) {
                continue;
            }
            // 检查是否可见
            const style = window.getComputedStyle(element);
            if (style.display === 'none' ||
                style.visibility === 'hidden' ||
                style.opacity === '0') {
                continue;
            }
            _findNodeReCursive(child, results, level + 1);
        } else if (child.nodeType === Node.TEXT_NODE) {
            const res = calcTextNode(child as Text, level + 1);
            results.push(res);
        } else {
            continue;
        }
    }
}

const findAllTextNodes = () => {
    let node = document.querySelector('div[data-radix-scroll-area-viewport]')! as HTMLElement;
    let nodeArray: Array<HTMLElement>;
    for (; ; node = node.childNodes[0] as HTMLElement) {
        const length = node.childNodes.length;
        if (length === 1) {
            continue;
        }
        nodeArray = new Array<HTMLElement>();
        for (let i = 0; i < node.childNodes.length; i++) {
            const child = node.childNodes[i];
            if (child.nodeType === Node.ELEMENT_NODE) {
                const element = child as HTMLElement;
                const excludeTags = ['SCRIPT', 'STYLE', 'NOSCRIPT', 'META'];
                if (excludeTags.includes(element.tagName)) {
                    continue;
                }
                const style = window.getComputedStyle(element);
                if (style.display === 'none' ||
                    style.visibility === 'hidden' ||
                    style.opacity === '0') {
                    continue;
                }
                nodeArray.push(element);
            } else {
                continue;
            }
        }
        if (nodeArray.length === 1) {
            continue;
        }
        break;
    }
    const infoArr = nodeArray.map(e => {
        const res = new Array<ResultProps>();
        _findNodeReCursive(e, res, 0);
        return res;
    }).filter(e=>e.length > 0);
    return infoArr;
};