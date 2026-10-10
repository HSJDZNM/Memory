r"""tools/dsh_bridge.py：接线是**字节级**操作，也是**跨进程**操作——两条都要钉住。

两条回归都来自本工具落地时真的踩到的坑（不写下来就会再踩一次）：

1. render_hook_command 的 $env:PYTHONPATH 必须指向**平台自己**的 src/，不是受治项目的
   src/。指错时 Hook 以 No module named adapters 结束，而"起不来"在 dsh 侧等于**放行**——
   这正是 hook.self_check 那条事实存在的理由，它在本工具的第一版里真的挡下过一次；
2. probe_fact 必须给命令补 --self-check。不补的话 Hook 把空 stdin 读成 null 载荷、
   以 context_error 退出 2，探针永远红："能失败的检查"变成"永远失败的检查"。

临时目录用仓库自带的 tmp_root 夹具而**不用** pytest 的 tmp_path：conftest 里那句
"刻意不用 pytest 的 tmp_path"写的就是这件事——tmp_path 走 mkdtemp + chmod，
受限沙箱里那条 chmod 会让目录后续连 listdir 都被拒绝（实测 WinError 5），
于是用例会因为与被测行为无关的权限错误变红。

第三条边界是**写下来的**，不是漏下来的：文件不以换行结尾时，安装会补一个换行
（否则标记块会粘在上一行上），撤回后因此多一个换行——这是唯一一处不是逐字节还原的地方，
由 test_files_without_trailing_newline_are_documented_boundary 显式钉住。
"""

from __future__ import annotations

from pathlib import Path

import dsh_bridge as bridge
import pytest

PLUGIN = Path("src/adapters/dsh/policy-hook.plugin.mjs")


def block(command: str = "py -m adapters.dsh.hooks --config .policy/x.yaml") -> str:
    return bridge.render_patch_block(plugin=PLUGIN, command=command, project=Path("C:/gov"))


def test_hook_command_points_pythonpath_at_the_platform_src():
    """回归 1：PYTHONPATH 是**平台**的 src，不是受治项目的 src。"""

    command = bridge.render_hook_command(
        python="C:/py/python.exe", config=".policy/dsh-adapter.yaml", hooks_config=".policy/hooks.json"
    )
    platform_src = bridge.REPO_ROOT / "src"
    assert platform_src.as_posix() in command
    assert "adapters.dsh.hooks" in command
    assert command.index(platform_src.as_posix()) < command.index("adapters.dsh.hooks")


def test_probe_appends_self_check_and_exit_code(monkeypatch: pytest.MonkeyPatch):
    """回归 2：探针必须走 --self-check，并补 exit $LASTEXITCODE（5.1 会压掉退出码）。"""

    seen: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, **kwargs):  # noqa: ANN001, ANN003 - 只关心 argv
        seen.append(list(argv))
        return Completed()

    monkeypatch.setattr(bridge, "shell_argv", lambda: ["powershell", "-Command"])
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)

    fact = bridge.probe_fact("py -m adapters.dsh.hooks --config .policy/x.yaml", project=Path("."))
    assert fact.status == bridge.PASS
    assert len(seen) == 1
    tail = seen[0][-1]
    assert "--self-check" in tail
    assert tail.endswith("exit $LASTEXITCODE")


def test_probe_without_a_shell_is_unavailable_not_pass(monkeypatch: pytest.MonkeyPatch):
    """没有 shell 时是 unavailable（不是通过）："没读到"与"读到了且对"必须能分开。"""

    monkeypatch.setattr(bridge, "shell_argv", lambda: None)
    fact = bridge.probe_fact("py -m adapters.dsh.hooks", project=Path("."))
    assert fact.status == bridge.UNAVAILABLE


@pytest.mark.parametrize(
    "text",
    [
        "# header\n- id: a\n",
        "# header\n- id: a\n\n\n",
        "# header\r\n- id: a\r\n",
        "",
    ],
)
def test_round_trip_restores_bytes_exactly(text: str):
    """装完再撤，文件逐字节回到原样——末尾空行属于原文，不属于我们写的那一段。"""

    assert bridge.remove_block(bridge.apply_block(text, block())) == text


def test_install_is_idempotent():
    """重复安装是整段替换，不是越贴越多。"""

    once = bridge.apply_block("# header\n", block())
    twice = bridge.apply_block(once, block())
    assert once == twice
    assert once.count(bridge.MARKER_BEGIN) == 1
    assert once.count(bridge.MARKER_END) == 1


def test_install_keeps_other_entries_untouched():
    """桌面 profile 的 patch 里有别人的条目（含 !!js 标签）——它们必须一个字节都不动。"""

    original = "# layer\n- id: ui-chat\n  disabled: !!js process.platform === 'win32'\n"
    updated = bridge.apply_block(original, block())
    assert updated.startswith(original.rstrip("\n"))
    assert bridge.remove_block(updated) == original


def test_torn_markers_are_a_configuration_error():
    """只有一个标记 = 残缺：宁可不猜要删哪一段（两个方向都要报错）。"""

    torn = bridge.MARKER_BEGIN + "\n- insert: []\n"
    with pytest.raises(ValueError):
        bridge.apply_block(torn, block())
    with pytest.raises(ValueError):
        bridge.remove_block(torn)


def test_files_without_trailing_newline_are_documented_boundary():
    """写下来的边界：补的那个换行在撤回后留下——唯一一处非逐字节还原。"""

    assert bridge.remove_block(bridge.apply_block("# header", block())) == "# header\n"


def test_block_is_parseable_and_found_by_id():
    text = bridge.apply_block("# header\n", block())
    state, entry, reason = bridge.load_block_entry(text)
    assert (state, reason) == ("present", "")
    assert entry is not None and entry["id"] == bridge.ENTRY_ID
    assert "adapters.dsh.hooks" in bridge.command_of(entry)


def test_missing_and_unparsable_states_are_distinguishable():
    assert bridge.load_block_entry("# nothing\n")[0] == "missing"
    broken = bridge.MARKER_BEGIN + "\n- insert: {\n" + bridge.MARKER_END + "\n"
    assert bridge.load_block_entry(broken)[0] == "unparsable"


def test_command_with_double_quote_is_refused():
    """命令里出现双引号时不拼一个自己读不准的 YAML 标量，直接报错。"""

    with pytest.raises(ValueError):
        bridge.render_patch_block(plugin=PLUGIN, command='py -c "x"', project=Path("C:/gov"))


def test_collect_facts_fails_when_block_missing(tmp_root: Path):
    """没装过就是 fail（不是 unavailable），而且报告里能逐条读出来。"""

    profile = tmp_root / "profiles" / "desktop"
    profile.mkdir(parents=True)
    patch = profile / "cordis.patch.yml"
    patch.write_text("# empty layer\n", encoding="utf-8")
    facts = bridge.collect_facts(
        profile_dir=profile,
        patch_path=patch,
        config_path=tmp_root / ".policy" / "dsh-adapter.yaml",
        hooks_path=tmp_root / ".policy" / "hooks.json",
        project=tmp_root,
    )
    statuses = {fact.name: fact.status for fact in facts}
    assert statuses["profile.exists"] == bridge.PASS
    assert statuses["patch.block"] == bridge.FAIL
    assert bridge.overall(facts) == "fail"


def test_collect_facts_stops_at_a_missing_profile(tmp_root: Path):
    """profile 不存在是第一条事实的失败——后面的事实没有被读到，不是"通过"。"""

    facts = bridge.collect_facts(
        profile_dir=tmp_root / "nope",
        patch_path=tmp_root / "nope" / "cordis.patch.yml",
        config_path=tmp_root / ".policy" / "dsh-adapter.yaml",
        hooks_path=tmp_root / ".policy" / "hooks.json",
        project=tmp_root,
    )
    assert [fact.name for fact in facts] == ["profile.exists"]
    assert bridge.overall(facts) == "fail"


def test_main_scaffold_then_install_writes_one_block(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """整条路径（scaffold → install → check）在真文件系统上走一遍（探针与核心层注入）。"""

    dsh_home = tmp_root / "dsh-home"
    profile = dsh_home / "profiles" / "desktop"
    profile.mkdir(parents=True)
    (profile / "cordis.patch.yml").write_text("# layer\n", encoding="utf-8")
    project = tmp_root / "project"
    project.mkdir()

    injected = [
        bridge.Fact("adapter.config", bridge.PASS, "注入"),
        bridge.Fact("hooks.config", bridge.PASS, "注入"),
        bridge.Fact("wiring.budget", bridge.PASS, "注入"),
    ]
    monkeypatch.setattr(bridge, "config_facts", lambda config, hooks: list(injected))
    monkeypatch.setattr(
        bridge, "probe_fact", lambda command, project: bridge.Fact("hook.self_check", bridge.PASS, "注入")
    )
    common = ["--dsh-home", str(dsh_home), "--profile", "desktop", "--project", str(project)]

    assert bridge.main(["--scaffold", *common]) == 0
    assert (project / ".policy" / "dsh-adapter.yaml").is_file()
    assert (project / ".policy" / "hooks.json").is_file()

    assert bridge.main(["--install", *common]) == 0
    assert bridge.main(["--check", *common]) == 0
    text = (profile / "cordis.patch.yml").read_text(encoding="utf-8")
    assert text.count(bridge.MARKER_BEGIN) == 1

    assert bridge.main(["--uninstall", *common]) == 0
    assert bridge.MARKER_BEGIN not in (profile / "cordis.patch.yml").read_text(encoding="utf-8")
    capsys.readouterr()


def test_main_refuses_install_without_project_config(
    tmp_root: Path, capsys: pytest.CaptureFixture[str]
):
    """受治项目还没有配置时是**用法错误 2**（并告诉人先跑 --scaffold），不是静默装一个空壳。"""

    dsh_home = tmp_root / "dsh-home"
    profile = dsh_home / "profiles" / "desktop"
    profile.mkdir(parents=True)
    (profile / "cordis.patch.yml").write_text("# layer\n", encoding="utf-8")
    project = tmp_root / "project"
    project.mkdir()
    code = bridge.main(
        [
            "--install",
            "--dsh-home",
            str(dsh_home),
            "--profile",
            "desktop",
            "--project",
            str(project),
        ]
    )
    assert code == 2
    assert "--scaffold" in capsys.readouterr().err


def test_main_unknown_profile_is_a_usage_error(tmp_root: Path, capsys: pytest.CaptureFixture[str]):
    code = bridge.main(["--check", "--dsh-home", str(tmp_root), "--profile", "nope"])
    assert code == 2
    assert "profile 不存在" in capsys.readouterr().err
