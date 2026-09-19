---
name: refcheck
description: 涉及文档与代码之间的引用时使用。触发场合：要写「见 X 文件第 N 行」「详见某函数」这类指路、要新增一条双向引用、改动了被别人引用的代码或文档、提交前想确认引用没有失真、或看到 `<|e:` / `<|/e:` 这类标记不知其意。本文件只是触发器，说明书由工具自己打印。
---

# refcheck

**本文件不含说明书。** 正文（命令、字段、状态、流程）随实现变，写在两处就要多一道保鲜机制，而防腐烂的手段本身也会腐烂。所以正文一律现场取：

```bash
python tools/refcheck/refcheck.py manual          # 全文
python tools/refcheck/refcheck.py manual --brief  # 精简版：两条禁令 + 命令清单
```

不确定怎么用就 `--brief`；要动手就先读全文。

本目录只有这一个文件。工具在 [`tools/refcheck/`](../../../tools/refcheck/)。
