r"""tools/dsh_sandbox_loop.py 的「dsh 起不来」归因检查（不依赖本机能否起 dsh）。

本轮缺陷（轮 14 / task-4）：真实日志里的权限错误落在**系统 temp**
（EPERM: operation not permitted, mkdtemp 指向 <Temp>\dsh-spill-XXXXXX），
而旧判据只要求「出现权限标记」+「文本里出现 profiles / cordis / .dsh / dsh-home 任一 token」。
真实 dsh 崩溃日志的堆栈帧里恰好有 <dsh-home>/profiles/headless/#spill-local，
于是**任何一种** dsh 启动失败都被写成「写 $DSH_HOME 下的 profile 被拒」——归因错了。

这些用例把合成日志直接喂给判定函数（外加一条把 main() 的判定路径整条驱动一遍的用例）：
既不需要 dsh 可执行文件，也不需要本机真的起不来 dsh，因此任何 runner 上都能守住这条判据。

判据（修后）分三层，且**只承认能归因的那一类**：
  1. 被拒路径落在 $DSH_HOME（或其子目录）下 → profile_write_denied（沿用 dsh_startup_denied 状态）；
  2. 被拒路径落在 dsh 自己的启动临时区（系统 temp / 名字以 dsh- 开头的 scratch）**且**日志里有
     dsh 启动崩溃的原文 → other_path_denied（独立状态，reason 里写出被拒路径）；
  3. 其它一律**不产生环境跳过**：宁可让真失败保持红，也不要把无关的 EPERM 洗成 skipped。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import dsh_sandbox_loop as loop
import pytest

pytestmark = pytest.mark.integration

DEFAULT_DSH_HOME = Path.home() / ".dsh"


def profile_path() -> str:
    """默认 $DSH_HOME 下的 profile 配置路径（随运行机器解析，不写死盘符）。"""

    return str(DEFAULT_DSH_HOME / "profiles" / "headless" / "cordis.yml")


def temp_scratch_path() -> str:
    """本机临时根下的 dsh scratch 目录（spill-local 的 mkdtemp 目标形态）。"""

    return str(Path(tempfile.gettempdir()) / "dsh-spill-XXXXXX")


def log_real_temp_spill() -> str:
    """真实形态：被拒路径只有系统 temp，但堆栈帧里带着 dsh home 的 profiles 路径。"""

    return (
        "file:///C:/Users/x/AppData/Roaming/npm/node_modules/@deepseek-ai/dsh/"
        "node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:2738\n"
        "Error: dsh: plugin tree failed to load: failed to apply loader entry include "
        "(cordis:include): failed to apply loader entry spill-local "
        "(@deepseek-ai/dsh-spill-local): EPERM: operation not permitted, mkdtemp "
        r"'C:\Users\ZNM\AppData\Local\Temp\dsh-spill-XXXXXX'" + "\n"
        "Error: EPERM: operation not permitted, mkdtemp "
        r"'C:\Users\ZNM\AppData\Local\Temp\dsh-spill-XXXXXX'" + "\n"
        "    at mkdtempSync (node:fs:3111:18)\n"
        "    at file:///C:/Users/ZNM/Downloads/Memory/.tmp/round-09/dsh-home/"
        "profiles/headless/#spill-local\n"
        "    at async runProfile (file:///C:/Users/x/npm/node_modules/@deepseek-ai/"
        "dsh/lib/profile-boot-BNu17Y9U.js:274:15)\n"
    )


def log_boot_crash_unattributable_path() -> str:
    """启动确实崩了，但被拒路径既不是 $DSH_HOME 也不是 dsh 的 scratch：不许算环境跳过。"""

    unrelated = str(Path(tempfile.gettempdir()).parent / "other-app" / "lock.db")
    return (
        "Error: dsh: plugin tree failed to load: failed to apply loader entry include\n"
        f"Error: EPERM: operation not permitted, open '{unrelated}'\n"
        "    at async runProfile (file:///C:/Users/x/npm/node_modules/@deepseek-ai/"
        "dsh/lib/profile-boot.js:274:15)\n"
    )


def log_profile_denied(style: str = "node") -> str:
    """只有 $DSH_HOME 下的 profile 被拒：三种常见原文形态都必须解析出同一条路径。"""

    target = profile_path()
    if style == "node":
        return (
            f"Error: EPERM: operation not permitted, open '{target}'\n"
            "    at Object.openSync (node:fs:596:3)\n"
            "    at loadProfile (file:///C:/Users/x/npm/node_modules/@deepseek-ai/"
            "dsh/lib/profile-boot-BNu17Y9U.js:210:18)\n"
            "    at async runCli (file:///C:/Users/x/npm/node_modules/@deepseek-ai/"
            "dsh/lib/bin.js:207:5)\n"
        )
    if style == "python":
        return f"PermissionError: [Errno 13] Permission denied: '{target}'\n"
    return f"[WinError 5] Access is denied: '{target}'\n"


def log_local_temp_scratch() -> str:
    """本机临时根下的同一形态：被拒路径随平台解析，保证判据不依赖写死的盘符。"""

    scratch = temp_scratch_path()
    return (
        "file:///C:/x/npm/node_modules/@deepseek-ai/dsh/node_modules/"
        "@deepseek-ai/dsh-app-boot/lib/index.js:2738\n"
        "Error: dsh: plugin tree failed to load: failed to apply loader entry spill-local: "
        f"EPERM: operation not permitted, mkdtemp '{scratch}'\n"
        "    at async runProfile (file:///C:/x/npm/node_modules/@deepseek-ai/"
        "dsh/lib/profile-boot.js:274:15)\n"
    )


def log_profile_and_temp_denied() -> str:
    return log_real_temp_spill() + log_profile_denied()


def log_hook_spawn_eperm() -> str:
    """说明 Hook 进程起不来（spawn EPERM）：属于另一条跳过路径，不是 dsh 启动失败。"""

    return (
        "dsh: loaded profile 'headless' from "
        + profile_path()
        + "\npolicy-hook: Hook 无法执行（spawn EPERM），按失败关闭拒绝该工具调用\n"
    )


def log_unrelated_eperm_git_lock() -> str:
    """日志里出现 EPERM，但目标是一个与 dsh 启动无关的仓库文件。"""

    lock = "C:/work/demo-shop/.git/index.lock"
    return (
        "dsh: loaded profile 'headless' from " + profile_path() + "\n"
        f"[hook] git: EPERM: operation not permitted, unlink '{lock}'\n"
    )


def log_no_permission_error() -> str:
    return (
        "dsh: loaded profile 'headless' from " + profile_path() + "\n"
        "[agent] 我没有调用任何写类工具，会话正常结束。\n"
    )


# (用例名, 日志, 期望状态)：None 表示「不许产生环境跳过」
CASES = (
    ("real_temp_spill_only", log_real_temp_spill(), loop.OTHER_PATH_DENIED),
    ("local_temp_scratch_only", log_local_temp_scratch(), loop.OTHER_PATH_DENIED),
    ("node_profile_denied_only", log_profile_denied("node"), loop.PROFILE_WRITE_DENIED),
    ("python_profile_denied_only", log_profile_denied("python"), loop.PROFILE_WRITE_DENIED),
    ("winerror_profile_denied_only", log_profile_denied("winerror"), loop.PROFILE_WRITE_DENIED),
    ("profile_and_temp_denied", log_profile_and_temp_denied(), loop.PROFILE_WRITE_DENIED),
    ("hook_spawn_eperm", log_hook_spawn_eperm(), None),
    ("unrelated_eperm_git_lock", log_unrelated_eperm_git_lock(), None),
    ("boot_crash_unattributable_path", log_boot_crash_unattributable_path(), None),
    ("no_permission_error", log_no_permission_error(), None),
)


@pytest.mark.parametrize("name,text,expected", CASES, ids=[case[0] for case in CASES])
def test_permission_error_is_classified_by_denied_path(name: str, text: str, expected: str | None):
    denial = loop.classify_startup_denial(text)
    if expected is None:
        assert denial is None, f"{name}: 不该被判成环境跳过，实际 {denial.kind}（{denial.path}）"
    else:
        assert denial is not None, f"{name}: 应该判成 {expected}，实际没有识别出被拒路径"
        assert denial.kind == expected
        assert denial.path, f"{name}: 判定必须带上被拒路径原文"


def test_temp_denial_is_not_described_as_profile_write():
    """本轮缺陷的正面断言：temp 被拒时不许出现「写 profile 被拒」那套措辞。"""

    denial = loop.classify_startup_denial(log_real_temp_spill())
    assert denial is not None
    reason = loop.startup_denied_reason(denial)
    assert denial.kind == loop.OTHER_PATH_DENIED
    assert "dsh-spill-XXXXXX" in reason, "reason 必须写出是哪条路径被拒"
    assert "profiles/*.yml" not in reason, "temp 被拒不许写成「$DSH_HOME 下的 profile 写不进去」"


def test_profile_denial_reason_names_the_profile_path():
    denial = loop.classify_startup_denial(log_profile_denied())
    assert denial is not None and denial.kind == loop.PROFILE_WRITE_DENIED
    reason = loop.startup_denied_reason(denial)
    assert profile_path() in reason, "reason 必须写出是哪条路径被拒"


def test_all_denied_paths_are_recorded_when_both_are_present():
    denial = loop.classify_startup_denial(log_profile_and_temp_denied())
    assert denial is not None and denial.kind == loop.PROFILE_WRITE_DENIED
    assert len(denial.paths) == 2, "同一条日志里的多条被拒路径都要留下，不能只报第一条"


def test_scan_reads_log_dir_and_ignores_clean_logs(tmp_root: Path, monkeypatch: pytest.MonkeyPatch):
    logs = tmp_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(loop, "LOGS", logs)
    (logs / "block-run.txt").write_text(log_no_permission_error(), encoding="utf-8")
    assert loop.dsh_startup_denial() is None
    assert loop.dsh_could_not_start() is False
    (logs / "block-run.txt").write_text(log_real_temp_spill(), encoding="utf-8")
    denial = loop.dsh_startup_denial()
    assert denial is not None and denial.kind == loop.OTHER_PATH_DENIED
    assert loop.dsh_could_not_start() is True


def drive_main(
    tmp_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    log_text: str,
    *,
    require_dsh: bool,
) -> tuple[int, dict]:
    """把 main() 的判定路径整条驱动一遍：假 dsh、假项目、真日志。"""

    project = tmp_root / "demo-shop"
    logs = tmp_root / "logs"
    artifact = tmp_root / "artifact.json"
    (project / "src" / "shop").mkdir(parents=True, exist_ok=True)
    (project / "src" / "shop" / "order_controller.py").write_text(
        "def create() -> dict:\n    return {}\n", encoding="utf-8"
    )
    logs.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(loop, "PROJECT", project)
    monkeypatch.setattr(loop, "LOGS", logs)
    monkeypatch.setattr(loop, "ARTIFACT", artifact)
    monkeypatch.setattr(loop, "build_project", lambda *, keep: None)
    monkeypatch.setattr(loop, "dsh_argv", lambda: ["dsh"])

    def fake_run(prompt: str, log_name: str) -> int:
        (logs / log_name).write_text(log_text, encoding="utf-8")
        return 1

    monkeypatch.setattr(loop, "run_dsh", fake_run)
    argv = ["--require-dsh"] if require_dsh else []
    code = loop.main(argv)
    return code, json.loads(artifact.read_text(encoding="utf-8"))


def test_main_reports_other_path_denied_for_real_temp_failure(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    code, payload = drive_main(tmp_root, monkeypatch, log_real_temp_spill(), require_dsh=True)
    assert code == 1, "--require-dsh 下环境跳过必须失败关闭"
    assert payload["result"] == "skipped"
    assert payload["environment_skipped"] is True
    assert payload["dsh_startup_denied"] is True
    assert payload["dsh_startup_denied_kind"] == loop.OTHER_PATH_DENIED
    assert "dsh-spill-XXXXXX" in payload["reason"]
    assert "profiles/*.yml" not in payload["reason"]
    assert payload["dsh_startup_denied_paths"], "载荷里要留下全部被拒路径"


def test_main_reports_profile_denied_for_profile_failure(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    code, payload = drive_main(tmp_root, monkeypatch, log_profile_denied(), require_dsh=True)
    assert code == 1
    assert payload["result"] == "skipped"
    assert payload["dsh_startup_denied_kind"] == loop.PROFILE_WRITE_DENIED
    assert profile_path() in payload["reason"]


def test_main_does_not_launder_unrelated_eperm_into_skip(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """有 EPERM 但与启动无关：不许记成 skipped，必须保持 fail。"""

    code, payload = drive_main(
        tmp_root, monkeypatch, log_unrelated_eperm_git_lock(), require_dsh=False
    )
    assert payload["result"] == "fail"
    assert payload.get("environment_skipped") is False
    assert payload.get("dsh_startup_denied") is None
    assert code == 1


def test_main_does_not_launder_missing_eperm_into_skip(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    code, payload = drive_main(tmp_root, monkeypatch, log_no_permission_error(), require_dsh=False)
    assert payload["result"] == "fail"
    assert payload.get("environment_skipped") is False
    assert code == 1


def test_environment_skip_keeps_documented_exit_codes(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """跳过默认不红（0），--require-dsh 下必须红（1）；两种情况都不是 pass。"""

    relaxed = drive_main(tmp_root, monkeypatch, log_real_temp_spill(), require_dsh=False)
    assert relaxed[0] == 0
    assert relaxed[1]["result"] == "skipped", "跳过绝不能被记成 pass"
    assert relaxed[1]["environment_skipped"] is True


# --- 轮 15：诊断字段的脏项 —— URL 形态与普通路径分开解析 ---------------------------------
#
# 真机日志（轮 14 的 block-run.txt）里 profile 根**只**出现在 `file://` 栈帧里。修前
# dsh_home_roots() 把它切成两个畸形候选（`e:///C:/…`：Windows 正则把 `file` 的 `e` 当盘符；
# `/Users/…`：POSIX 正则丢掉盘符），而**正确的根** `C:/…/dsh-home` 反而进不了候选。
# 这不只是好看问题：候选根参与 classify_startup_denial 的 is_under()，根缺失会让本该归因的
# 形态（被拒路径在 $DSH_HOME 下、但不在 /profiles/ 下）归不了因 → 不产生环境跳过。
# 下面的日志全是**合成夹具**（不读 .tmp/，任何 runner 上都能跑）。

FILE_URL_WINDOWS_ROOT = "C:/Users/ZNM/Downloads/Memory/.tmp/round-09/dsh-home"
FILE_URL_WINDOWS_LOCK = (
    "C:\\Users\\ZNM\\Downloads\\Memory\\.tmp\\round-09\\dsh-home\\cache\\headless.lock"
)


def log_file_url_frames_only() -> str:
    """真机同形：profile 根只出现在 file:// 栈帧里，被拒路径只有系统 temp。"""

    return (
        # 与真机第 6 行同形：崩溃原文与被拒路径在**同一行**（真机 6/19/22 三行都是这样）。
        # 拆成两行就归不了因 —— 这正是 N3 那个窗口的边界，别在这里改回去。
        "Error: dsh: plugin tree failed to load: failed to apply loader entry include "
        "(cordis:include): failed to apply loader entry spill-local "
        "(@deepseek-ai/dsh-spill-local): EPERM: operation not permitted, mkdtemp "
        "'C:\\Users\\ZNM\\AppData\\Local\\Temp\\dsh-spill-XXXXXX'\n"
        "    at mkdtempSync (node:fs:3111:18)\n"
        f"    at file:///{FILE_URL_WINDOWS_ROOT}/profiles/headless/#spill-local\n"
        f"    at file:///{FILE_URL_WINDOWS_ROOT}/profiles/headless/#include\n"
    )


def log_home_denied_with_url_only_root() -> str:
    """**合成**夹具：被拒路径在 $DSH_HOME 下、但路径里没有 /profiles/ 段，归因只能靠 URL 里的根。

    这不是真机样本（真机日志的被拒路径是自己被写全的 temp scratch）。它的作用是存在性证明：
    真根一旦缺候选，is_under 就判不出来——判据相邻这件事因此可测（J1）。
    """

    return (
        "Error: dsh: plugin tree failed to load: failed to apply loader entry include\n"
        f"Error: EPERM: operation not permitted, open '{FILE_URL_WINDOWS_LOCK}'\n"
        f"    at file:///{FILE_URL_WINDOWS_ROOT}/profiles/headless/#spill-local\n"
    )


def test_file_url_frames_yield_the_real_home_root_without_scheme_slices():
    """真机形态的正面断言（J1）：正确的根进候选，两条畸形项都不许在；判定本身不变（J2）。"""

    text = log_file_url_frames_only()
    roots = loop.dsh_home_roots(text)
    assert FILE_URL_WINDOWS_ROOT in roots, "file:// 栈帧里的 profile 根必须进候选"
    assert "e:///C:/Users/ZNM/Downloads/Memory/.tmp/round-09/dsh-home" not in roots
    assert "/Users/ZNM/Downloads/Memory/.tmp/round-09/dsh-home" not in roots
    assert not [root for root in roots if "://" in root], "候选里不许留 scheme 残片"
    # J2：真机这一形态的判定是 other_path_denied（被拒路径是系统 temp 的 mkdtemp），
    # 修解析不许把它改成别的 kind、也不许改成 None。
    denial = loop.classify_startup_denial(text)
    assert denial is not None and denial.kind == loop.OTHER_PATH_DENIED


def test_home_root_from_file_url_makes_home_denial_attributable():
    """判定相邻字段的正面断言：根补上之后，这个形态必须判成 profile_write_denied。"""

    denial = loop.classify_startup_denial(log_home_denied_with_url_only_root())
    assert denial is not None, "日志自己给出了 profile 根，这种形态必须能归因"
    assert denial.kind == loop.PROFILE_WRITE_DENIED
    assert denial.path == FILE_URL_WINDOWS_LOCK
    assert FILE_URL_WINDOWS_ROOT in denial.home_roots
    assert [item.root for item in denial.home_root_evidence] == list(denial.home_roots)
    assert loop.HOME_ROOT_SOURCE_FILE_URL in {item.source for item in denial.home_root_evidence}


def test_url_only_root_does_not_launder_unattributable_denial_into_skip():
    """同一个 URL 根：被拒路径既不在 $DSH_HOME 下、也不在启动临时区 → 仍然不许跳过。"""

    text = (
        "Error: dsh: plugin tree failed to load: failed to apply loader entry include\n"
        "Error: EPERM: operation not permitted, unlink 'C:/work/demo-shop/.git/index.lock'\n"
        f"    at file:///{FILE_URL_WINDOWS_ROOT}/profiles/headless/#spill-local\n"
    )
    assert loop.classify_startup_denial(text) is None


def log_boot_crash_and_unrelated_denial_in_separate_records() -> str:
    """N3：崩溃原文在一次尝试里，被拒的 scratch 路径在**另一次**不相关的记录里。

    两次记录之间可以连空行都没有（只有普通行），所以合取的窗口只能小到"同一行"——
    理由写在 classify_startup_denial 的 docstring 里。
    """

    unrelated = str(Path(tempfile.gettempdir()) / "unrelated" / "x.tmp")
    return (
        "== run 1（dsh 启动日志）==\n"
        "Error: dsh: plugin tree failed to load: failed to apply loader entry include\n"
        "dsh exited with code 1\n"
        "== run 2（另一条命令的输出）==\n"
        f"Error: EPERM: operation not permitted, open '{unrelated}'\n"
    )


def log_boot_crash_with_scratch_denial_in_same_block() -> str:
    """对照（N4 形态）：崩溃原文与被拒路径**分处两行**，但同属一个崩溃块（缩进续行）。

    只做行级收窄会在这里丢掉真因——所以窗口必须是"块"（缩进行属于同一记录）。
    """

    scratch = str(Path(tempfile.gettempdir()) / "dsh-spill-XXXXXX")
    return (
        "Error: dsh: plugin tree failed to load: failed to apply loader entry include "
        "(cordis:include)\n"
        "    at applyLoaderEntry (/opt/dsh/lib/index.js:120:11)\n"
        f"  [cause]: EPERM: operation not permitted, mkdtemp '{scratch}'\n"
    )


def test_boot_failure_and_denial_in_different_records_is_not_attributed():
    """N3：整篇日志上的两组判据不许被合起来读——跨记录 → None（不产生环境跳过）。"""

    text = log_boot_crash_and_unrelated_denial_in_separate_records()
    assert loop.denied_paths(text), "夹具本身要真的含被拒路径（否则这条靠空判据就能通过）"
    assert loop.has_dsh_boot_failure(text), "夹具本身要真的含启动崩溃原文"
    assert loop.classify_startup_denial(text) is None


def test_boot_failure_and_denial_in_same_block_is_attributed():
    """对照（N4）：同一个崩溃块（分处两行、缩进续行）→ 仍然 other_path_denied。

    没有这条，N3 那条就可能靠"永远返回 None"通过；只有行级收窄则会在这里丢真因。
    """

    denial = loop.classify_startup_denial(log_boot_crash_with_scratch_denial_in_same_block())
    assert denial is not None and denial.kind == loop.OTHER_PATH_DENIED
    assert "dsh-spill-XXXXXX" in denial.path


def test_crash_blocks_join_indented_continuations_and_stop_at_bare_lines():
    """块规则钉住：缩进续行并入本块；**不缩进**的行（另一条记录 / 普通输出）结束本块。"""

    text = (
        "Error: dsh: plugin tree failed to load: failed to apply loader entry include\n"
        "    at applyLoaderEntry (/opt/dsh/lib/index.js:120:11)\n"
        "  [cause]: EPERM: operation not permitted, mkdtemp 'C:/Temp/dsh-spill-XXXXXX'\n"
        "dsh exited with code 1\n"
        "Error: EPERM: operation not permitted, open 'C:/work/other/x.tmp'\n"
    )
    blocks = loop.crash_blocks(text)
    assert len(blocks) == 1, blocks
    assert "applyLoaderEntry" in blocks[0] and "[cause]" in blocks[0]
    assert "dsh exited with code 1" not in blocks[0], "不缩进的行结束本块"
    assert "other/x.tmp" not in blocks[0], "另一条记录里的被拒路径不许并进本块"


def log_home_denied_with_space_in_home_name() -> str:
    """**合成**夹具：家目录名带空格（`C:/Users/a b/dsh-home`），根只在 %20 的 URL 栈帧里。

    第二个存在性证明：修前 %20 解出的根被"空白不进路径"整条丢掉，is_under 无从判定（判 None）；
    修后根进候选，判定恢复成 profile_write_denied。
    """

    return (
        "Error: dsh: plugin tree failed to load: failed to apply loader entry include\n"
        "Error: EPERM: operation not permitted, open "
        "'C:\\Users\\a b\\dsh-home\\cache\\headless.lock'\n"
        "    at file:///C:/Users/a%20b/dsh-home/profiles/headless/#spill-local\n"
    )


def test_home_root_with_space_in_name_is_attributable():
    """J1：带空格的真根必须进候选并参与 is_under（丢了它这个形态就归不了因）。"""

    denial = loop.classify_startup_denial(log_home_denied_with_space_in_home_name())
    assert denial is not None, "%20 形态的根必须进候选"
    assert denial.kind == loop.PROFILE_WRITE_DENIED
    assert denial.path == "C:\\Users\\a b\\dsh-home\\cache\\headless.lock"
    assert "C:/Users/a b/dsh-home" in denial.home_roots


URL_FORM_CASES = (
    ("windows_drive", "at file:///C:/x/dsh-home/profiles/headless/cordis.yml", "C:/x/dsh-home"),
    ("posix_home", "at file:///home/x/.dsh/profiles/headless/cordis.yml", "/home/x/.dsh"),
    ("localhost", "at file://localhost/home/x/.dsh/profiles/headless/cordis.yml", "/home/x/.dsh"),
    ("remote_host", "at file://fileserver/share/dsh-home/profiles/p/cordis.yml", None),
    ("https_scheme", "at https://example.com/a/dsh-home/profiles/p/cordis.yml", None),
    # 百分号编码（只解一层）。%20 解出的空白是**路径内容**（带空格的家目录真实存在），
    # 因为"含空白"丢掉整个根就是本缺陷要消灭的「真根缺失」，所以 URL 形态必须保住它。
    ("percent_decoded", "at file:///C:/a%2Db/dsh/profiles/p/c.yml", "C:/a-b/dsh"),
    ("percent_space_windows", "at file:///C:/a%20b/dsh/profiles/p/c.yml", "C:/a b/dsh"),
    ("percent_space_posix", "at file:///home/a%20b/.dsh/profiles/p/c.yml", "/home/a b/.dsh"),
    # %2520 只解一层（文件名里真的带 `%20`）；%2F / %5C 是编码的分隔符 → 原样保留，不伪造分隔层
    ("percent_double_encoded", "at file:///C:/a%2520b/dsh/profiles/p/c.yml", "C:/a%20b/dsh"),
    ("percent_separator_slash", "at file:///C:/a%2Fb/dsh/profiles/p/c.yml", "C:/a%2Fb/dsh"),
    ("percent_separator_backslash", "at file:///C:/a%5Cb/dsh/profiles/p/c.yml", "C:/a%5Cb/dsh"),
)


@pytest.mark.parametrize(
    "name,text,expected", URL_FORM_CASES, ids=[case[0] for case in URL_FORM_CASES]
)
def test_url_forms_are_parsed_separately_from_plain_paths(
    name: str, text: str, expected: str | None
):
    """URL 只按 URL 规则解析：本机 file URL 给根，远程主机与非 file scheme 不产根。"""

    filed = [
        item.root
        for item in loop.dsh_home_root_evidence(text)
        if item.source == loop.HOME_ROOT_SOURCE_FILE_URL
    ]
    if expected is None:
        assert filed == [], f"{name}: 不是本机 file URL，不许产出根，实际 {filed}"
        junk = [
            root
            for root in loop.dsh_home_roots(text)
            if "://" in root or "fileserver" in root or "example.com" in root
        ]
        assert junk == [], f"{name}: URL 切片不许当路径，实际 {junk}"
    else:
        assert filed == [expected], f"{name}: 期望 {expected}，实际 {filed}"


def test_home_root_evidence_names_the_source_of_every_root(monkeypatch: pytest.MonkeyPatch):
    """诊断字段要读出「哪个根来自哪条证据」：来源标签 + 原文摘要都必须在。"""

    # DSH_HOME 会与默认值归一化后同键（同一台机器上就是同一个目录），因此这里显式控制环境：
    # 不设 DSH_HOME 时来源里必须出现"平台默认"，设了就必须出现"环境变量"。
    monkeypatch.delenv("DSH_HOME", raising=False)
    evidence = loop.dsh_home_root_evidence("at file:///C:/x/dsh-home/profiles/headless/c.yml\n")
    assert all(item.source and item.evidence for item in evidence), "每条候选根都要带来源与证据"
    assert {item.source for item in evidence} == {
        loop.HOME_ROOT_SOURCE_DEFAULT,
        loop.HOME_ROOT_SOURCE_FILE_URL,
    }
    filed = [item for item in evidence if item.source == loop.HOME_ROOT_SOURCE_FILE_URL]
    assert [item.root for item in filed] == ["C:/x/dsh-home"]
    assert "file:///C:/x/dsh-home/profiles/headless/c.yml" in filed[0].evidence

    monkeypatch.setenv("DSH_HOME", "C:/custom/dsh-home")
    with_env = loop.dsh_home_root_evidence("at file:///C:/x/dsh-home/profiles/headless/c.yml\n")
    env_roots = [item for item in with_env if item.source == loop.HOME_ROOT_SOURCE_ENV]
    assert [item.root for item in env_roots] == ["C:/custom/dsh-home"]

    plain = loop.dsh_home_root_evidence(
        "EPERM: operation not permitted, open 'C:\\Users\\x\\.dsh\\profiles\\headless\\c.yml'\n"
    )
    plain_roots = [item for item in plain if item.source == loop.HOME_ROOT_SOURCE_LOG_PATH]
    assert [item.root for item in plain_roots] == ["C:\\Users\\x\\.dsh"]
    assert "profiles" in plain_roots[0].evidence, "证据要能指回原文那一行"


@pytest.mark.parametrize(
    "candidate,allow_whitespace,plausible",
    (
        ("C:/Users/x/dsh-home", False, True),
        ("/home/x/.dsh", False, True),
        ("e:///C:/Users/x/dsh-home", False, False),
        ("s://host/x", False, False),
        ("C:/x/a:b/dsh-home", False, False),
        ("C:/x/y z", False, False),  # 普通扫描：空白是边界，切进来就是切错了
        ("C:", False, False),
        ("C:/x/y z", True, True),  # URL 形态：边界由 URL 语法给出，空格是路径内容
        ("/home/a b/.dsh", True, True),
        ("C:/x/y\tz", True, False),  # 控制字符：任何来源都丢
        ('C:/x/y"z', True, False),  # 引号：结构性字符，任何来源都丢
        ("C:/x/y(z)", True, False),  # 括号同理
    ),
)
def test_plausible_home_root_drops_documented_malformed_forms(
    candidate: str, allow_whitespace: bool, plausible: bool
):
    """丢弃规则逐条钉住：正常路径不许误丢；空白按来源分档；结构性字符任何来源都丢。"""

    assert loop._plausible_home_root(candidate, allow_whitespace=allow_whitespace) is plausible


def test_url_slice_starting_before_the_url_is_dropped_too():
    """普通扫描从 URL 之前开始的切片（带 scheme 残片）同样是畸形项：丢，正确的根仍在。"""

    text = (
        "EPERM: operation not permitted, open "
        "'C:/a/file:///C:/Users/x/dsh-home/profiles/headless/cordis.yml'\n"
    )
    roots = loop.dsh_home_roots(text)
    assert "C:/Users/x/dsh-home" in roots
    assert not [root for root in roots if "://" in root or root.startswith("C:/a")]


def test_url_authority_port_slice_is_not_taken_as_a_plain_path():
    """URL 的 authority 带端口时（`:8080/`），普通扫描会从端口后切出 `/a/dsh-home`——必须丢掉。

    这条专门钉住"URL 区间内的匹配不参与普通扫描"：端口让最左的 POSIX 匹配落在 URL 中间，
    而它既不以 `:` 结尾也不带 `://`，只有区间规则拦得住。
    """

    text = "at http://fileserver:8080/a/dsh-home/profiles/headless/cordis.yml\n"
    logged = [
        item.root for item in loop.dsh_home_root_evidence(text) if item.source.startswith("log:")
    ]
    assert logged == [], f"URL 切片不许当路径，实际 {logged}"


def test_scheme_slash_form_does_not_leave_a_missing_drive_fragment():
    """单斜杠 `file:/C:/…` 不产畸形候选：丢盘符的 POSIX 片段与 `e:/C:` 切片都不许在。"""

    roots = loop.dsh_home_roots("at file:/C:/Users/x/dsh-home/profiles/headless/c.yml\n")
    assert not [root for root in roots if root.startswith("/Users/")], roots
    assert not [root for root in roots if root.startswith("e:/")], roots


def test_plain_candidate_with_colon_body_is_dropped():
    """路径体里的冒号（不是盘符位）是非法形态：不许进候选，也不许被当成根。"""

    text = "EPERM: operation not permitted, open 'C:/x/a:b/dsh-home/profiles/headless/c.yml'\n"
    logged = [
        item.root for item in loop.dsh_home_root_evidence(text) if item.source.startswith("log:")
    ]
    assert logged == [], f"非法形态不许进候选，实际 {logged}"


def test_main_reports_home_root_evidence_in_payload(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """诊断字段进载荷：roots 与 evidence 同序同集合，且每条证据写明来源。"""

    code, payload = drive_main(
        tmp_root, monkeypatch, log_home_denied_with_url_only_root(), require_dsh=False
    )
    assert code == 0, "环境跳过默认不红；这里断言的是载荷字段，不是退出码语义"
    assert payload["dsh_startup_denied_kind"] == loop.PROFILE_WRITE_DENIED
    evidence = payload["dsh_startup_denied_home_root_evidence"]
    assert [item["root"] for item in evidence] == payload["dsh_startup_denied_home_roots"]
    assert any(item["source"] == loop.HOME_ROOT_SOURCE_FILE_URL for item in evidence)
    assert all(item["evidence"] for item in evidence)

# --- 轮 15：Hook 起不来的两类原因（Q6 修复之后的接口收口） -------------------------------
#
# 插件侧把"Hook 起不来"的理由写全了：`policy-hook: Hook 无法执行（…）`，其中
# 「工作目录不存在：<目录>（来自 config.projectDir）」只在 projectDir 不可用时出现，
# 而沙箱拒绝出现在 `spawn 报错：spawn EPERM`。本脚本必须把两者分开：
# 工作目录不可用是**接线/配置**错误（按真失败收场），只有沙箱禁管道 stdio 才是环境跳过。

def log_hook_workdir_missing() -> str:
    """projectDir 指向不存在的目录时的真机理由形态（task-1 修后的措辞）。"""

    return (
        "policy-hook: Hook 无法执行（工作目录不存在：C:\\gone\\demo-shop"
        "（来自 config.projectDir）；要启动的命令：python -m adapters.dsh.hooks；"
        "Node 的 spawn 在 cwd 不存在时会把 ENOENT 归给可执行文件；"
        "要改的是这个目录），按失败关闭拒绝该工具调用\n"
    )


def log_hook_workdir_is_not_a_directory() -> str:
    """同类的第二种形态：projectDir 指向的不是目录。"""

    return (
        "policy-hook: Hook 无法执行（工作目录不是目录：C:/repo/AGENTS.md"
        "（来自 config.projectDir）；要启动的命令：python -m adapters.dsh.hooks），"
        "按失败关闭拒绝该工具调用\n"
    )


def log_hook_spawn_eperm_sandbox() -> str:
    """真 sandbox 形态：目录已确认存在，`spawn 报错：spawn EPERM` 才是原因。"""

    return (
        "policy-hook: Hook 无法执行（工作目录已确认存在：C:/work/demo-shop"
        "（来自 config.projectDir）；要启动的命令：python -m adapters.dsh.hooks；"
        "spawn 报错：spawn EPERM；问题不在目录这一侧），按失败关闭拒绝该工具调用\n"
    )


def log_hook_eperm_on_unrelated_line() -> str:
    """**无关行**出现 `spawn EPERM`，理由那行说的是工作目录不存在。

    两件事都发生了，但它们不是因果：必须归**工作目录类**（真失败），不许读成沙箱（假的环境跳过）。
    """

    return (
        "[agent] 我试了一下 bash：EPERM: operation not permitted, spawn EPERM\n"
        "policy-hook: Hook 无法执行（工作目录不存在：C:\\gone\\demo-shop"
        "（来自 config.projectDir）；要启动的命令：python -m adapters.dsh.hooks），"
        "按失败关闭拒绝该工具调用\n"
    )


def log_hook_sandbox_reason_after_bare_eperm() -> str:
    """真沙箱理由（同一行里既有前缀又有 `spawn 报错：spawn EPERM`），前面还有一行裸 EPERM。

    判定与**证据**都必须是同一行的那条理由，不能取"随便一行里的 spawn EPERM"。
    """

    return (
        "bash: spawn EPERM: operation not permitted\n"
        "policy-hook: Hook 无法执行（工作目录已确认存在：C:/work/demo-shop"
        "（来自 config.projectDir）；要启动的命令：python -m adapters.dsh.hooks；"
        "spawn 报错：spawn EPERM），按失败关闭拒绝该工具调用\n"
    )


def log_bare_spawn_eperm_without_hook_failure() -> str:
    """**完全裸**的 `spawn EPERM`（没有 `Hook 无法执行`）：不是"Hook 起不来"的证据。"""

    return "bash: spawn EPERM: operation not permitted\n"


def log_hook_spawn_enoent_no_cause() -> str:
    """Q6 修前的真机原文：只说 ENOENT，读不出原因 → 不许猜，也不许环境跳过。"""

    return (
        "policy-hook: Hook 无法执行（spawn C:\\Program Files\\nodejs\\node.exe ENOENT），"
        "按失败关闭拒绝该工具调用\n"
    )


# 期望值写成 wire 字符串（载荷里出现的就是它们），这样即使驱动的是"修前模块"，
# 收集期也不会因为常量不存在而整份文件收集失败——红必须是"这条用例红"。
HOOK_FAILURE_LINE = "Hook 无法执行"

HOOK_FAILURE_CASES = (
    ("workdir_missing", log_hook_workdir_missing(), "hook_workdir_unusable"),
    ("workdir_not_a_directory", log_hook_workdir_is_not_a_directory(), "hook_workdir_unusable"),
    ("sandbox_spawn_eperm", log_hook_spawn_eperm_sandbox(), "sandbox_pipe_stdio_denied"),
    ("legacy_spawn_eperm", log_hook_spawn_eperm(), "sandbox_pipe_stdio_denied"),
    (
        "sandbox_reason_after_bare_eperm",
        log_hook_sandbox_reason_after_bare_eperm(),
        "sandbox_pipe_stdio_denied",
    ),
    ("eperm_on_unrelated_line", log_hook_eperm_on_unrelated_line(), "hook_workdir_unusable"),
    ("enoent_without_cause", log_hook_spawn_enoent_no_cause(), None),
)


def test_hook_failure_kind_values_are_the_payload_contract():
    """载荷里写的 kind 字符串就是契约：常量值与它不许各说各的。"""

    assert loop.HOOK_WORKDIR_UNUSABLE == "hook_workdir_unusable"
    assert loop.SANDBOX_PIPE_STDIO_DENIED == "sandbox_pipe_stdio_denied"
    assert loop.HOOK_SPAWN_UNATTRIBUTABLE == "hook_spawn_unattributable"


@pytest.mark.parametrize(
    "name,text,expected", HOOK_FAILURE_CASES, ids=[case[0] for case in HOOK_FAILURE_CASES]
)
def test_hook_failure_kind_separates_workdir_from_sandbox(
    name: str, text: str, expected: str | None, tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """两类原因各归各的；读不出原因时不许归因（但"起不来"这件事仍然成立）。"""

    logs = tmp_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(loop, "LOGS", logs)
    (logs / "block-run.txt").write_text(text, encoding="utf-8")

    assert loop.hook_failure_seen() is True
    assert loop.hook_could_not_spawn() is True
    failure = loop.hook_spawn_failure()
    if expected is None:
        assert failure is None, f"{name}: 读不出原因就不许归因，实际 {failure.kind}"
        return
    assert failure is not None, f"{name}: 应该判成 {expected}"
    assert failure.kind == expected
    assert failure.evidence, "归因必须带原文证据"
    if expected == "sandbox_pipe_stdio_denied":
        # 同一行要求：证据那行必须**两个标记都在**（"另一行的 spawn EPERM"不算）
        assert HOOK_FAILURE_LINE in failure.evidence, f"{name}: 证据必须是 Hook 失败那一行"
        assert "spawn EPERM" in failure.evidence, f"{name}: 证据行里要有沙箱标记"
    if expected == loop.HOOK_WORKDIR_UNUSABLE:
        assert "工作目录" not in (failure.workdir or ""), f"{name}: 取到的是目录本身"
        assert failure.workdir


def test_bare_spawn_eperm_without_hook_failure_is_not_a_hook_denial(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """(c) 完全裸的 `spawn EPERM`：没有 `Hook 无法执行` 就不是"Hook 起不来"的证据 → 真失败。"""

    logs = tmp_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(loop, "LOGS", logs)
    (logs / "block-run.txt").write_text(
        log_bare_spawn_eperm_without_hook_failure(), encoding="utf-8"
    )
    assert loop.hook_failure_seen() is False
    assert loop.hook_spawn_failure() is None, "没有 Hook 失败原文就不许归因，更不许说成沙箱"

    code, payload = drive_main(
        tmp_root, monkeypatch, log_bare_spawn_eperm_without_hook_failure(), require_dsh=False
    )
    assert code == 1, "裸 EPERM 不是环境限制：按真失败收场"
    assert payload["result"] == "fail"
    assert payload["environment_skipped"] is False
    assert payload.get("hook_spawn_denied_kind") is None


def test_main_does_not_launder_missing_hook_workdir_into_skip(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """工作目录配错 → 真失败（不是环境跳过）；理由要说清改哪里，且不许提沙箱。"""

    code, payload = drive_main(
        tmp_root, monkeypatch, log_hook_workdir_missing(), require_dsh=False
    )
    assert code == 1, "接线/配置错误不许按环境跳过收场（给不给 --require-dsh 都是失败）"
    assert payload["result"] == "fail"
    assert payload["environment_skipped"] is False
    assert payload.get("sandbox_blocked_spawn") is None
    assert payload["hook_spawn_denied_kind"] == loop.HOOK_WORKDIR_UNUSABLE
    assert payload["hook_spawn_denied_workdir"] == "C:\\gone\\demo-shop"
    assert "工作目录不可用" in payload["reason"]
    # 判据是**这句话有没有把沙箱当成原因**，不是"字面上不许出现沙箱三个字"：
    # 理由里显式否掉沙箱归因是对的（两类要区分开），但不能出现跳过分支那句因果断言。
    assert "原因**不是**沙箱" in payload["reason"], "理由必须先否掉沙箱归因"
    assert "受限沙箱禁止管道 stdio，而 dsh 的 ctx.shell" not in payload["reason"]
    assert "projectDir" in payload["reason"], "拒绝理由必须说清改成什么形态就能过"


def test_main_still_skips_when_sandbox_denied_the_spawn(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """真 spawn EPERM 仍然按环境跳过（上一处的收窄不许把这既有语义带坏）。"""

    code, payload = drive_main(
        tmp_root, monkeypatch, log_hook_spawn_eperm_sandbox(), require_dsh=False
    )
    assert code == 0
    assert payload["result"] == "skipped"
    assert payload["environment_skipped"] is True
    assert payload["sandbox_blocked_spawn"] is True
    assert payload["hook_spawn_denied_kind"] == loop.SANDBOX_PIPE_STDIO_DENIED
    strict = drive_main(tmp_root, monkeypatch, log_hook_spawn_eperm_sandbox(), require_dsh=True)
    assert strict[0] == 1, "--require-dsh 下环境跳过仍然失败关闭"


def test_main_does_not_launder_unattributable_hook_failure_into_skip(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """Q6 修前的真机原文（只有 ENOENT、读不出原因）→ 真失败，并写明"读不出原因"。"""

    code, payload = drive_main(
        tmp_root, monkeypatch, log_hook_spawn_enoent_no_cause(), require_dsh=False
    )
    assert code == 1
    assert payload["result"] == "fail"
    assert payload["environment_skipped"] is False
    assert payload["hook_spawn_denied_kind"] == loop.HOOK_SPAWN_UNATTRIBUTABLE
    assert "读不出原因" in payload["diagnosis"]
    assert "读不出原因" in payload["reason"]
    # 读不出原因时不许给出沙箱那一类的因果断言
    assert "受限沙箱禁止管道 stdio，而 dsh 的 ctx.shell" not in payload["reason"]
