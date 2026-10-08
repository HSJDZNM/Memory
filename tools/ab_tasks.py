"""AB-4 任务集获取与本地可运行化：把「用仓库自带测试判成败」从设计变成可执行。

职责边界（本模块**只做取用与可运行化**，不做判定、不算质量分）：
  * 取任务元数据（HF datasets-server，不依赖 pip / datasets 库）；
  * 钉死 revision：数据集 sha + 逐文件 sha256 → evaluation/ab/tasks.lock.json；
  * 取**基线树**（pre-fix）：上游仓库 base_commit 的 codeload tarball，剥掉顶层目录落到 out_root；
  * 产出 **oracle.json**：外部 oracle = 仓库自带测试（FAIL_TO_PASS / PASS_TO_PASS），不是平台 Decision；
  * 分类拒收：跑不动的任务写 needs_install / environment_unavailable / rejected + status_reason，**不许静默跳过**。

命令行：
    python tools/ab_tasks.py --list
    python tools/ab_tasks.py --fetch swe-bench-verified [--root .tmp/ab-tasks]
    python tools/ab_tasks.py --oracle <instance_id> [--json]
    python tools/ab_tasks.py --baseline <instance_id> [--apply-test-patch] [--json]
    python tools/ab_tasks.py --probe <instance_id> [--json]      # 实测能不能跑（collect-only）
    python tools/ab_tasks.py --run-oracle <instance_id> --phase baseline|fixed [--json]
    python tools/ab_tasks.py --verify [--json]
    python tools/ab_tasks.py --record-lock

两条纪律：
  1. 仪器独立：本模块**不**读 policies/**，也**不**用 validation/ruff.toml；它只回答"这个任务的外部判据是什么、跑不跑得动"。
  2. 缺东西写 unavailable + reason：装不上、网络不通、上游漂移，都逐条写出来，不写 0、不猜。
"""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

TASKS_SCHEMA_VERSION = "1"
ORACLE_SCHEMA_VERSION = "1"

DEFAULT_ROOT = Path(".tmp/ab-tasks")
LOCK_PATH = Path("evaluation/ab/tasks.lock.json")
ROWS_ENDPOINT = "https://datasets-server.huggingface.co/rows"
PAGE_SIZE = 100

# 本机实测（2026-10-07）：这是唯一能跑的本机解释器；.venv 缺依赖且装不进去。
# 写进 oracle.json 的 python 必须显式给出——相对路径会在错误的树上跑。
DEFAULT_PYTHON = sys.executable


@dataclass(frozen=True)
class TaskSource:
    id: str
    kind: str          # hf-rows | git
    url: str
    revision: str      # HF dataset sha / commit sha（钉死）
    license: str
    license_source: str
    gated: bool
    expected_rows: int
    note: str
    # hf-rows 专用：datasets-server 的三段坐标。dataset 名从 url 里取（见 _hf_dataset_id），
    # 这里只声明 config / split——曾经它们在请求里写死成 SWE-bench 的值，而目录、锁记录、
    # rows_path 都按 dataset_id 键控：再加一个 hf-rows 源就会静默取错数据集。
    hf_config: str = "default"
    hf_split: str = "test"


SOURCES: dict[str, TaskSource] = {
    "swe-bench-verified": TaskSource(
        id="swe-bench-verified",
        kind="hf-rows",
        url="https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified",
        revision="c104f840cc67f8b6eec6f759ebc8b2693d585d4a",
        license="MIT（上游仓库 princeton-nlp/SWE-bench 的 LICENSE；**数据集卡本身没有 license 标签**）",
        license_source=(
            "gh api repos/princeton-nlp/SWE-bench --jq .license.spdx_id -> MIT；"
            "huggingface.co/api/datasets/princeton-nlp/SWE-bench_Verified 的 tags 里**没有** license:*，"
            "gated=false [2026-10-07]"
        ),
        gated=False,
        expected_rows=500,
        note="500 条人核验子集；12 个仓库；字段含 base_commit / patch / test_patch / FAIL_TO_PASS / PASS_TO_PASS",
        hf_config="default",
        hf_split="test",
    ),
    "bugs-in-py": TaskSource(
        id="bugs-in-py",
        kind="git",
        url="https://github.com/soarsmu/BugsInPy",
        revision="",
        license="未在仓库声明（gh api license=null）；框架与 17 个项目各自的许可需逐个核",
        license_source="gh api repos/soarsmu/BugsInPy -> license: null [2026-10-07]",
        gated=False,
        expected_rows=0,
        note="框架要 pip 安装（framework/），每个项目还要独立虚拟环境；本机 PyPI 慢/可能受限 ⇒ 预期 needs_install",
    ),
}


class AbTaskError(RuntimeError):
    """取用失败：显式报错，不静默降级。"""


def _get(url: str, timeout: int = 120) -> bytes:
    """取一个 URL。**网络失败一律翻成 AbTaskError**：

    main 只认 (AbTaskError, KeyError)，URLError / HTTPError / socket.timeout / IncompleteRead
    逃出去就是一段栈回溯，而"网不通 / 上游 5xx / 传到一半断了"恰恰是本模块最常见的失败形态，
    它们必须和"本地没有语料"一样，逐条带 reason 写出来。
    """

    request = urllib.request.Request(url, headers={"User-Agent": "ab-tasks/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as error:
        raise AbTaskError("取 %s 失败：%s: %s" % (url, type(error).__name__, error)) from error


def _hf_dataset_id(source: TaskSource) -> str:
    """HF datasets-server 的 dataset 名：**从登记的源 URL 里取**，不在请求里另写一份。

    目录、rows_path、锁记录都按 dataset_id 键控；请求里写死一个数据集名，会让第二个
    hf-rows 源把数据取到自己的目录名下——错得静默。
    """

    marker = "/datasets/"
    if marker not in source.url:
        raise AbTaskError("源 %s 的 URL 里没有 %s，取不出 HF dataset 名：%s" % (source.id, marker, source.url))
    dataset = source.url.split(marker, 1)[1].strip("/")
    if not dataset or "/" not in dataset:
        raise AbTaskError("源 %s 的 URL 取出的 dataset 名不合法：%r" % (source.id, dataset))
    return dataset


def dataset_dir(dataset_id: str, root: Path) -> Path:
    return Path(root) / ("%s@%s" % (dataset_id, SOURCES[dataset_id].revision))


def rows_path(dataset_id: str, root: Path) -> Path:
    return dataset_dir(dataset_id, root) / "rows.jsonl"


def load_rows(dataset_id: str, root: Path) -> list[dict]:
    path = rows_path(dataset_id, root)
    if not path.is_file():
        raise AbTaskError("任务元数据不在本地：%s（先跑 --fetch %s）" % (path, dataset_id))
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(dataset_id: str, *, root: Path, offline: bool = False) -> dict:
    """把任务元数据取到 <root>/<id>@<rev>/rows.jsonl；返回取用读数（字节 / 耗时 / 摘要）。"""

    source = SOURCES[dataset_id]
    if source.kind != "hf-rows":
        raise AbTaskError("%s 不是 hf-rows 类型（kind=%s）；git 类型请用 --probe" % (dataset_id, source.kind))
    destination = dataset_dir(dataset_id, root)
    destination.mkdir(parents=True, exist_ok=True)
    target = rows_path(dataset_id, root)
    if target.is_file():
        data = target.read_bytes()
        return {"dataset": dataset_id, "reused": True, "bytes": len(data), "sha256": _sha256(data), "path": str(target)}
    if offline:
        raise AbTaskError("offline=True 但本地没有 %s" % target)
    started = time.time()
    hf_dataset = _hf_dataset_id(source)
    rows: list[dict] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode(
            {"dataset": hf_dataset, "config": source.hf_config, "split": source.hf_split,
             "offset": offset, "length": PAGE_SIZE}
        )
        page = json.loads(_get("%s?%s" % (ROWS_ENDPOINT, query)).decode("utf-8"))
        rows.extend(item["row"] for item in page["rows"])
        total = page.get("num_rows_total")
        offset += PAGE_SIZE
        if not page["rows"] or (total is not None and offset >= total):
            break
    payload = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n"
    target.write_text(payload, encoding="utf-8", newline="\n")
    elapsed = round(time.time() - started, 2)
    reading = {
        "dataset": dataset_id,
        "url": source.url,
        "revision": source.revision,
        "rows": len(rows),
        "bytes": len(payload.encode("utf-8")),
        "sha256": _sha256(payload.encode("utf-8")),
        "seconds": elapsed,
        "path": str(target),
        "expected_rows": source.expected_rows,
        "row_count_matches": (len(rows) == source.expected_rows) if source.expected_rows else None,
    }
    if source.expected_rows and len(rows) != source.expected_rows:
        reading["drift"] = "取到 %d 行，登记的是 %d 行" % (len(rows), source.expected_rows)
    return reading


def find_row(instance_id: str, *, root: Path) -> dict:
    for row in load_rows("swe-bench-verified", root):
        if row.get("instance_id") == instance_id:
            return row
    raise AbTaskError("找不到 instance_id=%s（--list 看可用任务）" % instance_id)


def _test_files(test_patch: str) -> list[str]:
    """从 test_patch 里取被改动的**测试文件**（相对仓库根的 POSIX 路径）。"""

    files: list[str] = []
    for line in test_patch.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            path = line[4:].strip()
            if path == "/dev/null":
                continue
            if path.startswith(("a/", "b/")):
                path = path[2:]
            if path not in files:
                files.append(path)
    return files


def _select_style(fail_to_pass: list[str], pass_to_pass: list[str]) -> str:
    ids = fail_to_pass + pass_to_pass
    if not ids:
        return "none"
    if all("::" in item or item.endswith(".py") for item in ids):
        return "append_node_ids"
    if all("::" not in item and "/" not in item for item in ids):
        return "by_keyword"
    return "none"


def _baseline_dir(instance_id: str, root: Path) -> Path:
    return Path(root) / instance_id / "baseline"


def _source_record(instance_id: str, *, root: Path) -> dict | None:
    """读 <root>/<id>/source.json（不存在或读不出来就返回 None，由调用方写 unavailable）。"""

    path = Path(root) / instance_id / "source.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _required_source_record(instance_id: str, *, root: Path) -> dict:
    """要用的来源记录：缺了 / 读不出来 / 字段不全一律显式报错。

    旧写法 `json.loads(...)` 会在缺文件时抛 FileNotFoundError、在字段缺失时抛 KeyError，
    两条都绕过了 main 的 (AbTaskError, KeyError) 分类（KeyError 只剩一句 `ab_tasks: 'url'`）。
    """

    path = Path(root) / instance_id / "source.json"
    record = _source_record(instance_id, root=root)
    if record is None:
        raise AbTaskError(
            "缺来源记录 %s：先跑 --baseline %s（partial 提取或手工建的树都没有它）"
            % (path, instance_id)
        )
    missing = [key for key in ("url", "sha256", "bytes") if key not in record]
    if missing:
        raise AbTaskError(
            "来源记录 %s 缺字段 %s：重跑 --baseline %s 重建（不猜、不补 0）"
            % (path, "/".join(missing), instance_id)
        )
    return record


def _baseline_marker(instance_id: str, *, root: Path, url: str) -> bool:
    """baseline/ 目录能不能被当成「已经解压好的那棵树」。

    判据是**正向标记**：目录非空 + source.json 读得出来 + url 与这次要下载的一致。
    只看「目录非空」会把 partial / 中断的提取、上一次别的 commit 留下的树一起当成可用，
    而且不会写 source.json——下游 verify_oracle 随后就在缺字段上崩。
    """

    directory = _baseline_dir(instance_id, root)
    if not (directory.is_dir() and any(directory.iterdir())):
        return False
    record = _source_record(instance_id, root=root)
    return record is not None and record.get("url") == url


def tarball_url(repo: str, commit: str) -> str:
    return "https://codeload.github.com/%s/tar.gz/%s" % (repo, commit)


def oracle(instance_id: str, *, root: Path, python: str = DEFAULT_PYTHON) -> dict:
    """产出一条任务的**外部 oracle**：怎么跑、期望什么、跑不跑得动。"""

    row = find_row(instance_id, root=root)
    fail_to_pass = json.loads(row["FAIL_TO_PASS"])
    pass_to_pass = json.loads(row["PASS_TO_PASS"])
    test_files = _test_files(row["test_patch"])
    style = _select_style(fail_to_pass, pass_to_pass)
    baseline_dir = _baseline_dir(instance_id, root)
    return {
        "oracle_schema_version": ORACLE_SCHEMA_VERSION,
        "instance_id": instance_id,
        "repo": row["repo"],
        "base_commit": row["base_commit"],
        "environment_setup_commit": row["environment_setup_commit"],
        "version": row["version"],
        "difficulty": row.get("difficulty", ""),
        "fail_to_pass": fail_to_pass,
        "pass_to_pass": pass_to_pass,
        "test_files": test_files,
        "test_command": {
            "argv": ["-m", "pytest", "--no-header", "-rA", "-p", "no:cacheprovider"],
            "argv_note": "argv 是**解释器之后**的参数；节点/关键字按 test_select_style 追加",
            "cwd": str(baseline_dir),
            "timeout_s": 900,
            "env": {"PYTEST_ADDOPTS": "--basetemp=%s" % (Path(root) / instance_id / "pytest-tmp")},
        },
        "test_select_style": style,
        "python": python,
        "patch": {"kind": "unified_diff", "path": str(Path(root) / instance_id / "patch.diff")},
        "test_patch": {"kind": "unified_diff", "path": str(Path(root) / instance_id / "test.patch.diff")},
        "source": {"url": tarball_url(row["repo"], row["base_commit"]), "sha256": ""},
        "baseline_source": (_source_record(instance_id, root=root) or {}).get("baseline_source", "not_extracted"),
        "declared_status": "unknown",
        "status_reason": "",
        "baseline_dir": str(baseline_dir),
    }


def baseline(instance_id: str, *, root: Path, apply_test_patch: bool = False) -> dict:
    """取基线树（pre-fix）：codeload tarball + 剥顶层；可选把 test_patch 打上（SWE-bench 的协议）。"""

    row = find_row(instance_id, root=root)
    repo, commit = row["repo"], row["base_commit"]
    directory = _baseline_dir(instance_id, root)
    task_dir = Path(root) / instance_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "patch.diff").write_text(row["patch"], encoding="utf-8", newline="\n")
    (task_dir / "test.patch.diff").write_text(row["test_patch"], encoding="utf-8", newline="\n")
    source_record = task_dir / "source.json"
    reused = False
    url = tarball_url(repo, commit)
    if not _baseline_marker(instance_id, root=root, url=url):
        started = time.time()
        data = _get(url, timeout=600)
        elapsed = round(time.time() - started, 2)
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            members = []
            for member in archive.getmembers():
                if "/" not in member.name or member.isdir():
                    continue
                member.name = member.name.split("/", 1)[1]
                members.append(member)
            archive.extractall(directory, members=members, filter="data")
        source_record.write_text(
            json.dumps({"url": url, "bytes": len(data), "sha256": _sha256(data), "seconds": elapsed,
                        "baseline_source": "fresh_extract",
                        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
    else:
        reused = True
    record = _required_source_record(instance_id, root=root)
    applied: dict = {"applied": False}
    if apply_test_patch:
        applied = apply_patch(instance_id, root=root, patch_name="test.patch.diff")
    files = sum(1 for item in directory.rglob("*") if item.is_file()) if directory.is_dir() else 0
    return {"instance_id": instance_id, "repo": repo, "base_commit": commit, "baseline_dir": str(directory),
            "baseline_source": "reused" if reused else "fresh_extract",
            "recorded_source": record.get("baseline_source", "unknown"),
            "reused": reused, "download": record, "test_patch_applied": applied, "files": files}


#: pytest 的 rootdir 锚点：任务树里有任意一个，pytest 就会把 rootdir 定在树里，
#: 不会再向上读到**宿主仓库**的配置。
PYTEST_ROOT_ANCHORS = ("pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg", "setup.py")


def _pytest_isolation(argv: list[str], *, cwd: Path, task_dir: Path) -> list[str]:
    """任务树自己没有任何 pytest 根标记时，给 oracle 一份**隔离的空配置**。

    oracle 跑在 <root>/<id>/baseline 下，而它常常落在平台仓库之内（.tmp/）：pytest 从参数的
    共同祖先向上找 rootdir 锚点，一路找到**本仓库的 pytest.ini**，于是 -p no:cacheprovider
    与仓库的 cache_dir + --strict-config 冲突（实测 ERROR: Unknown config option: cache_dir、
    退出码 4）。那是宿主配置泄漏，不是这个任务跑不起来——把环境问题说成任务问题正是要避免的
    归因错误。隔离配置写在任务目录（<root>/<id>/）里，不碰 baseline 树本身。

    树里**有**锚点时原样返回：任务自己的配置（addopts / markers / testpaths）必须照用，
    pytest 也不会再向上走。
    """

    if any((cwd / name).is_file() for name in PYTEST_ROOT_ANCHORS):
        return argv
    ini = task_dir / "pytest-isolation.ini"
    if not ini.is_file():
        task_dir.mkdir(parents=True, exist_ok=True)
        ini.write_text("[pytest]" + chr(10), encoding="utf-8", newline=chr(10))
    return [*argv, "-c", str(ini), "--rootdir", str(cwd)]


def _run(argv: list[str], *, cwd: Path, timeout: int = 900, env: dict | None = None) -> dict:
    """跑一条命令。**完整输出**（stdout / stderr）与截断尾（*_tail，只给读数看）都要给：

    旧版只留最后 4000 字符，而 _collect 的 node id、verify_oracle 的 PASSED/FAILED 摘要都从
    `stdout_tail` 里解析——超过 4000 字符的套件（SWE-bench 仓库的常态）于是**静默丢节点与结果**，
    node 落进 unresolved / 既非红也非绿。subprocess.run 本来就把整份输出读进内存，
    保留完整串不增加内存量级；截断只用于载荷里的展示字段。
    """

    started = time.time()
    merged = dict(os.environ)
    merged.update(env or {})
    try:
        completed = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout, env=merged)
        return {"exit_code": completed.returncode, "seconds": round(time.time() - started, 2),
                "stdout": completed.stdout, "stderr": completed.stderr,
                "stdout_tail": completed.stdout[-4000:], "stderr_tail": completed.stderr[-2000:],
                "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": None, "seconds": round(time.time() - started, 2),
                "stdout": "", "stderr": "", "stdout_tail": "",
                "stderr_tail": "timeout after %ss" % timeout, "timed_out": True}
    except OSError as exc:
        return {"exit_code": None, "seconds": round(time.time() - started, 2),
                "stdout": "", "stderr": "", "stdout_tail": "",
                "stderr_tail": "%s: %s" % (type(exc).__name__, exc), "timed_out": False}


def _git(directory: Path, args: list[str]) -> dict:
    return _run(["git"] + args, cwd=directory, timeout=300)


def init_repo(instance_id: str, *, root: Path) -> dict:
    """把基线树变成 git 仓库：这样才能 git apply 补丁、并给 agent 的改动算 diff。"""

    directory = _baseline_dir(instance_id, root)
    if not (directory / ".git").is_dir():
        _git(directory, ["init", "-q"])
        _git(directory, ["add", "-A"])
        _git(directory, ["-c", "user.email=ab@local", "-c", "user.name=ab", "commit", "-qm", "baseline"])
    head = _git(directory, ["rev-parse", "HEAD"])
    return {"head": head["stdout_tail"].strip(), "exit_code": head["exit_code"]}


def apply_patch(instance_id: str, *, root: Path, patch_name: str = "test.patch.diff") -> dict:
    directory = _baseline_dir(instance_id, root)
    patch_file = Path(root) / instance_id / patch_name
    if not patch_file.is_file():
        return {"applied": False, "reason": "补丁不在本地：%s" % patch_file}
    init_repo(instance_id, root=root)
    result = _git(directory, ["apply", "--whitespace=nowarn", str(patch_file.resolve())])
    return {"applied": result["exit_code"] == 0, "exit_code": result["exit_code"],
            "stderr": result["stderr_tail"][-400:], "file": str(patch_file)}


def probe(instance_id: str, *, root: Path, python: str = DEFAULT_PYTHON) -> dict:
    """实测这个任务能不能在本机跑：只做 --collect-only（便宜、且失败形态可分类）。"""

    directory = _baseline_dir(instance_id, root)
    if not directory.is_dir():
        return {"instance_id": instance_id, "measured_status": "rejected",
                "status_reason": "基线树还没有：先跑 --baseline %s --apply-test-patch" % instance_id}
    payload = oracle(instance_id, root=root, python=python)
    argv = [python] + payload["test_command"]["argv"] + ["--collect-only", "-q"] + payload["test_files"]
    argv = _pytest_isolation(argv, cwd=directory, task_dir=Path(root) / instance_id)
    result = _run(argv, cwd=directory, timeout=600, env=payload["test_command"]["env"])
    tail = (result["stdout"] + result["stderr"]).lower()
    if result["timed_out"]:
        status, reason = "environment_unavailable", "collect-only 超时"
    elif "modulenotfounderror" in tail or "importerror" in tail:
        status, reason = "needs_install", "collect 阶段 ImportError/ModuleNotFoundError（缺依赖，本机不装）"
    elif result["exit_code"] == 0:
        status, reason = "runnable", "collect-only 通过（可跑外部 oracle）"
    else:
        status, reason = "environment_unavailable", "collect-only 非零退出且不是缺依赖（见 stdout_tail）"
    return {"instance_id": instance_id, "measured_status": status, "status_reason": reason,
            "python": python, "argv": argv, "exit_code": result["exit_code"], "seconds": result["seconds"],
            "stdout_tail": result["stdout_tail"][-1500:], "stderr_tail": result["stderr_tail"][-800:]}


def run_oracle(instance_id: str, *, root: Path, phase: str, python: str = DEFAULT_PYTHON) -> dict:
    """按 oracle 跑一次外部判据。phase=baseline（未修复）时 fail_to_pass 应当**红**。"""

    payload = oracle(instance_id, root=root, python=python)
    directory = Path(payload["test_command"]["cwd"])
    style = payload["test_select_style"]
    targets = payload["fail_to_pass"] + payload["pass_to_pass"] if style == "append_node_ids" else None
    argv = [python] + payload["test_command"]["argv"]
    if style == "append_node_ids":
        argv += targets or []
    elif style == "by_keyword":
        names = [name.split("::")[-1] for name in payload["fail_to_pass"] + payload["pass_to_pass"]]
        argv += payload["test_files"] + ["-k", " or ".join(names)]
    else:
        argv += payload["test_files"]
    argv = _pytest_isolation(argv, cwd=directory, task_dir=Path(root) / instance_id)
    result = _run(argv, cwd=directory, timeout=payload["test_command"]["timeout_s"],
                  env=payload["test_command"]["env"])
    # 逐用例结果从 -rA 摘要解析（_outcomes）：pytest 的摘要行是**行首**的
    # "PASSED/FAILED/ERROR <node id>"，旧写法 count(" PASSED")（带前导空格）几乎恒为 0，
    # 于是 run_oracle 的三个计数在真实运行里永远是 0，读的人会以为一条都没跑。
    outcomes = _outcomes(result["stdout"])
    decided = {"PASSED": 0, "FAILED": 0, "ERROR": 0}
    for verdict in outcomes.values():
        if verdict in decided:
            decided[verdict] += 1
    return {"instance_id": instance_id, "phase": phase, "argv": argv, "exit_code": result["exit_code"],
            "seconds": result["seconds"], "timed_out": result["timed_out"],
            "passed": decided["PASSED"], "failed": decided["FAILED"], "errors": decided["ERROR"],
            "stdout_tail": result["stdout_tail"][-3000:], "stderr_tail": result["stderr_tail"][-1000:]}



OUTCOME_RE = None  # 延迟构造：见 _outcomes()


def _outcomes(text: str) -> dict[str, str]:
    """从 pytest -rA 的短摘要里解析 node id → 结果（PASSED / FAILED / ERROR / SKIPPED）。"""

    import re

    outcomes: dict[str, str] = {}
    pattern = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+(\S+)")
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            outcomes[match.group(2)] = match.group(1)
    return outcomes


def _collect(instance_id: str, *, root: Path, python: str) -> dict:
    payload = oracle(instance_id, root=root, python=python)
    directory = Path(payload["test_command"]["cwd"])
    argv = [python] + payload["test_command"]["argv"] + ["--collect-only", "-q"] + payload["test_files"]
    argv = _pytest_isolation(argv, cwd=directory, task_dir=Path(root) / instance_id)
    result = _run(argv, cwd=directory, timeout=900, env=payload["test_command"]["env"])
    text = result["stdout"] + result["stderr"]
    ids = [line.strip() for line in result["stdout"].splitlines() if "::" in line and not line.startswith(" ")]
    needs: list[str] = []
    for line in text.splitlines():
        marker = "No module named "
        if marker in line:
            name = line.split(marker, 1)[1].strip().strip("'\"")
            if name not in needs:
                needs.append(name)
    return {"argv": argv, "exit_code": result["exit_code"], "seconds": result["seconds"],
            "collected": len(ids), "node_ids": ids, "needs_deps": needs,
            "stdout_tail": result["stdout_tail"][-2500:], "stderr_tail": result["stderr_tail"][-1200:]}


def _resolve(requested: list[str], collected: list[str]) -> tuple[list[str], list[str], list[str]]:
    """把上游的期望解析成真实 node id。上游有的写文件名、有的只写裸函数名——**不许照抄**。"""

    resolved: list[str] = []
    unresolved: list[str] = []
    ambiguous: list[str] = []
    for item in requested:
        if "::" in item:
            if item in collected:
                resolved.append(item)
            else:
                unresolved.append(item)
            continue
        name = item.split("::")[-1]
        hits = [node for node in collected if node.split("::")[-1] == name or node.split("::")[-1].startswith(name + "[")]
        if len(hits) == 1:
            resolved.append(hits[0])
        elif hits:
            ambiguous.append("%s -> %d 个候选" % (item, len(hits)))
        else:
            unresolved.append(item)
    return resolved, unresolved, ambiguous


def verify_oracle(instance_id: str, *, root: Path, python: str = DEFAULT_PYTHON) -> dict:
    """在**基线树**上实测：fail_to_pass 必须全红、pass_to_pass 必须全绿。做不到就是 reject。"""

    payload = oracle(instance_id, root=root, python=python)
    row = find_row(instance_id, root=root)
    directory = Path(payload["test_command"]["cwd"])
    statement = Path(root) / instance_id / "problem_statement.txt"
    statement.parent.mkdir(parents=True, exist_ok=True)
    statement.write_text(row["problem_statement"], encoding="utf-8", newline="\n")
    collected = _collect(instance_id, root=root, python=python)
    f2p, f2p_unresolved, f2p_ambiguous = _resolve(payload["fail_to_pass"], collected["node_ids"])
    p2p, p2p_unresolved, p2p_ambiguous = _resolve(payload["pass_to_pass"], collected["node_ids"])

    def run(ids: list[str]) -> dict:
        if not ids:
            return {"argv": [], "exit_code": None, "seconds": 0.0, "outcomes": {}, "stdout_tail": "", "stderr_tail": ""}
        argv = [python] + payload["test_command"]["argv"] + ids
        argv = _pytest_isolation(argv, cwd=directory, task_dir=Path(root) / instance_id)
        result = _run(argv, cwd=directory, timeout=payload["test_command"]["timeout_s"],
                      env=payload["test_command"]["env"])
        return {"argv": argv, "exit_code": result["exit_code"], "seconds": result["seconds"],
                "outcomes": _outcomes(result["stdout"]), "stdout_tail": result["stdout_tail"][-2500:],
                "stderr_tail": result["stderr_tail"][-1200:]}

    f2p_run = run(f2p)
    p2p_run = run(p2p)
    f2p_green = [node for node in f2p if f2p_run["outcomes"].get(node) == "PASSED"]
    f2p_red = [node for node in f2p if f2p_run["outcomes"].get(node) in ("FAILED", "ERROR")]
    p2p_green = [node for node in p2p if p2p_run["outcomes"].get(node) == "PASSED"]
    p2p_red = [node for node in p2p if p2p_run["outcomes"].get(node) in ("FAILED", "ERROR")]
    # 每条解析出来的 node 都要有**决定性结果**：SKIPPED / XFAIL 与"根本没出现在摘要里"同样
    # 只是"没测到"，既不算红也不算绿。旧口径只看 f2p_green / p2p_red，于是"全部被跳过"这类
    # 任务 rejected=False 而 measured.fail_to_pass_all_red=False——同一份载荷自相矛盾，
    # 且一个从未被验证过的任务被静默放行。
    decisive = ("PASSED", "FAILED", "ERROR")
    f2p_undecided = [node for node in f2p if f2p_run["outcomes"].get(node) not in decisive]
    p2p_undecided = [node for node in p2p if p2p_run["outcomes"].get(node) not in decisive]
    problems: list[str] = []
    if collected["needs_deps"]:
        problems.append("needs_deps=%s" % collected["needs_deps"])
    if collected["exit_code"] != 0:
        problems.append("collect-only 非零退出")
    if f2p_unresolved or p2p_unresolved or f2p_ambiguous or p2p_ambiguous:
        problems.append("node id 解析不全")
    if not f2p:
        problems.append("fail_to_pass 解析后为空")
    if f2p_green:
        problems.append("基线树上 fail_to_pass 有 %d 条已经绿（任务无效）" % len(f2p_green))
    if f2p_undecided:
        problems.append("fail_to_pass 有 %d 条没有决定性结果（被跳过 / 没跑到 / 不在摘要里）" % len(f2p_undecided))
    if p2p_red:
        problems.append("基线树上 pass_to_pass 有 %d 条红" % len(p2p_red))
    if p2p_undecided:
        problems.append("pass_to_pass 有 %d 条没有决定性结果（被跳过 / 没跑到 / 不在摘要里）" % len(p2p_undecided))
    rejected = bool(problems)
    if collected["needs_deps"]:
        reason = "unrunnable_local"
    elif not f2p or f2p_unresolved or f2p_ambiguous or p2p_unresolved or p2p_ambiguous:
        reason = "no_oracle"
    elif f2p_green:
        reason = "other"
    elif p2p_red or f2p_undecided or p2p_undecided or collected["exit_code"] != 0:
        reason = "unrunnable_local"
    else:
        reason = ""
    source = _required_source_record(instance_id, root=root)
    return {
        "task_id": instance_id,
        "source": {"dataset": "swe-bench-verified", "revision": SOURCES["swe-bench-verified"].revision,
                   "license": SOURCES["swe-bench-verified"].license,
                   "license_source": SOURCES["swe-bench-verified"].license_source,
                   "language": "python"},
        "baseline": {"repo_url": "https://github.com/%s" % row["repo"], "repo_revision": row["base_commit"],
                     "base_tree_ref": {"url": source["url"], "sha256": source["sha256"], "bytes": source["bytes"]},
                     "task_statement_ref": str(statement),
                     "task_statement_sha256": _sha256(statement.read_bytes())},
        "oracle": {"kind": "frozen_tests", "fail_to_pass": f2p, "pass_to_pass": p2p,
                   "collection_ok_on_base": collected["exit_code"] == 0 and not collected["needs_deps"],
                   "needs_deps": collected["needs_deps"], "runtime_s": round(f2p_run["seconds"] + p2p_run["seconds"], 2)},
        "cost": {"bytes_download": source["bytes"], "seconds_setup": source["seconds"],
                 "seconds_oracle_run": round(collected["seconds"] + f2p_run["seconds"] + p2p_run["seconds"], 2)},
        "reject": {"rejected": rejected, "reason": reason},
        "measured": {
            "fail_to_pass_all_red": bool(f2p) and not f2p_green and len(f2p_red) == len(f2p),
            "pass_to_pass_all_green": bool(p2p) and not p2p_red and len(p2p_green) == len(p2p),
            "fail_to_pass_total": len(f2p), "fail_to_pass_red": len(f2p_red), "fail_to_pass_green": len(f2p_green),
            "pass_to_pass_total": len(p2p), "pass_to_pass_green": len(p2p_green), "pass_to_pass_red": len(p2p_red),
            "collected_on_base": collected["collected"], "collection_exit_code": collected["exit_code"],
            "select_style": payload["test_select_style"], "selected_total": len(f2p) + len(p2p),
            "fail_to_pass_unresolved": f2p_unresolved, "pass_to_pass_unresolved": p2p_unresolved,
            "fail_to_pass_ambiguous": f2p_ambiguous, "pass_to_pass_ambiguous": p2p_ambiguous,
            "problems": problems,
        },
        "raw": {"collect": {k: collected[k] for k in ("argv", "exit_code", "seconds", "needs_deps")},
                "fail_to_pass_run": {"argv": f2p_run["argv"], "exit_code": f2p_run["exit_code"], "seconds": f2p_run["seconds"]},
                "pass_to_pass_run": {"argv": p2p_run["argv"], "exit_code": p2p_run["exit_code"], "seconds": p2p_run["seconds"]}},
    }


def _lock_entries(root: Path) -> dict:
    entries: dict[str, dict] = {}
    for dataset_id, source in SOURCES.items():
        directory = dataset_dir(dataset_id, root)
        if not directory.is_dir():
            continue
        files = {}
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                files[path.relative_to(directory).as_posix()] = _sha256(path.read_bytes())
        entries[dataset_id] = {"revision": source.revision, "url": source.url, "files": files}
    return entries


def _baseline_entries(root: Path) -> dict:
    """基线树（每个任务一棵）的来源记录：URL + tarball sha256 + 记录文件自身的哈希。

    这里**不**存整棵树（GB 级）。verfiy 检查的是"来源记录没被改写"；要证明上游没变，
    重跑 --baseline 会重新下载并与这里的 sha256 比对（网络依赖，因此不放进 --verify）。
    """

    entries: dict[str, dict] = {}
    for path in sorted(Path(root).glob("*/source.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries[path.parent.name] = {
            "url": record.get("url", ""), "sha256": record.get("sha256", ""),
            "bytes": record.get("bytes", 0), "record": path.as_posix(),
            "record_sha256": _sha256(path.read_bytes()),
            # 这两条字段说明"这条记录是怎么来的"：老记录没有该字段时写 unknown，**不许写成 fresh_extract**
            "baseline_source": record.get("baseline_source", "unknown"),
            "extracted_at": record.get("extracted_at", "unknown"),
        }
    return entries


def record_lock(*, root: Path, lock_path: Path = LOCK_PATH) -> dict:
    payload = {
        "schema_version": TASKS_SCHEMA_VERSION,
        "recorded_on": time.strftime("%Y-%m-%d"),
        "note": "任务集取用的钉死记录：数据集 revision + 逐文件 sha256。漂移由 --verify 发现，不静默。",
        "datasets": _lock_entries(root),
        "baselines": _baseline_entries(root),
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8", newline="\n")
    return {"lock": str(lock_path), "datasets": sorted(payload["datasets"])}


def verify(*, root: Path, lock_path: Path = LOCK_PATH) -> tuple[bool, list[str]]:
    if not lock_path.is_file():
        return False, ["锁文件不存在：%s（先跑 --record-lock）" % lock_path]
    locked = json.loads(lock_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for dataset_id, entry in locked.get("datasets", {}).items():
        source = SOURCES.get(dataset_id)
        if source is None:
            problems.append("锁里有未登记的数据集 %s" % dataset_id)
            continue
        if source.revision and entry.get("revision") != source.revision:
            problems.append("%s: 登记的 revision 与锁不一致" % dataset_id)
        directory = dataset_dir(dataset_id, root)
        if not directory.is_dir():
            problems.append("%s: 本地没有语料 %s" % (dataset_id, directory))
            continue
        for relative, digest in entry.get("files", {}).items():
            path = directory / relative
            if not path.is_file():
                problems.append("%s: 缺文件 %s" % (dataset_id, relative))
            elif _sha256(path.read_bytes()) != digest:
                problems.append("%s: %s 哈希漂移" % (dataset_id, relative))
    for instance_id, entry in locked.get("baselines", {}).items():
        record = Path(entry.get("record", ""))
        if not record.is_file():
            problems.append("%s: 基线来源记录不在本地 %s" % (instance_id, record))
        elif _sha256(record.read_bytes()) != entry.get("record_sha256"):
            problems.append("%s: 基线来源记录 %s 被改写" % (instance_id, record))
    return (not problems), problems


def reading_context(root: Path) -> dict:
    return {
        "tree": str(Path(root).resolve()),
        "python": DEFAULT_PYTHON,
        "platform": sys.platform,
        "declarations": "tools/ab_tasks.py 的 SOURCES（数据集 revision 钉死）",
    }


def render(*, root: Path, as_json: bool, dataset_id: str | None = None) -> str:
    rows = load_rows(dataset_id or "swe-bench-verified", root=root)
    payload = {
        "schema_version": TASKS_SCHEMA_VERSION,
        "reading_context": reading_context(root),
        "dataset": dataset_id or "swe-bench-verified",
        "rows": len(rows),
        "repos": sorted({row["repo"] for row in rows}),
    }
    if as_json:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    lines = ["dataset=%s rows=%d repos=%d" % (payload["dataset"], payload["rows"], len(payload["repos"]))]
    for row in rows[:80]:
        fail = json.loads(row["FAIL_TO_PASS"])
        lines.append("%-42s %-28s v%-8s f2p=%d" % (row["instance_id"], row["repo"], row["version"], len(fail)))
    if len(rows) > 80:
        lines.append("...（共 %d 条，用 --oracle <id> 看单条）" % len(rows))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args

    def option(name: str, default: str | None = None) -> str | None:
        if name not in args:
            return default
        index = args.index(name)
        if index + 1 >= len(args) or args[index + 1].startswith("--"):
            return default
        return args[index + 1]

    root = Path(option("--root", str(DEFAULT_ROOT)) or str(DEFAULT_ROOT))
    python = option("--python", DEFAULT_PYTHON) or DEFAULT_PYTHON
    try:
        if "--fetch" in args:
            print(json.dumps(fetch(option("--fetch", "swe-bench-verified") or "swe-bench-verified", root=root,
                                   offline="--offline" in args), ensure_ascii=False, indent=2))
            return 0
        if "--oracle" in args:
            payload = oracle(option("--oracle") or "", root=root, python=python)
            print(json.dumps(payload, ensure_ascii=False, indent=2) if as_json else
                  "instance=%s repo=%s style=%s files=%s" % (payload["instance_id"], payload["repo"],
                                                             payload["test_select_style"], payload["test_files"]))
            return 0
        if "--baseline" in args:
            print(json.dumps(baseline(option("--baseline") or "", root=root,
                                      apply_test_patch="--apply-test-patch" in args),
                             ensure_ascii=False, indent=2))
            return 0
        if "--probe" in args:
            print(json.dumps(probe(option("--probe") or "", root=root, python=python), ensure_ascii=False, indent=2))
            return 0
        if "--run-oracle" in args:
            print(json.dumps(run_oracle(option("--run-oracle") or "", root=root,
                                        phase=option("--phase", "baseline") or "baseline", python=python),
                             ensure_ascii=False, indent=2))
            return 0
        if "--verify-oracle" in args:
            print(json.dumps(verify_oracle(option("--verify-oracle") or "", root=root, python=python),
                             ensure_ascii=False, indent=2))
            return 0
        if "--record-lock" in args:
            print(json.dumps(record_lock(root=root), ensure_ascii=False, indent=2))
            return 0
        if "--verify" in args:
            ok, problems = verify(root=root)
            payload = {"ok": ok, "problems": problems, "verify_scope": "lock_and_bytes",
                       "upstream_recheck": False,
                       "note": "verify_scope 覆盖锁记录与本地字节；不重新下载，上游漂移要靠重跑 --baseline 发现"}
            print(json.dumps(payload, ensure_ascii=False, indent=2) if as_json
                  else ("OK (verify_scope=lock_and_bytes, upstream_recheck=false)" if ok else "\n".join(problems)))
            return 0 if ok else 1
        print(render(root=root, as_json=as_json))
        return 0
    except (AbTaskError, KeyError) as exc:
        print("ab_tasks: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
