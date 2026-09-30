# E4 手动 Baseline 建立与标注

## 1. 每个 baseline 会话的最低要求

每个样本使用独立会话完成初始设计。正式登记前确认：

- 台账和计算记录均非空，且不存在 `stale` 项。
- 至少有 5 个可变的数值型台账参数；当前 `Quantity` 不支持材料牌号、载荷类型等分类值。
- 每个变化参数的当前值、单位与 `change_scenarios.json` 中的 `old_value`、`unit` 一致。
- 每个样本至少包含一条两级依赖链，例如：输入参数 -> `calc#N` -> 计算参数 -> `calc#M` -> 下游参数。
- `CalculationRecord.depends_on` 显式列出真实输入参数或上游计算参数。
- 计算所得参数的 `basis` 显式引用产生它的 `calc#N`。
- 用于几何探针的下游参数应为 `confirmed` 或 `frozen`；runner 会在 clone 上受控解冻，不修改原会话。

建议每个 baseline 覆盖五类变化：功率、转速、传动比、寿命，以及模数/轴径/轴承额定载荷/箱体尺寸中的一个数值参数。分类变量待 backend 增加非数值台账类型后再纳入。

## 2. 登记 baseline

在 `change_scenarios.json` 的 `baselines` 中为每个会话添加：

- `sample_id`：实验内唯一名称。
- `task_id`：任务数据集 ID。
- `session_id`：人工完成并检查后的固定会话 UUID。
- `changes`：至少 5 个变化，每项包含 `change_id`、`changed_param`、`old_value`、`new_value`、`unit`。

runner 每次从该固定会话深拷贝新 session，原 baseline 不会被修改。

## 3. 独立 gold 标注

两名机械设计人员分别阅读任务输入、公式、计算书和参数含义，独立标注每个变化应失效的：

- `gold_stale_calcs`：受影响计算记录 ID。
- `gold_stale_params`：受影响下游参数符号。

标注时不能查看系统运行 E4 后产生的 stale 集合。将两人的原始结果分别写入 `annotator_a` 和 `annotator_b`，计算 Cohen's kappa；低于 0.8 时返工。分歧裁决后填写最终 gold 数组，将 `adjudicated` 设为 `true` 并记录 `kappa`。

正式 gold 的参数和计算数组都必须非空，并且所有节点必须存在于固定 baseline。

## 4. 运行顺序

先重启 backend，使 E4 路由和 workflow 轮数限制生效。然后执行：

```powershell
python experiments/E4_invalidation/run_e4.py --validate-only
python experiments/E4_invalidation/run_e4.py --replicates 5
```

只运行某一条件：

```powershell
python experiments/E4_invalidation/run_e4.py --replicates 5 --condition P_recursive
```

## 5. 条件解释

- `C1_no_graph`：变化后不标记失效。
- `C2_full_invalidation`：除被修改根参数外，全部现有参数和计算记录失效，然后执行受限恢复。它不是删除会话重做，论文中应按“全量失效并重算参考条件”报告。
- `C3_direct_only`：只标记直接依赖节点。
- `P_recursive`：沿 `depends_on` 和 `basis` 递归传播。

## 6. 结果解释

- IR/precision 在恢复前的 `state_after_invalidation.json` 上计算。
- ORR/BR 来自 gold 节点经过正式几何参数 Gate 和报告 stale Gate 后的实际接受结果。
- 恢复 workflow 最多 12 轮；恢复耗时、工具调用、新增计算数和恢复后 stale 集合均写入结果。
- `state_after.json` 是恢复后状态；`state_after_invalidation.json` 是恢复前状态。
- 超时或 HTTP 错误会记录阶段、异常类型和 traceback，不计为成功样本。

## 7. 当前已登记样本

当前 baseline：

- `sample_id`：`G_001_single_stage_gearbox_01`
- `session_id`：`1e60a568-5dbb-4d0a-8a22-16e7b2d76854`
- 对象：4 kW、1440 r/min、传动比 4 的单级直齿圆柱齿轮减速器
- 状态：48 个冻结台账参数、35 条计算记录、0 个 stale 节点
- 变化：`P_in` 4→5.5 kW、`n_in` 1440→960 r/min、`i` 4→3.15、`m` 2→2.5 mm、`z_1` 24→25

`gold_annotations.json` 已包含一份依据公式输入、计算结果和机械设计因果关系整理的候选标注。它明确标记为 `yujinghe`，不是第二位专家，也不是已裁决 gold。

独立专家应在不查看 E4 dry probe 结果的前提下完成每个 `annotator_b`：

1. 将 `identity` 改为真实、可审计的专家标识。
2. 分别填写 `stale_params` 和 `stale_calcs`。
3. 对分歧进行裁决，将最终集合写入 `gold_stale_params` 和 `gold_stale_calcs`。
4. 计算并填写 Cohen's kappa，将 `adjudicated` 改为 `true`。
5. 运行正式校验。runner 会在 baseline 的全部 83 个节点上复算 kappa；手填值不一致或低于 0.8 均会拒绝。

草案结构检查：

```powershell
python experiments/E4_invalidation/run_e4.py --validate-draft
```

该命令不会运行实验，也不会绕过正式 gold 门槛。
