r"""把受跟踪的臂配置**模板**物化成可用的臂配置目录（只用标准库）。

它回答什么
==========

臂配置是实验输入，必须**换台机器也可比**：同一份内容在两台机器上要得到同一个摘要。
而 `dsh-adapter.yaml` 的三个路径字段（`rules[0]` / `rules_root` /
`pre_evidence.registry_root`）原本是机器绝对路径，换台机器就全变。所以受跟踪的模板里写
`${REPO_ROOT}` 占位，物化时才替换成 `--repo-root` 的 POSIX 绝对路径；记录
`materialized.json` 只留模板与副本各自的组合摘要与逐文件摘要，**不含绝对路径**。

三条命令
========

    python materialize_arm_config.py --template <模板目录> --target <目标目录> --repo-root <仓库根>
    python materialize_arm_config.py ... --json      # 标准输出就是 materialized.json 的字节

`--template` / `--target` 的相对路径按 `--repo-root` 解析（与 `freeze_manifest.py` 同一条）。
模板目录的**每个文件**按相对路径复制到目标目录；占位符只替换文本文件里的 `${REPO_ROOT}`。

占位符契约
==========

- 本脚本只认 `${REPO_ROOT}`；出现别的 `${...}` 一律是模板非法（不猜，不静默保留）；
- 替换后仍含 `${` 同样是模板非法（`--repo-root` 自己的路径里带占位符形状时也会命中）；
- 模板里出现绝对路径（`C:/`、反斜杠的 `C:` 写法、`/Users/`、`/home/`，大小写不敏感）
  同样是模板非法——绝对路径就是"换台机器不可比"的那一件事实，必须写成 `${REPO_ROOT}`。

物化记录（`materialized.json`）的字段
=====================================

| 字段 | 内容 |
| --- | --- |
| `schema_version` | `"1.0"`（`AB_ARM_CONFIG_MATERIALIZATION_SCHEMA_VERSION`） |
| `template` | `{path, file_count, combined_digest}`：模板的仓库相对路径与组合摘要 |
| `target` | `{path, file_count, combined_digest}`：副本同上（仓库外写 `<outside-workspace>`） |
| `tokens` | `{"${REPO_ROOT}": n}`：本次替换的占位符总数（键恒在，0 也写） |
| `files` | 每文件一条 `{path, template_sha256, target_sha256, tokens_replaced}`，按路径升序 |

组合摘要与 `freeze_manifest.py` 同一个算法：按**路径**升序的 `"<sha256>  <相对路径>"` 行
用一个换行连接、末尾再加一个换行，对整个字符串取 sha256。**记录自身不在摘要里**：
`materialized.json` 是这次物化的读数，不是被物化的输入；把它算进去就会自己引用自己，
第二次物化必然与第一次不同。所以"同输入两次逐字节相同"覆盖的是**副本文件 +
materialized.json 的全部字节**。

退出码（与 `bank/harness/README.md` 第 5 节同一条划分）
=======================================================

- `0`：成立（副本与记录都写好了）；
- `1`：**模板非法 / 事实不成立**：缺 `dsh-adapter.yaml` 或 `hooks.json`、未知或残留占位符、
  模板里出现绝对路径、文件不是 UTF-8、目录里有不可枚举的子目录；此时**一个字节都不写**；
- `2`：**参数 / 前置错**：`--repo-root` 下没有 `.git`、`--template` 不是目录、`--target` 是已有
  文件、`--target` 就是模板或落在模板里。

边界（引用读数之前先读这一条）
=============================

1. **不替使用者签审批条子**：`approval.json` 不模板化、也不生成；缺它时 `scaffold_arms.py` 写
   未签字占位，`run_session.py` 见到占位就拒绝发车。已签的条子留在目标目录里是**陈旧授权**，
   所以目标目录要新建/空。
2. **不删目标目录里的陈旧文件**：同名的覆盖，多出来的原样留着，并在 stderr 点名。
3. **不解析 YAML、不校验 `${REPO_ROOT}/...` 指向的路径是否存在**：物化只做字节替换。
4. **不跟随符号链接目录**（`os.walk` 默认），符号链接文件按内容读取。
5. **模板是文本**：非 UTF-8 文件按模板非法处理（判定不了占位符就不复制，不静默保留）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _ab_harness_common import (  # noqa: E402
    EXIT_INVALID,
    EXIT_OK,
    HarnessInputError,
    check_no_absolute_paths,
    combined_digest,
    display_path,
    find_repo_root,
    is_under,
    manifest_lines,
    render_json,
    sanitize_text,
    sha256_bytes,
    walk_files,
    write_text_lf,
)

#: 物化记录载荷自己的版本轴；加键 / 改语义必须按 AGENTS 第 55 条递增，并同批改
#: `bank/arm-configs/README.md` 与 `tests/unit/test_ab_arm_config.py`。轴登记由 Lead 落
#: `docs/project/architecture/版本轴登记表.md` 与 AGENTS 第 55 条。
AB_ARM_CONFIG_MATERIALIZATION_SCHEMA_VERSION = "1.0"

#: 模板里唯一被认的占位符。
REPO_ROOT_PLACEHOLDER = "${REPO_ROOT}"

#: 物化记录的固定文件名（写在目标目录里，不参与组合摘要）。
MATERIALIZED_RECORD = "materialized.json"

#: 模板必须提供的文件（其余文件原样复制；缺这两个就不是一份臂配置）。
REQUIRED_FILES: Tuple[str, ...] = ("dsh-adapter.yaml", "hooks.json")

#: 占位符形状；未知名字由调用方拒绝（AGENTS 第 3 条：不得静默忽略）。
_TOKEN = re.compile("[$][{]([^}]*)[}]")

#: 反斜杠：用 chr 取，源码里不写字面量，免得与转义规则纠缠。
_BACKSLASH = chr(92)

#: 模板里不许出现的绝对路径标记（小写比较）；第二个元素是报告给人看的写法。
_ABSOLUTE_MARKERS: Tuple[Tuple[str, str], ...] = (
    ("c:/", "C:/"),
    ("c:" + _BACKSLASH, "C:" + _BACKSLASH),
    ("/users/", "/Users/"),
    ("/home/", "/home/"),
)


# --------------------------------------------------------------------------- 路径


def _resolve(raw: str, repo_root: Path) -> Path:
    """相对路径按仓库根解析（与 freeze_manifest.py 同一条），绝对路径原样。"""

    path = Path(raw)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


# --------------------------------------------------------------------------- 模板


def _read_bytes(path: Path, label: str) -> bytes:
    """读一个模板文件的原始字节；读不到是**事实不成立**（退出 1），不当空文件。"""

    try:
        return path.read_bytes()
    except OSError as error:
        raise HarnessInputError(
            "%s 读不到（%s）" % (label, error.strerror or type(error).__name__),
            exit_code=EXIT_INVALID,
        ) from error


def _absolute_marker(text: str) -> Optional[str]:
    """文本里第一个绝对路径标记（报告用写法）；没有返回 None。"""

    lowered = text.lower()
    for needle, label in _ABSOLUTE_MARKERS:
        if needle in lowered:
            return label
    return None


def _scan_tokens(text: str) -> Tuple[Dict[str, int], List[str]]:
    """找 ${...} 占位符：返回（各 token 的出现次数, 问题）。

    未闭合的 `${` 与未登记的名字都是模板非法：保留一个本脚本替换不了的占位符，物化副本既
    不是模板也不是可用配置——那种"看起来物化过了"的状态比直接失败更难发现。
    """

    names = _TOKEN.findall(text)
    problems: List[str] = []
    if text.count("${") != len(names):
        problems.append("有未闭合的 ${ 占位符")
    unknown = sorted({name for name in names if name != "REPO_ROOT"})
    if unknown:
        rendered = ", ".join("${%s}" % name for name in unknown)
        problems.append("未知占位符 %s（本脚本只认 %s）" % (rendered, REPO_ROOT_PLACEHOLDER))
    return {REPO_ROOT_PLACEHOLDER: names.count("REPO_ROOT")}, problems


def load_template(
    repo_root: Path, template: Path
) -> Tuple[List[str], Dict[str, Dict[str, Any]], List[str]]:
    """读模板并替换占位符；返回（文件列表, 每文件的 {raw, materialized, tokens}, 问题）。

    问题**全部收集完再报**：一次调用就能看到"哪个文件含绝对路径"与"哪个文件缺了"，而不是
    改一处跑一次。有任何问题调用方都不写盘——半份物化副本比没有更危险。
    """

    label = display_path(template, repo_root)
    files, unreadable, _ignored = walk_files(template, (), label)
    if unreadable:
        raise HarnessInputError(
            "模板目录里有不可枚举的子目录：%s" % ", ".join(unreadable), exit_code=EXIT_INVALID
        )
    repo_root_posix = repo_root.as_posix()
    outputs: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []
    missing = [name for name in REQUIRED_FILES if name not in files]
    if missing:
        problems.append("模板缺必需文件 %s（%s）" % (missing, label))
    for relative in files:
        raw = _read_bytes(template / relative, relative)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            problems.append("%s 不是 UTF-8 文本（%s）" % (relative, error))
            continue
        marker = _absolute_marker(text)
        if marker is not None:
            problems.append(
                "%s 含绝对路径（%s）：模板里必须写 %s" % (relative, marker, REPO_ROOT_PLACEHOLDER)
            )
        tokens, token_problems = _scan_tokens(text)
        problems.extend("%s %s" % (relative, problem) for problem in token_problems)
        materialized = text.replace(REPO_ROOT_PLACEHOLDER, repo_root_posix)
        if "${" in materialized:
            problems.append(
                "%s 替换后仍含 ${（--repo-root 自己的路径里有占位符形状？）" % relative
            )
        outputs[relative] = {
            "raw": raw,
            "materialized": materialized.encode("utf-8"),
            "tokens": tokens,
        }
    return files, outputs, problems


# --------------------------------------------------------------------------- 载荷


def build_payload(
    repo_root: Path,
    template: Path,
    target: Path,
    files: Sequence[str],
    outputs: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """物化记录：两条摘要 + token 计数 + 逐文件摘要；路径一律仓库相对（仓库外是占位写法）。"""

    ordered = sorted(files)
    template_digest = combined_digest(
        manifest_lines((name, sha256_bytes(outputs[name]["raw"])) for name in ordered)
    )
    target_digest = combined_digest(
        manifest_lines((name, sha256_bytes(outputs[name]["materialized"])) for name in ordered)
    )
    total_tokens = sum(outputs[name]["tokens"][REPO_ROOT_PLACEHOLDER] for name in ordered)
    return {
        "schema_version": AB_ARM_CONFIG_MATERIALIZATION_SCHEMA_VERSION,
        "template": {
            "path": display_path(template, repo_root),
            "file_count": len(ordered),
            "combined_digest": template_digest,
        },
        "target": {
            "path": display_path(target, repo_root),
            "file_count": len(ordered),
            "combined_digest": target_digest,
        },
        "tokens": {REPO_ROOT_PLACEHOLDER: total_tokens},
        "files": [
            {
                "path": name,
                "template_sha256": sha256_bytes(outputs[name]["raw"]),
                "target_sha256": sha256_bytes(outputs[name]["materialized"]),
                "tokens_replaced": dict(outputs[name]["tokens"]),
            }
            for name in ordered
        ],
    }


# --------------------------------------------------------------------------- 写盘与输出


def _stale_entries(target: Path, produced: Sequence[str]) -> List[str]:
    """目标目录里不是本次产物的文件（同名覆盖，多出来的只点名、不删除）。"""

    if not target.is_dir():
        return []
    expected = set(produced) | {MATERIALIZED_RECORD}
    found: List[str] = []
    for item in sorted(target.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(target).as_posix()
        if relative not in expected:
            found.append(relative)
    return found


def _write_target(
    target: Path, files: Sequence[str], outputs: Dict[str, Dict[str, Any]], payload: Dict[str, Any]
) -> None:
    """先写副本、再写读数：读数是本次物化的事实，不参与摘要。"""

    for name in sorted(files):
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(outputs[name]["materialized"])
    write_text_lf(target / MATERIALIZED_RECORD, render_json(payload))


def _report(payload: Dict[str, Any]) -> None:
    """人类可读读数：逐文件两条摘要 + token 数，最后一行是两条组合摘要。"""

    template = payload["template"]
    target = payload["target"]
    print("materialize-arm-config: template=%s -> target=%s" % (template["path"], target["path"]))
    for entry in payload["files"]:
        print(
            "  %s  template_sha256=%s  target_sha256=%s  %s=%d"
            % (
                entry["path"],
                entry["template_sha256"],
                entry["target_sha256"],
                REPO_ROOT_PLACEHOLDER,
                entry["tokens_replaced"][REPO_ROOT_PLACEHOLDER],
            )
        )
    print(
        "tokens: %s=%d  files=%d"
        % (REPO_ROOT_PLACEHOLDER, payload["tokens"][REPO_ROOT_PLACEHOLDER], target["file_count"])
    )
    print(
        "RESULT: PASS template_digest=%s target_digest=%s"
        % (template["combined_digest"], target["combined_digest"])
    )


def _warn_stale(stale: Sequence[str]) -> None:
    """目标目录里的陈旧文件只点名，不删、不改退出码。"""

    if not stale:
        return
    print(
        "WARNING: 目标目录里有不是本次物化产物的文件 %s（不会被删除）；"
        "如果其中有已签的 approval.json，它是一次陈旧授权——先删掉再物化" % list(stale),
        file=sys.stderr,
    )


# --------------------------------------------------------------------------- 主流程


def _materialize(repo_root: Path, template: Path, target: Path, *, as_json: bool) -> int:
    """一次物化：先做参数与模板检查（不通过就一个字节都不写），再写副本与读数。"""

    if not template.is_dir():
        raise HarnessInputError("--template 不是目录：%s" % display_path(template, repo_root))
    if target.resolve() == template.resolve() or is_under(target, template):
        raise HarnessInputError(
            "--target 不能是 --template 本身、也不能落在模板目录里：物化会覆盖模板自己（%s）"
            % display_path(template, repo_root)
        )
    if target.exists() and not target.is_dir():
        raise HarnessInputError("--target 已存在且不是目录：%s" % display_path(target, repo_root))

    files, outputs, problems = load_template(repo_root, template)
    if problems:
        for problem in problems:
            print("PROBLEM: %s" % problem, file=sys.stderr)
        print("RESULT: FAIL（%d 条模板问题；**没有写盘**）" % len(problems), file=sys.stderr)
        return EXIT_INVALID

    payload = build_payload(repo_root, template, target, files, outputs)
    hits = check_no_absolute_paths(payload)
    if hits:
        for hit in hits:
            print("PROBLEM: 载荷里出现绝对路径 %s" % hit, file=sys.stderr)
        print("RESULT: FAIL（载荷自检不通过；**没有写盘**）", file=sys.stderr)
        return EXIT_INVALID

    _write_target(target, files, outputs, payload)
    stale = _stale_entries(target, files)
    if as_json:
        sys.stdout.write(render_json(payload))
    else:
        _report(payload)
    _warn_stale(stale)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "把臂配置模板物化成可用目录：复制每个文件，并把 ${REPO_ROOT} 换成仓库根的绝对路径"
        )
    )
    parser.add_argument(
        "--template", required=True, help="受跟踪的模板目录（含 ${REPO_ROOT} 占位）"
    )
    parser.add_argument("--target", required=True, help="物化副本的目标目录（建议新建/空）")
    parser.add_argument(
        "--repo-root", required=True, help="仓库根：占位符替换成它的 POSIX 绝对路径（要求有 .git）"
    )
    parser.add_argument("--json", action="store_true", help="标准输出直接打印 materialized.json")
    return parser


def run(argv: Optional[Sequence[str]] = None) -> int:
    """CLI 入口：约定见模块 docstring 的退出码表。"""

    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        repo_root = find_repo_root(_HERE, Path(args.repo_root))
        template = _resolve(args.template, repo_root)
        target = _resolve(args.target, repo_root)
        return _materialize(repo_root, template, target, as_json=args.json)
    except HarnessInputError as error:
        print("materialize-arm-config: %s" % sanitize_text(str(error), None), file=sys.stderr)
        return error.exit_code


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(argv)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
