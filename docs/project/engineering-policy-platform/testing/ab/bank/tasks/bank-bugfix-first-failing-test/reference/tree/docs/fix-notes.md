# 修 bug 记录：OrderRepository.insert 的别名 bug

## 根因

`OrderRepository.insert` 把调用方传进来的 `payload` 原样 `append` 进 `self._rows`，
又把同一个 dict 返回。于是内部行与调用方的 dict 是**同一个对象**：

- 改入参：调用方之后复用那个 dict（例如换一单的 id）→ 已存订单被改；
- 改返回值：调用方在返回的 dict 上加字段 → 已存订单被改。

`listing` 本来就是对的（每次新的列表、每行新的 dict），所以问题只在 `insert` 的两个方向。

## 修法

`insert` 存副本、返回另一个副本（浅拷贝足够，本题不要求深拷贝）：

```python
row = dict(payload)     # 存副本：之后改入参不影响内部
self._rows.append(row)
return dict(row)        # 返回另一个副本：改返回值不影响内部
```

`listing` 一个字没改；类与方法签名、docstring 都保留；没有新增校验，也没有新增异常分支。

## 验证

在项目根目录跑：

```powershell
python -m pytest -q
```

修复前是红的（`2 failed, 2 passed`），修复后应全绿（0 failed）；只看目标用例可以跑
`python -m pytest -q tests/test_order_repository.py`（应全绿）。
