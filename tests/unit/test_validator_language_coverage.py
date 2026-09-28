"""P2：不受验证器覆盖的语言必须是**显式声明**，并产出显式判定（07 号报告 §4 P2）。

缺陷现场（07 号报告 §3.4）：`validation/validators.yaml` 只有 python 的 rule pack，
受控项目的 Adapter 把 `.md` 声明成 `default_language: text`，于是**任何** `.md` 写入都在
取证路径上得到 `RegistryError: 上下文声明的语言 text 没有任何 rule pack` →
`evidence_unavailable` → 退出码 2：任务书里改 README 那一条因此没能完成。

失败关闭本身没错（AGENTS 第 20/42 条），错的是**没有表达"哪些语言按设计不取证"的地方**。
本文件把边界钉成三条，三条都必须同时成立：

- 语言**有** rule pack → `covered_by_rule_pack`（现状行为不变）；
- 语言**没有** rule pack、但在 `uncovered_languages` 里 → `not_covered_by_design`：
  显式判定，既不是错误、也不是静默放行；同一批里**有规则需要 checker 证据**时仍然阻断；
- 语言没有 rule pack、也不在清单里 → **保持** `RegistryError`（退出码 2），不许被顺带放行。

为什么把"不取证"写成数据而不是代码分支：AGENTS 核心约束 2 / 21（规则与注册表都是数据）、
第 40 条（"看起来在管、实际什么都没查"是最坏的形态）。一条 `uncovered_languages` 记录
必须带可被评审的 reason，评审的对象是"平台为什么不验证这门语言"，不是某个 if 分支。
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
import yaml

from conftest import (
    POLICIES_DIR,
    REPO_ROOT,
    VALIDATION_DIR,
    make_checker_rule,
    make_context,
    validators_config,
)
from policy.check import EXIT_ALLOWED
from policy.engine import evaluate
from policy.loader import load_rule_set
from policy.models import Decision, RuleSet, Severity
from validators.pipeline import PipelineRequest, run_pipeline
from validators.registry import RegistryError

CONFIG = validators_config()
RULES = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)

# 07 号报告 P2 的现场就是它：受控项目里被声明为 text 的那一类目标。
DOC_TARGET = "README.md"
DECLARED_IN = "validation/validators.yaml"


def run_for_language(
    *,
    language: str,
    rules: RuleSet = RULES,
    target: str = DOC_TARGET,
    config=CONFIG,
):
    """按给定语言跑一次真实流水线（只读配置，不写任何东西）。"""

    context = make_context(file=target, language=language, layer="unknown")
    return run_pipeline(
        PipelineRequest(target=target, workspace=REPO_ROOT, context=context, rules=rules),
        config=config,
    )


def registry_document() -> dict:
    return yaml.safe_load((VALIDATION_DIR / "validators.yaml").read_text(encoding="utf-8"))


# --------------------------------------------------- 1. 声明不取证的语言：显式判定，不是错误


def test_a_language_declared_uncovered_is_an_explicit_judgement() -> None:
    """红→绿的主证据：修复前这里是 RegistryError「没有任何 rule pack」。"""

    report = run_for_language(language="text")

    coverage = report.language_coverage
    assert coverage["language"] == "text"
    assert coverage["status"] == "not_covered_by_design"
    assert coverage["declared_in"] == DECLARED_IN
    # reason 必须来自清单、必须能被人评审：空理由等于把"为什么不查"重新变成不可读
    declaration = CONFIG.registry.uncovered("text")
    assert declaration is not None
    assert coverage["reason"] == declaration.reason
    assert "rule pack" in coverage["reason"]
    assert "不取证" in coverage["reason"]

    # 没有验证器真的服务过：这条口径与 P7 的 declared_checkers 是两件事
    assert report.served_checkers == ()
    # 也没有任何阻断点：语言按设计不取证不是失败
    assert report.blockers == ()
    assert report.checks == ()

    # 审计读得到：pre_evidence 摘要的 passthrough 直接取这一项（字段名与形状是接口）
    assert report.to_payload()["language_coverage"] == dict(coverage)

    # 判定仍然由引擎做：没有规则适用于 text，于是 allow；而且"没有规则适用"是**显式**的
    context = make_context(file=DOC_TARGET, language="text", layer="unknown")
    result = evaluate(RULES, context, evidence=report.bundle)
    assert result.decision is Decision.ALLOW
    assert len(result.skipped_rules) == len(RULES.rules)


def test_a_language_with_a_rule_pack_says_so() -> None:
    """有 rule pack 的语言必须给出同一字段的另一半口径，而不是留空。"""

    report = run_for_language(language="python", target="src/policy/evidence.py")

    assert report.language_coverage == {
        "language": "python",
        "status": "covered_by_rule_pack",
        "reason": "",
        "declared_in": DECLARED_IN,
    }


# ------------------------------------------- 2. 没有声明的语言：保持失败关闭（不许顺带放行）


def test_an_undeclared_language_still_fails_closed() -> None:
    """既没有 rule pack、也没声明不取证 → RegistryError；理由必须指向缺的那份声明。"""

    with pytest.raises(RegistryError) as error:
        run_for_language(language="go")

    message = str(error.value)
    assert "go" in message
    assert "rule pack" in message
    # 修复前这句话不存在：调用方看不出"缺的是一个可声明的清单"
    assert "uncovered_languages" in message
    assert DECLARED_IN in message


# ------------------------------------- 3. 声明不取证但本次有规则需要证据：仍然失败关闭


def test_a_declared_uncovered_language_with_needed_checkers_is_blocked() -> None:
    """放宽的只是"没有规则需要证据"那一格；有需要就必须阻断，绝不放行。"""

    rule = make_checker_rule("DOC-900", checker="missing_docstring", scope={"language": "text"})
    rules = RuleSet(rules=(rule,), source_paths=("policies/coding/DOC-900.yaml",))

    report = run_for_language(language="text", rules=rules)

    assert report.language_coverage["status"] == "not_covered_by_design"
    assert report.served_checkers == ()
    assert [blocker.checkers for blocker in report.blockers] == [("missing_docstring",)]
    reason = report.blockers[0].reason
    assert "按声明不取证" in reason
    assert "missing_docstring" in reason

    context = make_context(file=DOC_TARGET, language="text", layer="unknown")
    result = evaluate(rules, context, evidence=report.bundle)
    assert result.decision is Decision.BLOCK
    assert result.violations[0].severity is Severity.CRITICAL
    assert "没有验证器为 checker" in result.violations[0].message or "关键验证器" in (
        result.violations[0].message
    )


# ------------------------------------------------------------------ 4. 端到端：policy.check


def test_policy_check_no_longer_dies_on_a_markdown_target() -> None:
    """07 号报告里模型真的走到的那条路：`policy.check <某 .md> --language text`。"""

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "policy.check",
            DOC_TARGET,
            "--language",
            "text",
            "--config-root",
            str(REPO_ROOT),
            "--request-id",
            "req-p2-md",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    combined = completed.stdout + completed.stderr
    # 修复前：config error + 退出码 2（RegistryError 从 _select_specs 抛出）
    assert "没有任何 rule pack" not in combined
    assert completed.returncode == EXIT_ALLOWED, combined
    assert "text" in completed.stdout
    assert "not_covered_by_design" in completed.stdout


def test_the_declaration_is_data_not_a_code_branch() -> None:
    """清单本身在数据文件里，且每一项都带 language 与非空 reason。"""

    document = registry_document()

    entries = document["uncovered_languages"]
    assert [entry["language"] for entry in entries] == ["text"]
    for entry in entries:
        assert set(entry) == {"language", "reason"}
        assert entry["reason"].strip()
    # 本轮只声明 text：多一条就是多一份没被评审过的"不取证"
    assert CONFIG.registry.uncovered("python") is None
