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
