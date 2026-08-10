# 比赛反馈数据契约

## 生产者：比赛结果采集任务

生产者读取比赛页面“查看结果”，将每条提交记录规范化后运行：

```bash
python scripts/update_feedback.py --input feedback/incoming.json --archive-snapshot
```

生产者拥有并更新：

- `queue.json`
- `latest.json`
- `models/*.json`

同一个 `project_url + 问题文本` 会生成稳定问题 ID，因此重复采集不会制造重复任务。
采集状态还会生成忽略巡检时间的 `state_hash`；比赛结果没有变化时，脚本不会改写文件或制造重复提交。

## 消费者：服务器模型修复任务

消费者只读取 `queue.json`，按优先级选择一项，通过 `project_url` 定位模型仓库。消费者不得修改生产者拥有的文件；进度和结果写入：

```text
feedback/receipts/<repo-name>.json
```

回执格式见 `schema/repair-receipt-v1.schema.json`。

建议状态：

- `accepted`：已领取
- `fixed`：修复已推送，等待比赛平台复查
- `blocked`：缺少真实证据、权限或其他人工输入

## 解决判定

服务器写入 `fixed` 不代表问题已闭环。只有后续比赛结果快照中对应低分提醒消失，生产者才将模型状态改为 `resolved` 并从 `queue.json` 移除。

## 截图类问题

遇到缺少 `assets/*.png` 时，消费者必须从真实 Model Agent 工作流、真实 NPU 设备调用和真实推理结果生成截图。缺少真实证据时写 `blocked` 回执，不得生成虚假图片。
