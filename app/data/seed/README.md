# MySQL Seed 数据说明

这些 seed 文件已按当前 ORM 模型重新生成，编码为 UTF-8 无 BOM。

## 文件

- `orders_seed.json` / `orders_seed.sql`：200 条订单数据，对应 `app.models.order.Order`
- `tickets_seed.json` / `tickets_seed.sql`：80 条工单数据，对应 `app.models.ticket.Ticket`
- `ticket_logs_seed.json` / `ticket_logs_seed.sql`：工单操作日志，对应 `app.models.ticket_log.TicketLog`

## orders 字段

`order_no, user_id, platform, country, currency, total_amount, payment_status, fulfillment_status, logistics_status, shipped_at, delivered_at`

## tickets 字段

`ticket_no, user_id, order_no, session_id, issue_type, title, description, priority, status, source, trace_id`

## ticket_logs 字段

`ticket_no, action, from_status, to_status, operator_id, remark, trace_id`

## 导入建议

先导入 `orders_seed.sql`，再导入 `tickets_seed.sql`，最后导入 `ticket_logs_seed.sql`。

`orders` 和 `tickets` 使用了 `ON DUPLICATE KEY UPDATE`，可以重复执行；`ticket_logs` 没有唯一键，重复执行会追加日志。