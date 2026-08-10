# Ascend Model Agent 完成与反馈闭环

本仓库是昇腾 Model Agent S2 模型适配任务的公开、机器可读状态中心。

- [`完成列表.md`](完成列表.md)：已完成适配并可提交的模型清单，来源于 GitCode 自动生成仓库。
- [`feedback/queue.json`](feedback/queue.json)：服务器适配任务的唯一待修复入口。
- [`feedback/latest.json`](feedback/latest.json)：最近一次比赛“查看结果”采集快照。
- [`feedback/models/`](feedback/models/)：按模型仓库拆分的详细问题与观察历史。
- [`feedback/receipts/`](feedback/receipts/)：服务器修复任务的回执目录。

## 服务器快速消费

```bash
curl -fsSL \
  https://raw.githubusercontent.com/Harzva/ascend-modelagent-completed/main/feedback/queue.json \
  | jq '.items[] | {project_url, model_id, issues, repair_contract}'
```

也可以克隆仓库后领取下一项：

```bash
python scripts/next_repair.py --limit 1
```

## 闭环

1. 适配服务器将已完成模型写入 `完成列表.md`。
2. Codex 定时任务将未提交项目提交到比赛平台。
3. Codex 打开“查看结果”，提取低分提醒并运行 `scripts/update_feedback.py`。
4. 规范化问题提交到 GitHub；服务器读取 `feedback/queue.json`。
5. 服务器只修复对应 `project_url` 的问题，并在 `feedback/receipts/` 写回回执。
6. Codex 再次检查比赛结果；只有平台提醒消失，问题才会从修复队列移除并标记为已解决。

## 安全边界

仓库只能包含公开模型地址、公开项目地址、比赛分数和规范化问题。禁止提交 token、Cookie、`.env`、访问文件、原始聊天日志、本机私有路径或凭据转储。截图修复必须来自真实 NPU 执行或真实适配日志，禁止伪造证据。
