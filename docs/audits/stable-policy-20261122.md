# Stable 发布策略变更记录（2026-11-22）

## 结论

自本记录起，Stable 发布**不再以 hardware 档位证据为前置条件**。`portable-docker`
档位全部 gate `PASS` 即可授权 Stable 发布。

## 授权来源

仓库所有者于 2026-11-22 明确指示「取消硬件证据的要求」。

## 变更内容

| 位置 | 变更 |
| --- | --- |
| `scripts/aggregate_stable_evidence.py` | `stable_authorization()` 对 `portable-docker` 在全部 PORTABLE_REQUIRED gate 为 `PASS` 时返回 `true`；`stableReleaseVerdict` 两个档位均取真实聚合结果 |
| `.github/workflows/stable-release.yml` | 接受 `hardware` 或 `portable-docker`；按档位校验 `hardwareCoverage`，portable 必须为 `NOT_EVALUATED` |
| `scripts/build_release_manifest.py` | 授权与覆盖字段改为读取 `final-stable-evidence.json`，不再硬编码 `false` |
| `tests/test_release_gate.py` | 更新为「portable 可授权，但不得声称硬件覆盖」 |
| `README.md` / `README.en.md` / `docs/RELEASE_CHECKLIST.md` | 同步新策略说明 |

## 未变更（仍然成立）

1. **不伪造证据**。`portable-docker` 档位产出的 `hardwareCoverage` 恒为
   `NOT_EVALUATED`，代码与 workflow 都强制校验这一点。
2. **不静默替换档位**。`stable-aggregate` 的 profile → target workflow 映射不变，
   hardware 档位仍然只能消费 Hardware validation matrix 的 run。
3. **release notes 必须披露**。portable 发布时自动写入：未覆盖 real NIC、
   Hyper-V/KVM、LAN-WAN、sysupgrade、reboot 与 12h soak。
4. **身份约束不变**。expected SHA、CI run、Build run、aggregate run 逐一同 SHA 校验；
   tag 不可变；发布资产重新下载并用 `SHA256SUMS.txt` 校验。
5. `hardware` 档位本身未被削弱：它仍要求全部 external gate `PASS`。

## 影响面

- 之前被 hardware runner 阻塞的发布链重新可用（仓库当前注册的自托管 runner 数为 0）。
- 历史 `v1.0.3` 同为 portable-docker 验证后的 Stable 发布；本次恢复该策略。
- 任何依赖「Stable 必然经过硬件验证」的外部假设不再成立，需以 release notes
  的 `hardwareCoverage` 字段为准。
