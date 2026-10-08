"""核验前置的**运行时**：真的去 stat / load，再据观测结果归因（方案 §3.4）。

与 `origin.py` 分开的理由只有一个：`origin.py` 是纯数据形状（可被两侧逐字实现、可单独测），
这里才是"动手核验"的那一半——它读文件系统，因此必须能在测试里被喂一个假的路径而不需要
改动形状本身。

四条硬规则（与 §3.4 逐条对应）：

1. **核验前置**：说"配置读不到"之前先真的去读它；`stat` 说它其实在 → 结论**必须**改成
   "问题不在这一侧"（`platform.config_unreadable` 或 `unknown_origin`），不许换对象继续指控。
2. **核验允许证伪自己人**：判据不成立 → `unknown_origin`，`causal_link=unproven`。
3. **写不出 fix 的 origin 不许存在**：每一个分支都给出"改成什么形态就能过"。
4. **核验记录无权威**：调用方（Hook）只把它写进审计与诊断行，**不许**据此 allow/block。
"""

from __future__ import annotations

import stat as stat_module
from pathlib import Path
from typing import Any, Mapping, Optional

from .origin import (
    Origin,
    build_origin,
    config_path_in,
    unknown_origin,
)

__all__ = ["verification_of_config", "origin_from_failure", "ORIGIN_BY_REASON_CODE"]

OWNER = "platform.attribution"

# 失败码 → 是否走配置核验的一族。**只有**这条闭集里的码会被核验；
# 其余码一律 unknown_origin（"这条理由目前没有可执行的证伪判据"）。
ORIGIN_BY_REASON_CODE: Mapping[str, str] = {
    "startup_error": "platform.config_unreadable",
    "config_error": "platform.config_unreadable",
    # 接线自检失败也是"这一份被声明的输入读不到 / 不成立"（G12）：对象是 hooks.json，
    # 不是 adapter 配置——所以调用方必须把**那一个**路径交进来，不许拿 adapter 配置顶替。
    "wiring_error": "platform.config_unreadable",
    "evidence_unavailable": "platform.evidence_unavailable",
}

_CONFIG_FIX = (
    "先证明这份配置读得到：确认路径存在、是文件、是 UTF-8、能被 YAML 解析"
    "（缺哪一步就改哪一步）；确认之后再重跑一次，这次核验会给出被点名的那个字段"
)

_EVIDENCE_FIX = (
    "把取证这一段的输入补齐并让它可复现：pre_evidence 的 registry_root / workspace 必须存在，"
    "验证器数据（validation/validators.yaml）必须读得到；补齐后重跑，理由会指名是哪一份输入"
)

_EVIDENCE_SOURCE = "从失败原文里取回（--config 是 adapter 配置，与取证输入无关，不参与核验）"


def _read_text(path: Path) -> tuple[Optional[str], str]:
    """尽力读一份文本：返回 (文本或 None, 观测结果)。读不到不抛异常——观测本身就是结论。"""

    try:
        return path.read_text(encoding="utf-8"), "read ok"
    except FileNotFoundError:
        return None, "FileNotFoundError（ENOENT）"
    except IsADirectoryError:
        return None, "IsADirectoryError（它是一个目录）"
    except UnicodeDecodeError as error:
        return None, f"UnicodeDecodeError（不是 UTF-8）：{error}"
    except OSError as error:
        return None, f"OSError：{type(error).__name__}: {error}"


def _describe(error: OSError) -> str:
    """OSError 的可读描述：类型 + strerror（`str(OSError)` 会带上出错的绝对文件名）。"""

    return type(error).__name__ + "（" + (error.strerror or str(error)) + "）"


def _observe(path: Path) -> tuple[str, str, bool, bool]:
    """对一个被点名的输入做一次**真实观测**。

    返回 (method, result, 是否确实不可用, 是不是目录)；四种结果一种都不合并：
    不存在 / 是目录 / 读不出来 → 这份输入确实不可用；读得到 → 指控被证伪。

    观测自己**不许抛异常**：stat 也会抛（EACCES、路径在检查与读取之间被换掉、名字太长…），
    而这条路径存在的意义就是"把失败原因记下来"——抛出去等于把原因弄丢，调用方
    （只认结构化结果的那一侧）还会把它当成另一种失败。顺带，只有真的读过 errno
    才说得出是哪一种观测结果：`Path.exists()` 只吞 ENOENT/ENOTDIR/EBADF/ELOOP，
    其余 OSError 会逃逸；而它返回 False 时也分不清"不存在"与"看不到"。
    """

    try:
        info = path.stat()
    except FileNotFoundError:
        return "stat", "stat 观测：该路径不存在（ENOENT）", True, False
    except OSError as error:
        return "stat", "stat 观测：" + _describe(error), True, False
    if stat_module.S_ISDIR(info.st_mode):
        return "stat", "stat 观测：该路径是一个目录，不是一份可读的输入", True, True
    text, how = _read_text(path)
    if text is None:
        return "read", "读观测：" + how + "（文件在，但这份内容读不出来）", True, False
    # 只读到"它是可读的 UTF-8"为止：**没有解析**它的内容。观测方法必须与真正做过的事
    # 对齐——写 load 等于声称解析过（配置族的证伪理由还会据此说"不是配置读不到这一侧"），
    # 而内容层面的问题（语法错、缺字段）要另一次核验才说得出来。
    return (
        "read",
        "读观测：读到了 " + str(len(text)) + " 字符（UTF-8 可读）；这一步没有解析它的内容",
        False,
        False,
    )


def _evidence_unavailable_origin(*, detail: str) -> Origin:
    """取证族（platform.evidence_unavailable）的归因：**先真的去看**被点名的那份输入。

    规则 1 在这一族同样是硬要求：调用方（Hook）总把 adapter 配置交进来，而"取证输入
    不可用"与那份配置无关——拿它当对象就是 §3.4 禁止的"换一个对象继续指控"。因此对象
    只认失败原文点名的那一份输入，并且必须真的 stat / read 它：看不到才叫"不可用"，
    看得到就把这条指控证伪掉（规则 2，落 unknown_origin）。
    """

    named = config_path_in(detail)
    if named is None:
        return build_origin(
            origin="platform.evidence_unavailable",
            owner=OWNER,
            object_kind="path",
            object_value="<未指名>",
            object_source="失败原文里没有指名任何取证输入",
            method="none",
            result="取证这一段的输入没有被点名，核验前置没有对象可执行",
            verified=False,
            fix=_EVIDENCE_FIX,
            causal_link="unproven",
        )
    path = Path(named)
    display = path.name or str(path)
    method, result, unavailable, _is_directory = _observe(path)
    if not unavailable:
        return unknown_origin(
            reason=(
                "核验证伪了自己人：失败原文点名的取证输入 "
                + display
                + " 现在读得到（"
                + result
                + "），因此「取证输入不可用」这一侧不成立"
            ),
            owner=OWNER,
            object_value=display,
            object_source=_EVIDENCE_SOURCE,
            method=method,
        )
    return build_origin(
        origin="platform.evidence_unavailable",
        owner=OWNER,
        object_kind="file" if method == "read" else "path",
        object_value=display,
        object_source=_EVIDENCE_SOURCE,
        method=method,
        result=result,
        verified=True,
        fix=_EVIDENCE_FIX,
        causal_link="proven",
    )


def verification_of_config(config_path: Optional[Path | str], *, source: str) -> Origin:
    """对一份**具体**配置输入做核验，并按观测结果归因（R-g 的载体）。

    四种观测结果对应四种结论，一种都不许合并：

    - `stat` 说它不在 → `platform.config_unreadable`（`causal_link=proven`：证伪判据成立，
      理由指着的对象确实是这一位）；
    - `stat` 说它在、但读不到 / 不是 UTF-8 → `host.config_unreadable` 之下的
      `platform.config_unreadable`（**不是**"不存在"）——两者都是配置输入的问题，
      但理由必须说得出是哪一种；
    - 读得到（UTF-8）→ **核验证伪了"读不到"这条指控** → `unknown_origin`，`method="read"`；
      这一步只做了读观测、**没有解析**内容，所以结论只说"不是读不到这一侧"，
      不声称内容层面没问题（那要另一次核验，`causal_link=unproven`）。
    - 配置路径给不出来 → `unknown_origin`（没有对象就没有核验）。
    """

    if config_path is None or str(config_path).strip() == "":
        return unknown_origin(
            reason="这一条理由没有指名任何配置输入，核验前置没有对象可执行",
            owner=OWNER,
            object_value="<未指名>",
            object_source=source,
        )

    path = Path(str(config_path))
    display = path.name or str(path)
    # 一次真实观测决定一切：观测路径自己不抛异常，所以"看不到"（EACCES 等）与
    # "不存在"不会被合并成同一句话，也不会把这条诊断路径变成一次崩溃。
    method, result, unavailable, is_directory = _observe(path)
    if unavailable:
        return build_origin(
            origin="platform.config_unreadable",
            owner=OWNER,
            object_kind="path" if is_directory else "file",
            object_value=display,
            object_source=source,
            method=method,
            result=result,
            verified=True,
            fix=(
                "把配置指到一个文件（而不是目录）：" + _CONFIG_FIX
                if is_directory
                else _CONFIG_FIX
            ),
            causal_link="proven",
        )

    # 走到这里：核验**证伪**了"配置读不到"这条指控。按 §3.4 落 unknown_origin，
    # 不许把对象换成"配置里的某个字段"——那正是"换一个对象继续指控"。
    return unknown_origin(
        reason=(
            "核验证伪了自己人：被点名的配置 "
            + display
            + " 存在、可读、是 UTF-8（"
            + result
            + "），因此这条理由不是「配置读不到」这一侧的问题"
        ),
        owner=OWNER,
        object_value=display,
        object_source=source,
        method=method,
    )


def origin_from_failure(
    *,
    reason_code: str,
    detail: str = "",
    config_path: Optional[Path | str] = None,
    config_source: str = "--config（本次调用的 adapter 配置）",
) -> Origin:
    """失败码 + 失败原文 → 一条结构化归因（核验前置已经执行过）。

    `config_path` 缺省时**尽力**从失败原文里取回被点名的配置文件；取不到就落
    `unknown_origin`——宁可不归因，也不照抄一段猜出来的路径。
    """

    expected = ORIGIN_BY_REASON_CODE.get(reason_code)
    if expected is None:
        return unknown_origin(
            reason=(
                "原因码 " + str(reason_code) + " 目前没有可执行的证伪判据（本台阶只覆盖"
                "配置族与 spawn 输入族），因此不做归因"
            ),
            owner=OWNER,
            object_value=str(reason_code) or "<空>",
            object_source="reason_code",
        )

    if expected == "platform.evidence_unavailable":
        # 取证族单独一条：它的对象是**取证输入**，而 config_path 是本次调用的 adapter
        # 配置——两者不是一回事，详见 _evidence_unavailable_origin。
        return _evidence_unavailable_origin(detail=detail)

    candidate: Any = config_path
    source = config_source
    if candidate is None or str(candidate).strip() == "":
        candidate = config_path_in(detail)
        source = "从失败原文里取回（--config 未提供）"
    return verification_of_config(candidate, source=source)
