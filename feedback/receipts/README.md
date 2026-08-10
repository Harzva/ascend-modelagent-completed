# 修复回执

服务器修复任务在此目录写入 `<repo-name>.json`，格式遵循 [`schema/repair-receipt-v1.schema.json`](../../schema/repair-receipt-v1.schema.json)。

回执不得包含服务器凭据、私有路径、完整原始日志或访问令牌。`evidence` 只保存公开提交、公开仓库文件或经过脱敏的验证摘要。
